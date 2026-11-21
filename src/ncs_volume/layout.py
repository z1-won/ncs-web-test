"""원고의 줄 배치 읽기 — 한글이 저장해 둔 줄 배치 정보(줄마다 시작 글자·세로 위치·높이)로 최상위 문단을 행·쪽에 놓는다.

hwp는 PARA_LINE_SEG 레코드, hwpx는 <hp:linesegarray>다. 둘 다 한글이 저장할 때 계산해 넣은 값이라 '한글 화면에 보이는 줄'과 같다.
다른 도구가 만든 파일처럼 배치 정보가 없으면 글자 폭으로 줄 수를 '추정'한다(Layout.measured=False).

- 쪽: 최상위 문단 줄의 세로 위치(vertpos)가 앞 줄보다 작아지면 새 쪽. 구역이 바뀌어도 새 쪽. 한 쪽보다 큰 표는 다음 쪽으로 넘친 만큼 이어 놓는다.
- 행: 글 문단은 줄 수(빈 문단도 1행 — 계약서 제13조 4항 ③ 행 띄움 포함), 표는 행마다 가장 많은 칸의 줄 수의 합,
  그림은 캡션 줄만(그림 자리는 시각 자료로 뺀다 — 제2조 5항). 글상자(그림이 아닌 도형)는 안의 글 줄을 센다.
- 표 안에 든 그림, 글 문단 속 글자처럼 취급한 작은 그림은 따로 빼지 못한다(그 표·문단의 높이에 들어간다).

읽기 도우미(read_cfb·records·para_text·HP)는 ncs_core를 쓰고, 줄 배치 해석만 여기서 한다(코어는 줄 배치를 내주지 않는다).
"""

from __future__ import annotations

import math
import re
import struct
import zipfile
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from ncs_core.documents import detect_format
from ncs_core.hwp import SHORT_CONTROL_CHARS, read_cfb, records
from ncs_core.hwpx import HP, para_text, section_names

from .config import DEFAULT_CONFIG, VolumeConfig

TAG_PARA_HEADER, TAG_PARA_TEXT, TAG_CTRL_HEADER, TAG_LINE_SEG = 0x42, 0x43, 0x47, 0x45
TAG_LIST_HEADER, TAG_PICTURE = 0x48, 0x55
SHAPES = ("rect", "ellipse", "polygon", "curve", "arc", "container", "line", "connectLine", "textart")


@dataclass
class Seg:
    """한글이 저장한 줄 하나: 시작 글자 위치, 세로 위치, 줄 높이, 줄 사이 간격(HWPUNIT)."""

    textpos: int
    vertpos: int
    vertsize: int
    spacing: int


@dataclass
class RawPara:
    """형식(hwp/hwpx)에 상관없이 같은 모양으로 읽은 최상위 문단. 배치 해석(place)의 입력."""

    text: str
    segs: list[Seg]
    kind: str = "text"                                       # text | table | picture | shape
    rows: list[list[tuple[str, int]]] = field(default_factory=list)   # 표: 행마다 [(칸 글, 줄 수)]
    inner: list[tuple[str, list[Seg]]] = field(default_factory=list)   # 그림 캡션·글상자 글: [(글, 줄)]


@dataclass
class Line:
    """산정 대상 행. count는 행 수(표의 한 행은 그 행에서 가장 줄이 많은 칸의 줄 수), height는 쪽에서 차지하는 높이(HWPUNIT).
    page·top은 그 행이 시작하는 쪽(0부터)과 쪽 안 세로 위치 — 추정이면 page=-1. start·end는 unit 글에서 이 행이 맡는 글자 범위."""

    count: int
    height: float
    page: int
    top: float
    start: int
    end: int


@dataclass
class Unit:
    """비교 단위 하나 — 글 문단, 표의 한 행, 캡션·글상자 문단. 기존 원고와 대조할 때 이 글로 짝을 짓는다."""

    text: str
    lines: list[Line]


@dataclass
class Block:
    """최상위 문단 하나를 놓은 결과. head는 구성 판별용 글(표는 앞 두 칸), full은 표 전체 글."""

    kind: str
    head: str
    full: str
    units: list[Unit]
    visual: float            # 시각 자료로 뺀 높이
    page: int                # 시작 쪽(추정이면 -1)
    page_top: bool           # 쪽 맨 위에서 시작하는가
    has_caption: bool = False


