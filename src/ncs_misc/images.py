"""그림 정보 — 쪽 위 출력 크기, 원본 픽셀 크기, 실효 DPI, 캡션, 그리고 픽셀 행 읽기(BMP·PNG·JPEG). 표준 라이브러리만 쓴다.

기타 ③④⑤⑧이 함께 쓴다. hwpx만 지원한다(hwp는 그림 개체를 읽지 못함 — Document.pictures가 비어 있음).

  실효 DPI = 원본 픽셀 ÷ 출력 크기(인치). 출력 크기는 <hp:pic>의 <hp:sz>(HWP 단위, 1/7200 inch) — Document.figures.
  가로·세로 DPI 중 작은 쪽을 쓴다(한쪽만 늘린 그림도 잡기 위해).
"""

from __future__ import annotations

import math
import re
import struct
import zipfile
import zlib
from pathlib import Path

HWPUNIT_PER_INCH = 7200
CAPTION = re.compile(r"\[\s*그림\s*\d+\s*-\s*\d+\s*\]")
CAPTION_AFTER = 6   # 캡션은 보통 그림 아래 — 그림 문단 뒤 이 범위
CAPTION_BEFORE = 3  # 그림 위에 캡션을 둔 원고도 있다


def image_header(data: bytes) -> tuple[str, int, int] | None:
    """(형식, 가로 px, 세로 px). 형식: png / jpeg / jpeg-progressive / bmp / gif. 모르면 None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return ("jpeg-progressive" if marker == 0xC2 else "jpeg"), w, h
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        return None
    if data[:2] == b"BM" and len(data) >= 26:
        w, h = struct.unpack("<ii", data[18:26])
        return "bmp", w, abs(h)
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        return "gif", w, h
    return None


def picture_records(manuscript, sections: list[int] | None = None) -> list[dict]:
    """그림마다 {'section','para','bin_id','format','px','size_hwp','mm','dpi','caption','data'}.

    hwpx 패키지를 한 번 열어 그림 파일(BinData)을 읽는다. 그림 파일이 없거나 형식을 모르면 format=None·dpi=None.
    Document.pictures와 Document.figures는 같은 <hp:pic> 순서이므로 구역별로 순서대로 짝짓는다.
    """
    if manuscript.format != "hwpx" or not manuscript.pictures:
        return []
    wanted = set(sections) if sections is not None else None
    sizes: dict[int, list[tuple[int, int, int]]] = {}
    for s, p, _name, w, h in manuscript.figures:
        sizes.setdefault(s, []).append((p, w, h))
    by_section: dict[int, list[tuple[int, str | None]]] = {}
    for s, p, bin_id in manuscript.pictures:
        by_section.setdefault(s, []).append((p, bin_id))
    out = []
    with zipfile.ZipFile(Path(manuscript.path)) as archive:
        names = set(archive.namelist())
        for s, pics in sorted(by_section.items()):
            if wanted is not None and s not in wanted:
                continue
            figs = sizes.get(s, [])
            paired = figs if len(figs) == len(pics) else [next(((fp, w, h) for fp, w, h in figs if fp == p), (p, 0, 0)) for p, _ in pics]
            paragraphs = manuscript.sections[s]
            for (p, bin_id), (_fp, w, h) in zip(pics, paired):
                href = (manuscript.binaries.get(bin_id) or {}).get("href") if bin_id else None
                data = archive.read(href) if href and href in names else b""
                header = image_header(data) if data else None
                fmt, pw, ph = header if header else (None, 0, 0)
                dpi = None
                if pw and ph and w and h:
                    dpi = round(min(pw / (w / HWPUNIT_PER_INCH), ph / (h / HWPUNIT_PER_INCH)))
                out.append({
                    "section": s, "para": p, "bin_id": bin_id, "format": fmt, "px": (pw, ph), "size_hwp": (w, h),
                    "mm": (round(w / HWPUNIT_PER_INCH * 25.4), round(h / HWPUNIT_PER_INCH * 25.4)), "dpi": dpi,
                    "caption": caption_near(paragraphs, p), "data": data,
                })
    return out


def caption_near(paragraphs: list[str], para: int) -> str:
    """그림 문단 근처의 '[그림 N-M] …' 캡션(없으면 '')."""
    order = list(range(para, min(len(paragraphs), para + CAPTION_AFTER + 1))) + list(range(para - 1, max(-1, para - CAPTION_BEFORE - 1), -1))
    for j in order:
        text = (paragraphs[j] or "").strip()
        if CAPTION.search(text):
            return text[:60]
    return ""


def size_advice(record: dict, target_dpi: int) -> str:
    """그림마다 그때그때 계산한 수정 안내 — 이 출력 크기에서 target_dpi가 되는 픽셀 수, 또는 지금 픽셀로 target_dpi가 되는 최대 출력 크기.

    필요 픽셀 = 출력 길이(인치) × target_dpi, 최대 출력 크기 = 지금 출력 크기 × (실효 DPI ÷ target_dpi).
    수정 제안 끝에 붙이므로 ' — '로 시작한다. 크기·픽셀을 모르면 ''.
    """
    (pw, ph), (w, h), dpi = record["px"], record["size_hwp"], record["dpi"]
    if not (pw and ph and w and h and dpi):
        return ""
    need = (math.ceil(w / HWPUNIT_PER_INCH * target_dpi), math.ceil(h / HWPUNIT_PER_INCH * target_dpi))
    scale = dpi / target_dpi
    fit = (math.floor(w / HWPUNIT_PER_INCH * 25.4 * scale), math.floor(h / HWPUNIT_PER_INCH * 25.4 * scale))
    return (f" — 이 크기({record['mm'][0]}×{record['mm'][1]}mm)로 {target_dpi} DPI가 되려면 {need[0]:,}×{need[1]:,}px 이상 필요"
            f"(지금 {pw:,}×{ph:,}px), 또는 출력 크기를 {fit[0]}×{fit[1]}mm 이하로 줄이면 지금 그림으로 {target_dpi} DPI")


def label(record: dict) -> str:
    """비고에 쓰는 그림 이름 — 캡션이 있으면 캡션, 없으면 '문단 N의 그림'."""
    return f"「{record['caption']}」" if record["caption"] else f"문단 {record['para']}의 그림"


# ── 픽셀 행 읽기 (기타 ④ 작업 표시줄) ─────────────────────────────────────────────


def decode_rows(record: dict, rows: range) -> dict[int, list[tuple[int, int, int]]] | None:
    """원하는 행(위에서 0부터)의 (R, G, B) 목록. BMP·PNG·JPEG(기본 방식)만. 못 읽으면 None."""
    data, fmt = record["data"], record["format"]
    try:
        if fmt == "bmp":
            return _bmp_rows(data, rows)
        if fmt == "png":
            return _png_rows(data, rows)
        if fmt == "jpeg":
            from .jpeg import decode_jpeg_rows
            return decode_jpeg_rows(data, rows)
    except (ValueError, IndexError, struct.error, zlib.error):
        return None
    return None


def _bmp_rows(data: bytes, rows: range) -> dict[int, list[tuple[int, int, int]]] | None:
    offset = struct.unpack("<I", data[10:14])[0]
    w, h = struct.unpack("<ii", data[18:26])
    bits = struct.unpack("<H", data[28:30])[0]
    compression = struct.unpack("<I", data[30:34])[0]
    if bits not in (24, 32) or compression not in (0, 3):
        return None
    bottom_up = h > 0
    h = abs(h)
    step = bits // 8
    stride = (w * step + 3) // 4 * 4
    out = {}
    for y in rows:
        if not 0 <= y < h:
            continue
        stored = (h - 1 - y) if bottom_up else y
        base = offset + stored * stride
        row = data[base:base + w * step]
        out[y] = [(row[x + 2], row[x + 1], row[x]) for x in range(0, len(row) - step + 1, step)]
    return out


def _png_rows(data: bytes, rows: range) -> dict[int, list[tuple[int, int, int]]] | None:
    pos, chunks, palette = 8, [], None
    w = h = depth = ctype = interlace = 0
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"IDAT":
            chunks.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if depth != 8 or interlace or channels is None:
        return None
    raw = zlib.decompress(b"".join(chunks))
    stride = w * channels
    prev = bytearray(stride)
    out, wanted, last = {}, set(rows), max(rows, default=-1)
    for y in range(min(h, last + 1)):
        start = y * (stride + 1)
        filt, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b, c = prev[i], (prev[i - channels] if i >= channels else 0)
            if filt == 1:
                line[i] = (line[i] + a) & 0xFF
            elif filt == 2:
                line[i] = (line[i] + b) & 0xFF
            elif filt == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif filt == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        if y in wanted:
            if ctype == 2 or ctype == 6:
                out[y] = [tuple(line[x:x + 3]) for x in range(0, stride, channels)]
            elif ctype == 3 and palette:
                out[y] = [palette[v] if v < len(palette) else (0, 0, 0) for v in line]
            else:  # 회색조(0)·회색조+알파(4)
                out[y] = [(line[x],) * 3 for x in range(0, stride, channels)]
        prev = line
    return out
