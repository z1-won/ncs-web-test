"""HWP(바이너리, OLE/CFB) 읽기. 문단 텍스트·표 셀 텍스트·그림 개체(자리·크기·그림 파일)를 읽고 서식은 읽지 않는다.

그림(HWP 5.0 규격): 본문의 그리기 개체(CTRL_HEADER 'gso ')가 놓인 문단이 그림 자리이고, 그 안의 그림 레코드
(SHAPE_COMPONENT_PICTURE)의 BinItem ID가 문서 정보(DocInfo)의 BIN_DATA 순번을 가리킨다. 그림 파일은 BinData/BINxxxx.확장자 스트림.
"""

import struct
import zlib
from collections.abc import Iterator

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
HWP_SIGNATURE = b"HWP Document File"
END_OF_CHAIN = (0xFFFFFFFE, 0xFFFFFFFF)

TAG_PARA_TEXT, TAG_LIST_HEADER, TAG_TABLE = 0x43, 0x48, 0x4D
TAG_CTRL_HEADER, TAG_PICTURE, TAG_BIN_DATA = 0x47, 0x55, 0x12
GSO = b" osg"                     # 'gso '(그리기 개체) 컨트롤 ID — UINT32 리틀 엔디언
PICTURE_BIN_ID = 71               # 그림 레코드에서 BinItem ID 위치(테두리 12 + 사각형 32 + 자르기 16 + 여백 8 + 밝기·명암·효과 3)
# 문단 텍스트의 제어 문자 중 2바이트짜리. 나머지 제어 문자는 16바이트.
SHORT_CONTROL_CHARS = (0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31)


