"""HWP(바이너리, OLE/CFB) 읽기. 문단 텍스트와 표 셀 텍스트만 읽고 서식은 읽지 않는다."""

import struct
import zlib
from collections.abc import Iterator

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
HWP_SIGNATURE = b"HWP Document File"
END_OF_CHAIN = (0xFFFFFFFE, 0xFFFFFFFF)

TAG_PARA_TEXT, TAG_LIST_HEADER, TAG_TABLE = 0x43, 0x48, 0x4D
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
    entries = []
    for i in range(len(directory) // 128):
        entry = directory[i * 128 : (i + 1) * 128]
        name_length = struct.unpack_from("<H", entry, 0x40)[0]
        entries.append(
            (
                entry[: max(name_length - 2, 0)].decode("utf-16le", "ignore"),
                entry[0x42],
                struct.unpack_from("<I", entry, 0x74)[0],
                struct.unpack_from("<Q", entry, 0x78)[0],
            )
        )
    ministream = read_chain(entries[0][2], entries[0][3])
    minifat: list[int] = []
    for s in chain(minifat_start, fat):
        minifat += struct.unpack(f"<{entries_per_sector}I", sector(s))

    def read_stream(name: str) -> bytes | None:
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
    return "".join(out)


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
    read_stream, names = read_cfb(data)
    file_header = read_stream("FileHeader")
    if file_header is None:
        raise ValueError("HWP FileHeader 스트림이 없음")
    flags = struct.unpack_from("<I", file_header, 36)[0]
    if flags & 2:
        raise ValueError("암호화된 hwp는 읽을 수 없음")
    section_names = sorted(
        (n for n in names if n.startswith("Section")), key=lambda s: int(s[7:])
    )
    sections, tables = [], []
    for section_index, name in enumerate(section_names):
        raw = read_stream(name)
        if flags & 1:
            raw = zlib.decompress(raw, -15)
        paragraphs: list[str] = []
        stack: list[tuple[int, dict]] = []  # (level, table)
        cell: tuple[int, dict, tuple[int, int]] | None = None
        for tag, level, payload in records(raw):
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
    return sections, tables