@dataclass
class Layout:
    path: Path
    format: str
    measured: bool
    blocks: list[Block]
    pages: int               # 물리 쪽 수(추정이면 0)
    lines_per_page: int
    pitch: int               # 쪽당 행 수 계산에 쓴 줄 간격


# ── hwp ────────────────────────────────────────────────────────────────


def _hwp_chars(payload: bytes) -> list[tuple[int, str]]:
    """PARA_TEXT → [(글자 위치, 글자)]. 줄 배치의 textpos와 같은 단위(WCHAR, 확장 제어 문자는 8)로 센다. 탭·줄바꿈은 공백."""
    out, i, pos, n = [], 0, 0, len(payload)
    while i + 2 <= n:
        code = struct.unpack_from("<H", payload, i)[0]
        if code < 32:
            width = 1 if code in SHORT_CONTROL_CHARS else 8
            if code in (9, 10, 13):
                out.append((pos, " "))
            i += 2 * width
            pos += width
            continue
        out.append((pos, chr(code)))
        i += 2
        pos += 1
    return out


def _hwp_segs(payload: bytes) -> list[Seg]:
    segs = []
    for k in range(len(payload) // 36):
        textpos, vertpos, vertsize, _height, _base, spacing, *_ = struct.unpack_from("<Ii4iiiI", payload, k * 36)
        segs.append(Seg(textpos, vertpos, vertsize, spacing))
    return segs


def _split_text(chars: list[tuple[int, str]], segs: list[Seg]) -> tuple[str, list[int]]:
    """(문단 글, 줄마다 그 글에서의 시작 글자 번호)."""
    text = "".join(c for _, c in chars)
    starts = []
    for seg in segs:
        starts.append(next((k for k, (pos, _) in enumerate(chars) if pos >= seg.textpos), len(chars)))
    return text, starts


def hwp_paragraphs(stream: bytes) -> list[RawPara]:
    """본문 구역 스트림 하나(압축 푼 레코드) → 최상위 문단 목록. 레코드 수준(level)으로 문단·표 칸·그림 캡션을 가른다."""
    paras: list[RawPara] = []
    current: dict | None = None
    ctrl: str | None = None          # 지금 읽는 최상위 문단의 컨트롤('tbl ', 'gso ', …)
    cell: tuple[int, int] | None = None
    inner: dict | None = None        # 표 칸·도형 안 문단 {'level', 'chars', 'segs', 'cell'}

    def close_inner():
        if inner is None or current is None:
            return
        text = "".join(c for _, c in inner["chars"])
        if inner["cell"] is not None:
            current["cells"].setdefault(inner["cell"], []).append((text, len(inner["segs"]) or 1))
        else:
            current["inner"].append((text, inner["segs"]))

    def close():
        if current is None:
            return
        close_inner()
        text, starts = _split_text(current["chars"], current["segs"])
        for seg, start in zip(current["segs"], starts):
            seg.textpos = start          # 이후로는 '문단 글에서의 글자 번호'로 쓴다
        para = RawPara(text=text, segs=current["segs"])
        if current["table"]:
            para.kind = "table"
            rows: dict[int, list[tuple[str, int]]] = {}
            for (row, _col), parts in sorted(current["cells"].items()):
                rows.setdefault(row, []).append((" ".join(t for t, _ in parts).strip(), sum(n for _, n in parts)))
            para.rows = [rows[r] for r in sorted(rows)]
        elif current["shape"]:
            para.kind = "picture" if current["picture"] else "shape"
            para.inner = [(t, s) for t, s in current["inner"]]
        paras.append(para)

    for tag, level, payload in records(stream):
        if tag == TAG_PARA_HEADER and level == 0:
            close()
            current = {"chars": [], "segs": [], "table": False, "shape": False, "picture": False, "cells": {}, "inner": []}
            ctrl, cell, inner = None, None, None
            continue
        if current is None:
            continue
        if level == 1:
            if tag == TAG_PARA_TEXT:
                current["chars"] = _hwp_chars(payload)
            elif tag == TAG_LINE_SEG:
                current["segs"] = _hwp_segs(payload)
            elif tag == TAG_CTRL_HEADER:
                close_inner()
                inner, cell = None, None
                ctrl = payload[:4][::-1].decode("latin-1")
                current["table"] |= ctrl == "tbl "
                current["shape"] |= ctrl == "gso "
            continue
        if ctrl not in ("tbl ", "gso "):
            continue                     # 머리말·꼬리말·각주 안 글은 본문이 아니다
        if tag == TAG_PICTURE:
            current["picture"] = True
        elif ctrl == "tbl " and tag == TAG_LIST_HEADER and level == 2 and len(payload) >= 12:
            close_inner()
            inner = None
            col, row = struct.unpack_from("<HH", payload, 8)
            cell = (row, col)
        elif tag == TAG_PARA_HEADER and (ctrl == "gso " or level == 2):
            close_inner()
            inner = {"level": level, "chars": [], "segs": [], "cell": cell if ctrl == "tbl " else None}
        elif inner is not None and level == inner["level"] + 1:
            if tag == TAG_PARA_TEXT:
                inner["chars"] = _hwp_chars(payload)
            elif tag == TAG_LINE_SEG:
                inner["segs"] = _hwp_segs(payload)
    close()
    return paras


def read_hwp(path: Path) -> list[list[RawPara]]:
    data = path.read_bytes()
    read_stream, names = read_cfb(data)
    header = read_stream("FileHeader")
    if header is None:
        raise ValueError("HWP FileHeader 스트림이 없음")
    flags = struct.unpack_from("<I", header, 36)[0]
    if flags & 2:
        raise ValueError("암호화된 hwp는 읽을 수 없음")
    names = sorted((n for n in names if n.startswith("BodyText/Section")), key=lambda s: int(s.rsplit("Section", 1)[1]))
    if not names:
        raise ValueError("HWP 본문(BodyText/Section) 스트림이 없음")
    sections = []
    for name in names:
        raw = read_stream(name)
        sections.append(hwp_paragraphs(zlib.decompress(raw, -15) if flags & 1 else raw))
    return sections


# ── hwpx ───────────────────────────────────────────────────────────────


def _xml_segs(paragraph: ET.Element) -> list[Seg]:
    return [Seg(int(s.get("textpos", 0)), int(s.get("vertpos", 0)), int(s.get("vertsize", 0)), int(s.get("spacing", 0)))
            for s in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")]


def _sub_paragraphs(element: ET.Element) -> list[ET.Element]:
    """element 바로 아래 subList의 문단들(더 깊은 표·도형 안 문단은 빼고)."""
    return [p for sub in element.findall(f"{HP}subList") for p in sub.findall(f"{HP}p")]


def hwpx_paragraph(paragraph: ET.Element) -> RawPara:
    para = RawPara(text=para_text(paragraph), segs=_xml_segs(paragraph))
    for run in paragraph.findall(f"{HP}run"):
        for child in run:
            tag = child.tag.replace(HP, "")
            if tag == "tbl":
                para.kind = "table"
                rows: dict[int, list[tuple[str, int]]] = {}
                for cell in (c for tr in child.findall(f"{HP}tr") for c in tr.findall(f"{HP}tc")):
                    address = cell.find(f"{HP}cellAddr")
                    row = int(address.get("rowAddr", 0)) if address is not None else 0
                    own = _sub_paragraphs(cell)
                    text = " ".join(para_text(p) for p in own).strip()
                    rows.setdefault(row, []).append((text, sum(len(_xml_segs(p)) or 1 for p in own) or 1))
                para.rows = [rows[r] for r in sorted(rows)]
            elif tag == "pic" and para.kind != "table":
                para.kind = "picture"
                caption = child.find(f"{HP}caption")
                if caption is not None:
                    para.inner += [(para_text(p), _xml_segs(p)) for p in _sub_paragraphs(caption)]
            elif tag in SHAPES and para.kind == "text":
                para.kind = "shape"
                for holder in child.iter(f"{HP}drawText"):
                    para.inner += [(para_text(p), _xml_segs(p)) for p in _sub_paragraphs(holder)]
    return para


def read_hwpx(path: Path) -> list[list[RawPara]]:
    sections = []
    with zipfile.ZipFile(path) as archive:
        for name in section_names(archive):
            root = ET.fromstring(archive.read(name))
            sections.append([hwpx_paragraph(p) for p in root.findall(f"{HP}p")])
    return sections


# ── 배치 ───────────────────────────────────────────────────────────────

_WIDE = re.compile(r"[ᄀ-ᇿ⺀-꓏가-힣豈-﫿＀-￯\U000f0000-\U0010ffff]")


def text_width(text: str) -> float:
    """한글 1, 영문·숫자·기호 0.55로 센 폭."""
    wide = len(_WIDE.findall(text))
    return wide + 0.55 * (len(text) - wide)


def _chunks(text: str, per_line: float) -> list[tuple[int, int]]:
    """추정용: 폭으로 글을 줄로 자른 (시작, 끝) 목록. 빈 글도 한 줄."""
    spans, start, width = [], 0, 0.0
    for k, char in enumerate(text):
        w = text_width(char)
        if width + w > per_line and k > start:
            spans.append((start, k))
            start, width = k, 0.0
        width += w
    spans.append((start, len(text)))
    return spans


def _pitches(paras: list[RawPara]) -> list[list[float]]:
    """줄마다 차지하는 높이: 같은 쪽 다음 줄까지의 거리(문단 간격 포함), 쪽 마지막 줄이면 줄 높이 + 줄 사이."""
    flat = [(i, k, seg) for i, para in enumerate(paras) for k, seg in enumerate(para.segs)]
    out = [[0.0] * len(para.segs) for para in paras]
    for n, (i, k, seg) in enumerate(flat):
        own = seg.vertsize + seg.spacing
        nxt = flat[n + 1][2].vertpos if n + 1 < len(flat) else None
        out[i][k] = float(nxt - seg.vertpos) if nxt is not None and nxt > seg.vertpos else float(own)
        if out[i][k] < own and seg.vertsize > 0:
            out[i][k] = float(own)   # 다음 줄이 겹쳐 놓인 경우(글 앞 도형 등)에도 줄 높이만큼은 차지한다
    return out


def _measured_blocks(sections: list[list[RawPara]], body: int) -> tuple[list[Block], int]:
    blocks: list[Block] = []
    page, spill = -1, -1
    for paras in sections:
        page = max(page + 1, spill)          # 구역은 새 쪽에서 시작
        last = None
        pitches = _pitches(paras)
        for para, heights in zip(paras, pitches):
            if not para.segs:                # 배치 정보가 없는 문단(드묾): 앞 줄 바로 아래에 한 줄로 둔다
                para.segs = [Seg(0, (last or 0), 0, 0)]
                heights = [0.0]
            first_page, page_top = None, False
            placed = []
            for seg, height in zip(para.segs, heights):
                if last is not None and seg.vertpos < last:
                    page = max(page + 1, spill)
                    page_top = page_top or first_page is None
                if first_page is None:
                    first_page = page
                    page_top = page_top or seg.vertpos == 0 or last is None
                placed.append((page, seg, height))
                last = seg.vertpos
                end = seg.vertpos + height
                if end > body:
                    spill = max(spill, page + math.ceil(end / body) - 1)
            blocks.append(_block(para, placed, first_page, page_top))
    return blocks, max(page, spill) + 1


def _block(para: RawPara, placed: list[tuple[int, Seg, float]], page: int, page_top: bool) -> Block:
    """배치한 줄로 비교 단위와 산정 행을 만든다."""
    p0, s0, _ = placed[0]
    total = sum(h for _, _, h in placed)
    head, full, units, visual = para.text.strip(), para.text, [], 0.0
    if para.kind == "table":
        cells = [c for row in para.rows for c in row]
        head = " ".join(t for t, _ in cells[:2])
        full = " ".join(t for t, _ in cells)
        counts = [max((n for _, n in row), default=1) for row in para.rows] or [1]
        unit_h, offset = total / sum(counts), 0.0
        for row, count in zip(para.rows or [[("", 1)]], counts):
            text = " | ".join(t for t, _ in row)
            units.append(Unit(text, [Line(count, unit_h * count, p0, s0.vertpos + offset, 0, len(text))]))
            offset += unit_h * count
    elif para.kind in ("picture", "shape"):
        texts = [(t, segs) for t, segs in para.inner if t.strip() or segs]
        head = " ".join(t for t, _ in texts).strip()
        full = head
        lines_total = sum(len(segs) or 1 for _, segs in texts)
        if para.kind == "picture":
            # 그림 자리는 시각 자료로 빼고, 캡션 줄만 그 줄 높이로 센다
            caption_h = [float(s.vertsize + s.spacing) for _, segs in texts for s in segs] or [0.0] * lines_total
            visual = max(0.0, total - sum(caption_h))
            unit_h = None
        else:
            unit_h = total / lines_total if lines_total else 0.0
            visual = 0.0 if lines_total else total
        k, offset = 0, 0.0
        for text, segs in texts:
            spans = _spans(text, segs)
            lines = []
            for start, end in spans:
                h = unit_h if unit_h is not None else caption_h[k] if k < len(caption_h) else 0.0
                lines.append(Line(1, h, p0, s0.vertpos + offset, start, end))
                offset += h
                k += 1
            units.append(Unit(text, lines))
    else:
        spans = _spans(para.text, para.segs)
        lines = [Line(1, h, pg, seg.vertpos, start, end) for (pg, seg, h), (start, end) in zip(placed, spans)]
        units.append(Unit(para.text, lines))
    return Block(para.kind, head, full, units, visual, page, page_top, has_caption=bool(head) and para.kind == "picture")


def _spans(text: str, segs: list[Seg]) -> list[tuple[int, int]]:
    if not segs:
        return [(0, len(text))]
    starts = [min(max(s.textpos, 0), len(text)) for s in segs]
    ends = starts[1:] + [len(text)]
    return [(a, max(a, b)) for a, b in zip(starts, ends)]


def _estimated_blocks(sections: list[list[RawPara]], config: VolumeConfig) -> list[Block]:
    per_line, pitch = config.chars_per_line, config.line_pitch
    blocks = []
    for paras in sections:
        for para in paras:
            head, full, units, visual = para.text.strip(), para.text, [], 0.0
            if para.kind == "table":
                cells = [c for row in para.rows for c in row]
                head, full = " ".join(t for t, _ in cells[:2]), " ".join(t for t, _ in cells)
                for row in para.rows:
                    width = per_line / max(1, len(row))
                    count = max((len(_chunks(t, width)) for t, _ in row), default=1)
                    text = " | ".join(t for t, _ in row)
                    units.append(Unit(text, [Line(count, count * pitch, -1, 0, 0, len(text))]))
            elif para.kind in ("picture", "shape"):
                texts = [t for t, _ in para.inner if t.strip()]
                head = full = " ".join(texts).strip()
                units = [Unit(t, [Line(1, pitch, -1, 0, a, b) for a, b in _chunks(t, per_line)]) for t in texts]
                visual = 0.0 if texts or para.kind == "shape" else float(config.body_height) / 3   # 그림 자리(참고값)
            else:
                units.append(Unit(para.text, [Line(1, pitch, -1, 0, a, b) for a, b in _chunks(para.text, per_line)]))
            blocks.append(Block(para.kind, head, full, units, visual, -1, False, has_caption=bool(head) and para.kind == "picture"))
    return blocks


def read_layout(path: Path | str, config: VolumeConfig = DEFAULT_CONFIG) -> Layout:
    """hwp/hwpx 원고 → Layout. 배치 정보가 있는 문단이 절반 미만이면 전체를 추정으로 센다."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"원고 파일이 없습니다: {path.name}")
    fmt = detect_format(path)
    if fmt == "pdf":
        raise ValueError(f"PDF는 분량을 셀 수 없습니다. hwp/hwpx 원고를 올리세요: {path.name}")
    sections = read_hwp(path) if fmt == "hwp" else read_hwpx(path)
    paras = [p for section in sections for p in section]
    if not paras:
        raise ValueError(f"원고에 문단이 없습니다: {path.name}")
    measured = sum(bool(p.segs) for p in paras) * 2 >= len(paras)
    if measured:
        own = Counter(s.vertsize + s.spacing for p in paras if p.kind == "text" and p.text.strip() for s in p.segs)
        pitch = own.most_common(1)[0][0] if own else config.line_pitch
        blocks, pages = _measured_blocks(sections, config.body_height)
    else:
        pitch = config.line_pitch
        blocks, pages = _estimated_blocks(sections, config), 0
    return Layout(path, fmt, measured, blocks, pages, max(1, config.body_height // max(1, pitch)), pitch)