def read_cfb(data: bytes):
    """CFB 컨테이너를 열어 (read_stream, 스트림 이름 목록)을 돌려준다.

    섹터 n은 파일 오프셋 (n+1)*섹터크기에서 시작한다(CFB 규격).
    순환하는 섹터 체인은 손상으로 보고 예외를 낸다.
    """
    header = data[:512]
    sector_size = 1 << struct.unpack_from("<H", header, 0x1E)[0]
    mini_sector_size = 1 << struct.unpack_from("<H", header, 0x20)[0]
    dir_start = struct.unpack_from("<I", header, 0x30)[0]
    mini_cutoff = struct.unpack_from("<I", header, 0x38)[0]
    minifat_start = struct.unpack_from("<I", header, 0x3C)[0]
    difat_start = struct.unpack_from("<I", header, 0x44)[0]
    difat = list(struct.unpack_from("<109I", header, 0x4C))
    entries_per_sector = sector_size // 4

    def sector(n: int) -> bytes:
        return data[(n + 1) * sector_size : (n + 2) * sector_size]

    next_difat, seen = difat_start, set()
    while next_difat not in END_OF_CHAIN:
        if next_difat in seen:
            raise ValueError("손상된 HWP: DIFAT 순환 참조")
        seen.add(next_difat)
        values = struct.unpack(f"<{entries_per_sector}I", sector(next_difat))
        difat += values[:-1]
        next_difat = values[-1]

    fat: list[int] = []
    for fat_sector in difat:
        if fat_sector not in END_OF_CHAIN:
            fat += struct.unpack(f"<{entries_per_sector}I", sector(fat_sector))

    def chain(start: int, table: list[int]) -> list[int]:
        out, current, visited = [], start, set()
        while current not in END_OF_CHAIN:
            if current in visited or current >= len(table):
                raise ValueError("손상된 HWP: 잘못된 섹터 체인")
            visited.add(current)
            out.append(current)
            current = table[current]
        return out

    def read_chain(start: int, size: int) -> bytes:
        return b"".join(sector(s) for s in chain(start, fat))[:size]

    directory = b"".join(sector(s) for s in chain(dir_start, fat))
    raw_entries = []
    for i in range(len(directory) // 128):
        entry = directory[i * 128 : (i + 1) * 128]
        name_length = struct.unpack_from("<H", entry, 0x40)[0]
        raw_entries.append(
            (
                entry[: max(name_length - 2, 0)].decode("utf-16le", "ignore"),
                entry[0x42],
                struct.unpack_from("<I", entry, 0x74)[0],
                struct.unpack_from("<Q", entry, 0x78)[0],
                struct.unpack_from("<III", entry, 0x44),  # 왼쪽 형제, 오른쪽 형제, 자식
            )
        )
    # 스토리지 트리를 따라 "BodyText/Section0"처럼 경로가 붙은 이름을 만든다.
    # 같은 이름의 스트림이 여러 스토리지에 있을 수 있다(본문 BodyText/Section0과 배포용 미리보기 ViewText/Section0).
    entries: list[tuple[str, int, int, int]] = []

    def walk(index: int, prefix: str, visited: set[int]) -> None:
        if index >= len(raw_entries) or index in visited or index == 0xFFFFFFFF:
            return
        visited.add(index)
        name, kind, start, size, (left, right, child) = raw_entries[index]
        walk(left, prefix, visited)
        path = prefix + name
        if kind == 2:
            entries.append((path, kind, start, size))
        elif kind == 1:
            walk(child, path + "/", visited)
        walk(right, prefix, visited)

    root_name, root_kind, root_start, root_size, (_, _, root_child) = raw_entries[0]
    entries.append((root_name, root_kind, root_start, root_size))
    walk(root_child, "", set())
    ministream = read_chain(entries[0][2], entries[0][3])
    minifat: list[int] = []
    for s in chain(minifat_start, fat):
        minifat += struct.unpack(f"<{entries_per_sector}I", sector(s))

    def read_stream(name: str) -> bytes | None:
        """경로("BodyText/Section0") 또는 루트 바로 아래 이름("FileHeader")으로 스트림을 읽는다."""
        for entry_name, kind, start, size in entries:
            if entry_name == name and kind == 2:
                if size < mini_cutoff:
                    return b"".join(
                        ministream[s * mini_sector_size : (s + 1) * mini_sector_size]
                        for s in chain(start, minifat)
                    )[:size]
                return read_chain(start, size)
        return None

    return read_stream, [name for name, kind, *_ in entries if kind == 2]


def records(buffer: bytes) -> Iterator[tuple[int, int, bytes]]:
    """본문 스트림을 (tag, level, payload)로 나눈다. 잘린 레코드는 예외."""
    i = 0
    while i + 4 <= len(buffer):
        head = struct.unpack_from("<I", buffer, i)[0]
        i += 4
        tag, level, size = head & 0x3FF, (head >> 10) & 0x3FF, head >> 20
        if size == 0xFFF:
            if i + 4 > len(buffer):
                raise ValueError("손상된 HWP: 확장 레코드 길이 누락")
            size = struct.unpack_from("<I", buffer, i)[0]
            i += 4
        if i + size > len(buffer):
            raise ValueError("손상된 HWP: 레코드 잘림")
        yield tag, level, buffer[i : i + size]
        i += size


def para_text(payload: bytes) -> str:
    """PARA_TEXT 레코드에서 문자열을 꺼낸다. 탭·줄바꿈은 공백으로."""
    out, i, n = [], 0, len(payload)
    while i + 2 <= n:
        code = struct.unpack_from("<H", payload, i)[0]
        if code < 32:
            i += 2 if code in SHORT_CONTROL_CHARS else 16
            if code in (9, 10, 13):
                out.append(" ")
            continue
        out.append(chr(code))
        i += 2
    # 한글 밖 글자(이모지·확장 한자 등)는 UTF-16 대리 쌍 두 개로 저장된다 — 하나의 글자로 합치고, 짝 없는 반쪽은 버린다
    return "".join(out).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "ignore")


def is_hwp(data: bytes) -> bool:
    """OLE 파일이고 FileHeader 스트림의 서명이 HWP인가."""
    if data[:8] != OLE_MAGIC:
        return False
    try:
        read_stream, _ = read_cfb(data)
        header = read_stream("FileHeader")
    except (ValueError, struct.error, IndexError):
        return False
    return header is not None and header[:32].rstrip(b"\x00") == HWP_SIGNATURE


def load_hwp(data: bytes) -> tuple[list[list[str]], list[dict]]:
    """(섹션별 문단 목록, 표 목록)을 돌려준다.

    문단 목록은 모든 PARA_TEXT 레코드(표 셀 안 포함)를 순서대로 담는다.
    표의 `paragraph`는 그 표를 가진 문단의 인덱스(같은 기준)다.
    """
    sections, tables, _pictures, _figures, _binaries = load_hwp_full(data)
    return sections, tables


