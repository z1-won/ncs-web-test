"""HWP/HWPX 문단 로더. 원본 v1.1 추출 동작을 유지한다."""

import struct
import zlib
import zipfile
import re
import io
import olefile
from .xml_names import HP


def detect_format(path):
    """파일 내용으로 HWP/HWPX 형식을 판별한다."""
    with open(path, "rb") as f:
        head = f.read(8)

    # OLE/CFB 형식이면 HWP 고유 서명을 추가 확인
    if head == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        try:
            with olefile.OleFileIO(path) as ole:
                if not ole.exists("FileHeader"):
                    raise ValueError(f"OLE 파일이지만 HWP의 FileHeader가 없음: {path}")

                header = ole.openstream("FileHeader").read(32)

                if len(header) != 32:
                    raise ValueError(f"FileHeader의 파일 식별 정보가 불완전함: {path}")

                signature = header.rstrip(b"\x00")

                if signature != b"HWP Document File":
                    raise ValueError(f"OLE 파일이지만 HWP 고유 서명이 아님: {path}")

        except OSError as exc:
            raise ValueError(
                f"OLE 내부 구조 또는 FileHeader를 읽을 수 없음: {path}"
            ) from exc

        return "hwp"

    # ZIP 형식이면 HWPX 내부 항목 확인
    if head[:2] == b"PK":
        with zipfile.ZipFile(path) as z:
            names = z.namelist()

        if any(n.startswith("Contents/section") for n in names):
            return "hwpx"

        raise ValueError(f"zip이지만 hwpx가 아님: {path}")

    raise ValueError(f"hwp/hwpx 둘 다 아님 (머리 바이트 {head!r}): {path}")


def _read_cfb(data):
    hdr = data[:512]
    ssz = 1 << struct.unpack_from("<H", hdr, 0x1E)[0]
    mssz = 1 << struct.unpack_from("<H", hdr, 0x20)[0]
    dir_start = struct.unpack_from("<I", hdr, 0x30)[0]
    mini_cutoff = struct.unpack_from("<I", hdr, 0x38)[0]
    minifat_start = struct.unpack_from("<I", hdr, 0x3C)[0]
    difat_start = struct.unpack_from("<I", hdr, 0x44)[0]
    difat = list(struct.unpack_from("<109I", hdr, 0x4C))

    sec = lambda n: data[512 + n * ssz : 512 + (n + 1) * ssz]

    nxt = difat_start
    while nxt not in (0xFFFFFFFE, 0xFFFFFFFF):
        vals = struct.unpack(f"<{ssz // 4}I", sec(nxt))
        difat += vals[:-1]
        nxt = vals[-1]

    fat = []
    for fs in difat:
        if fs not in (0xFFFFFFFE, 0xFFFFFFFF):
            fat += struct.unpack(f"<{ssz // 4}I", sec(fs))

    def chain(start, table):
        out, s = [], start
        while s not in (0xFFFFFFFE, 0xFFFFFFFF) and s < len(table) and len(out) < 10**6:
            out.append(s)
            s = table[s]
        return out

    read_chain = lambda start, size: b"".join(sec(s) for s in chain(start, fat))[:size]

    dirdata = b"".join(sec(s) for s in chain(dir_start, fat))
    entries = []

    for i in range(len(dirdata) // 128):
        e = dirdata[i * 128 : (i + 1) * 128]
        nlen = struct.unpack_from("<H", e, 0x40)[0]
        entries.append(
            (
                e[: max(nlen - 2, 0)].decode("utf-16le", "ignore"),
                e[0x42],
                struct.unpack_from("<I", e, 0x74)[0],
                struct.unpack_from("<Q", e, 0x78)[0],
            )
        )

    ministream = read_chain(entries[0][2], entries[0][3])

    minifat = []
    for s in chain(minifat_start, fat):
        minifat += struct.unpack(f"<{ssz // 4}I", sec(s))

    def read_stream(name):
        for n, typ, start, size in entries:
            if n == name and typ == 2:
                if size < mini_cutoff:
                    return b"".join(
                        ministream[s * mssz : (s + 1) * mssz]
                        for s in chain(start, minifat)
                    )[:size]
                return read_chain(start, size)

    return read_stream, [n for n, t, *_ in entries if t == 2]


def _records(buf):
    """본문 기록을 (tag, level, payload)로 나눠 반환."""
    i = 0

    while i + 4 <= len(buf):
        h = struct.unpack_from("<I", buf, i)[0]
        i += 4

        tag = h & 0x3FF
        level = (h >> 10) & 0x3FF
        size = h >> 20

        if size == 0xFFF:
            size = struct.unpack_from("<I", buf, i)[0]
            i += 4

        yield tag, level, buf[i : i + size]
        i += size


def _hwp_para_text(payload):
    """HWP 문단 데이터에서 문자열 추출."""
    out, i, n = [], 0, len(payload)

    while i + 2 <= n:
        c = struct.unpack_from("<H", payload, i)[0]

        if c < 32:
            i += 2 if c in (0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31) else 16
            if c in (9, 10, 13):
                out.append(" ")
            continue

        out.append(chr(c))
        i += 2

    return "".join(out)


def _load_hwp(path):
    with open(path, "rb") as f:
        data = f.read()

    read_stream, names = _read_cfb(data)
    flags = struct.unpack_from("<I", read_stream("FileHeader"), 36)[0]

    if flags & 2:
        raise ValueError("암호화된 hwp는 읽을 수 없음")

    sections = []
    section_names = sorted(
        [n for n in names if n.startswith("Section")],
        key=lambda s: int(s[7:]),
    )

    for s in section_names:
        raw = read_stream(s)

        if flags & 1:
            raw = zlib.decompress(raw, -15)

        sections.append(
            [_hwp_para_text(p) for tag, lv, p in _records(raw) if tag == 0x43]
        )

    return sections


def _hwpx_para_text(p):
    """삭제 표시 구간을 제외하고 문단의 텍스트를 추출한다.

    중첩된 문단은 바깥 순회에서 따로 처리하므로 내려가지 않는다.
    hp:t 내부 인라인 요소 뒤의 tail 텍스트도 포함한다.
    """
    out, state = [], None

    def walk(el):
        nonlocal state

        for ch in el:
            tag = ch.tag.replace(HP, "")

            if tag == "p":
                continue

            if tag == "deleteBegin":
                state = "del"
            elif tag in ("deleteEnd", "insertEnd"):
                state = None
            elif tag == "insertBegin":
                state = "ins"

            if state != "del":
                if tag == "t":
                    out.append(ch.text or "")
                if ch.tail and el.tag == HP + "t":
                    out.append(ch.tail)

            walk(ch)

    walk(p)
    return "".join(out)


def _load_hwpx(path, max_sections=None):
    from lxml import etree

    sections = []

    with zipfile.ZipFile(path) as z:
        names = sorted(
            [n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)],
            key=lambda n: int(re.search(r"\d+", n).group()),
        )

        for n in names[:max_sections]:
            t = etree.parse(io.BytesIO(z.read(n)))
            sections.append([_hwpx_para_text(p) for p in t.iter(HP + "p")])

    return sections


def load_sections(path, max_sections=None):
    """반환: (형식, 섹션별 문단 목록)."""
    fmt = detect_format(path)

    secs = _load_hwp(path) if fmt == "hwp" else _load_hwpx(path, max_sections)

    clean = lambda s: re.sub(r"\s+", " ", s).strip()

    return fmt, [[clean(p) for p in sec] for sec in secs]