def _bin_items(read_stream, compressed: bool) -> dict[str, dict]:
    """DocInfo의 BIN_DATA → {BinItem 순번(문자열): {'href': 스트림 이름, 'bytes': 크기, 'data': 그림 파일}}. 링크 그림은 파일이 없다."""
    info = read_stream("DocInfo")
    if info is None:
        return {}
    if compressed:
        info = zlib.decompress(info, -15)
    items, n = {}, 0
    for tag, _level, payload in records(info):
        if tag != TAG_BIN_DATA or len(payload) < 2:
            continue
        n += 1
        attr = struct.unpack_from("<H", payload, 0)[0]
        if attr & 0xF not in (1, 2) or len(payload) < 6:          # 0 = 링크(파일 밖)
            items[str(n)] = {"href": None, "bytes": 0, "data": b""}
            continue
        bin_id = struct.unpack_from("<H", payload, 2)[0]
        length = struct.unpack_from("<H", payload, 4)[0]
        ext = payload[6:6 + 2 * length].decode("utf-16le", "replace")
        href = f"BinData/BIN{bin_id:04X}.{ext}"
        raw = read_stream(href)
        mode = (attr >> 4) & 3                                     # 0 = 문서 설정 따름, 1 = 압축, 2 = 압축 안 함
        if raw and (mode == 1 or (mode == 0 and compressed)):
            try:
                raw = zlib.decompress(raw, -15)
            except zlib.error:
                pass                                               # 압축 표시와 달리 그대로 저장된 파일
        items[str(n)] = {"href": href, "bytes": len(raw or b""), "data": raw or b""}
    return items


def load_hwp_full(data: bytes):
    """(섹션별 문단, 표, 그림 [(섹션, 문단, BinItem id)], 그림 크기 [(섹션, 문단, "", 가로, 세로)], 그림 파일 {id: {...}}).

    그림 문단은 그리기 개체를 가진 문단(load_hwp와 같은 인덱스)이고, 크기는 개체 공통 속성의 너비·높이(HWPUNIT)다.
    """
    read_stream, names = read_cfb(data)
    file_header = read_stream("FileHeader")
    if file_header is None:
        raise ValueError("HWP FileHeader 스트림이 없음")
    flags = struct.unpack_from("<I", file_header, 36)[0]
    if flags & 2:
        raise ValueError("암호화된 hwp는 읽을 수 없음")
    # 본문은 BodyText 스토리지의 Section 스트림만. ViewText(배포용 미리보기)에 같은 이름의 사본이 있어도 읽지 않는다.
    section_names = sorted(
        (n for n in names if n.startswith("BodyText/Section")), key=lambda s: int(s.rsplit("Section", 1)[1])
    )
    if not section_names:
        raise ValueError("HWP 본문(BodyText/Section) 스트림이 없음")
    sections, tables, pictures, figures = [], [], [], []
    binaries = _bin_items(read_stream, bool(flags & 1))
    for section_index, name in enumerate(section_names):
        raw = read_stream(name)
        if flags & 1:
            raw = zlib.decompress(raw, -15)
        paragraphs: list[str] = []
        stack: list[tuple[int, dict]] = []  # (level, table)
        cell: tuple[int, dict, tuple[int, int]] | None = None
        shape: tuple[int, int, int] | None = None        # 지금 읽는 그리기 개체 (문단, 가로, 세로)
        for tag, level, payload in records(raw):
            if tag == TAG_CTRL_HEADER and payload[:4] == GSO and len(payload) >= 24:
                width, height = struct.unpack_from("<II", payload, 16)
                shape = (max(len(paragraphs) - 1, 0), width, height)
            elif tag == TAG_PICTURE and shape is not None and len(payload) >= PICTURE_BIN_ID + 2:
                bin_id = str(struct.unpack_from("<H", payload, PICTURE_BIN_ID)[0])
                pictures.append((section_index, shape[0], bin_id))
                figures.append((section_index, shape[0], "", shape[1], shape[2]))
            if tag == TAG_PARA_TEXT:
                paragraphs.append(para_text(payload))
                if cell and level == cell[0] + 1:
                    table, key = cell[1], cell[2]
                    table["cells"][key] = (table["cells"][key] + " " + paragraphs[-1]).strip()
            elif tag == TAG_TABLE:
                rows, cols = struct.unpack_from("<HH", payload, 4)
                table = {
                    "section": section_index,
                    "paragraph": max(len(paragraphs) - 1, 0),
                    "rows": rows,
                    "cols": cols,
                    "cells": {},
                    "styles": None,
                }
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, table))
                tables.append(table)
            elif tag == TAG_LIST_HEADER:
                while stack and stack[-1][0] > level:
                    stack.pop()  # 안쪽 표가 끝남
                if stack and stack[-1][0] == level and len(payload) >= 16:
                    col, row = struct.unpack_from("<HH", payload, 8)
                    table = stack[-1][1]
                    table["cells"].setdefault((row, col), "")
                    cell = (level, table, (row, col))
                else:
                    cell = None
        sections.append(paragraphs)
    return sections, tables, pictures, figures, binaries
