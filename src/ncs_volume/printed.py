"""출력본(원고를 한글에서 PDF로 저장한 것)에서 쪽을 직접 재기 — 전체 쪽 수, 구성별 쪽 범위, 쪽마다 산정 대상이 차지한 높이.

무엇을 재고 무엇을 계산하는가(결과의 '측정 구분'에 항목별로 적는다)
- 전체 쪽 수: PDF 쪽 수 그대로(측정).
- 구성별 쪽 범위: PDF 본문 줄(본문 띠 안)과 그림 위치를 한글 원고와 같은 구성 나누기(segments.assign)에 넣어 찾는다(측정).
  꼬리 구성의 제목이 글 없는 배너 그림인 것도 같다 — 평가 뒤 쪽 맨 위 그림을 차례 순서대로 다음 꼬리 구성의 시작으로 본다.
- 쪽별 채움 높이(½쪽 규칙): PDF 글자의 y좌표와 표 테두리(사각형)·그림 상자의 y좌표로 잰다(측정).
  쪽 안 산정 대상의 맨 위 ~ 맨 아래 높이에서, 글이 겹치지 않는 그림 자리만 뺀다. 한 줄은 줄 간격(한글 원고의 본문 줄 간격) 높이를 차지한다고 본다.
- 시각 자료 제외: PDF의 그림(이미지 XObject) 상자로 잰다(측정). 선으로 그린 도형·차트, 표 안 그림 중 글이 겹치는 것은 가리지 못한다.
- 남은 행(½쪽 미만인 쪽): PDF에는 빈 줄·표 행 구조가 없으므로 그 쪽 채움 높이 ÷ 줄 간격으로 계산한다(계산).
- 행 합계·변경 행: 한글 줄 배치(PDF로는 바뀐 행을 가릴 수 없다).
PDF 글·쪽 번호·모듈 코드 읽기는 ncs_core.pdf.load_pdf, 좌표 읽기만 여기서 pypdf로 한다(선택 설치, 없으면 PdfUnavailable).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ncs_core.module_code import CODE_IN_NAME
from ncs_core.pdf import LINE_TOLERANCE, PdfUnavailable, load_pdf

from .config import PT_PER_MM, PT_PER_UNIT, SEGMENTS, VolumeConfig, round_half_up
from .layout import Block, Layout
from .segments import assign, norm

UNDECIDED = "판단불가"
_NAV = re.compile(r"^학습\s*(\d+)\s+\S")
_BANNER = re.compile(r"^(필요\s*지식|수행\s*내용)\s*/")
_WS = re.compile(r"\s+")
MIN_SAME_TEXT = 0.3          # 모듈 코드를 모를 때, 한글 원고 문단 첫머리가 PDF에서 이 비율 미만으로 보이면 다른 원고로 본다


@dataclass
class Item:
    """출력본 한 쪽의 본문 띠 안 요소. top·bottom은 PDF 좌표(pt, 아래가 0)."""

    kind: str                # text | picture | rect
    top: float
    bottom: float
    text: str = ""
    segment: str = ""


@dataclass
class PrintedPage:
    index: int               # 물리 쪽(0부터)
    folio: str | None        # 인쇄된 쪽 번호
    body_top: float
    body_bottom: float
    items: list[Item] = field(default_factory=list)

    @property
    def body(self) -> float:
        return self.body_top - self.body_bottom


@dataclass
class Printed:
    path: Path
    pages: list[PrintedPage]
    module_code: str | None


# ── 읽기 ───────────────────────────────────────────────────────────────


def _clean(text: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFC", text.replace("\x00", ""))).strip()


def _page_items(page, top: float, bottom: float) -> list[Item]:
    """pypdf 쪽 하나 → 본문 띠 안의 글 줄·그림·사각형. 쪽 회전은 다루지 않는다(학습모듈 본문은 세로 쪽)."""
    chunks: list[tuple[float, float, str, float]] = []
    pictures: list[tuple[float, float, float, float]] = []
    rects: list[tuple[float, float, float, float]] = []
    height = float(page.mediabox.height) or 1.0
    try:
        xobjects = page["/Resources"]["/XObject"]
    except (KeyError, TypeError):
        xobjects = {}

    def on_text(text, cm, tm, font_dict, font_size):  # noqa: ARG001 — pypdf 콜백 서명
        if text and text.strip():
            y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            size = abs(font_size * tm[3] * cm[3]) or abs(font_size) or 10.0
            chunks.append((y, x, text, size))

    def on_operator(op, args, cm, tm):  # noqa: ARG001
        if op == b"Do" and args:
            try:
                is_image = xobjects[args[0]]["/Subtype"] == "/Image"
            except (KeyError, TypeError):
                is_image = False
            if is_image:
                y0, y1 = sorted((cm[5], cm[5] + cm[3]))
                x0, x1 = sorted((cm[4], cm[4] + cm[0]))
                pictures.append((y0, y1, x0, x1))
        elif op == b"re" and len(args) == 4:
            x, y, w, h = (float(a) for a in args)
            y0, y1 = sorted((cm[3] * y + cm[5], cm[3] * (y + h) + cm[5]))
            x0, x1 = sorted((cm[0] * x + cm[4], cm[0] * (x + w) + cm[4]))
            if y1 - y0 < 0.9 * height and x1 - x0 > 5:
                rects.append((y0, y1, x0, x1))

    page.extract_text(visitor_text=on_text, visitor_operand_before=on_operator)
    items: list[Item] = []
    chunks.sort(key=lambda c: (-c[0], c[1]))
    lines: list[list] = []
    for y, x, text, size in chunks:
        if lines and abs(lines[-1][0] - y) <= LINE_TOLERANCE:
            lines[-1][1].append((x, text))
            lines[-1][2] = max(lines[-1][2], size)
        else:
            lines.append([y, [(x, text)], size])
    for y, parts, size in lines:
        text = _clean("".join(t for _, t in sorted(parts, key=lambda p: p[0])))
        if text and bottom <= y <= top:
            items.append(Item("text", min(top, y + 0.85 * size), max(bottom, y - 0.25 * size), text))
    for y0, y1, _x0, _x1 in pictures:
        y0, y1 = max(y0, bottom), min(y1, top)
        if y1 - y0 >= 1:
            items.append(Item("picture", y1, y0))
    for y0, y1, x0, x1 in rects:
        # 그림 테두리·자르기 사각형은 그림과 같은 자리라 뺀다
        if any(p0 - 4 <= y0 and y1 <= p1 + 4 and x0 < px1 and px0 < x1 for p0, p1, px0, px1 in pictures):
            continue
        y0, y1 = max(y0, bottom), min(y1, top)
        if y1 > y0:
            items.append(Item("rect", y1, y0))
    items.sort(key=lambda item: -item.top)
    return items


def read_printed(path: Path | str, config: VolumeConfig) -> Printed:
    """출력본 PDF → Printed. PDF가 아니거나 글을 못 뽑으면 ValueError, pypdf가 없으면 PdfUnavailable."""
    path = Path(path)
    document = load_pdf(path)                 # PDF 확인·암호·스캔본 판별·쪽 번호·모듈 코드
    try:
        from pypdf import PdfReader
    except ImportError:                       # load_pdf가 이미 걸렀지만 함께 둔다
        raise PdfUnavailable("PDF 읽기에는 pypdf가 필요합니다: pip install -e \".[pdf]\"") from None
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    pages = []
    for raw, page in zip(reader.pages, document.pages):
        height = float(raw.mediabox.height) or 1.0
        top, bottom = height - config.print_top_mm * PT_PER_MM, config.print_bottom_mm * PT_PER_MM
        pages.append(PrintedPage(page.index, page.folio, top, bottom, _page_items(raw, top, bottom)))
    return Printed(path, pages, document.module_code)


# ── 구성 나누기 ─────────────────────────────────────────────────────────


def assign_pages(printed: Printed) -> list[str]:
    """출력본 요소에 구성 이름을 붙이고 찾은 구성 이름 순서를 돌려준다. 한글 원고와 같은 segments.assign을 쓴다."""
    blocks: list[Block] = []
    owners: list[Item] = []
    for page in printed.pages:
        navigator = {int(m.group(1)) for item in page.items if item.kind == "text" and (m := _NAV.match(item.text))}
        nav_text = " ".join(item.text for item in page.items if item.kind == "text" and _NAV.match(item.text))
        first = True
        for item in page.items:
            if item.kind == "rect":
                continue
            if item.kind == "picture":
                block = Block("picture", "", "", [], 0.0, page.index, first)
            elif len(navigator) >= 2 and _NAV.match(item.text):
                block = Block("table", item.text, nav_text, [], 0.0, page.index, first)   # 내비게이터(학습 묶음 표)
            elif _BANNER.match(item.text) or item.text.startswith("ISBN"):
                block = Block("table", item.text, item.text, [], 0.0, page.index, first)  # 필요 지식·수행 내용 배너, 판권 표
            else:
                block = Block("text", item.text, item.text, [], 0.0, page.index, first)
            blocks.append(block)
            owners.append(item)
            first = False
    names, found = assign(blocks)
    for item, name in zip(owners, names):
        item.segment = name
    state = "표지"
    for page in printed.pages:               # 사각형은 바로 위 요소의 구성을 따른다
        for item in page.items:
            if item.kind == "rect":
                item.segment = state
            state = item.segment or state
    return found


# ── 채움 높이 ───────────────────────────────────────────────────────────


def _union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for low, high in sorted(intervals):
        if out and low <= out[-1][1]:
            out[-1][1] = max(out[-1][1], high)
        else:
            out.append([low, high])
    return [(a, b) for a, b in out]


def _length(intervals: list[tuple[float, float]]) -> float:
    return sum(b - a for a, b in intervals)


def _minus(base: list[tuple[float, float]], cut: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for low, high in base:
        pieces = [(low, high)]
        for c0, c1 in cut:
            pieces = [p for a, b in pieces for p in ((a, min(b, c0)), (max(a, c1), b)) if p[1] - p[0] > 0]
        out += pieces
    return out


def fill(items: list[Item], pitch: float) -> tuple[float, float]:
    """(산정 높이, 뺀 그림 높이). 맨 위~맨 아래 높이에서 글이 겹치지 않는 그림 자리를 뺀다. 한 줄은 줄 간격만큼 아래로 차지한다."""
    if not items:
        return 0.0, 0.0
    spans = [(min(i.bottom, i.top - pitch), i.top) if i.kind == "text" else (i.bottom, i.top) for i in items]
    low, high = min(a for a, _ in spans), max(b for _, b in spans)
    texts = _union([s for s, i in zip(spans, items) if i.kind == "text"])
    pictures = _union([(max(low, a), min(high, b)) for (a, b), i in zip(spans, items) if i.kind == "picture"])
    visual = _length(_minus(pictures, texts))
    return max(0.0, high - low - visual), visual


# ── 같은 원고인가 ───────────────────────────────────────────────────────


def manuscript_code(layout: Layout) -> str | None:
    match = CODE_IN_NAME.search(layout.path.name)
    if match:
        return match.group(0)
    for block in layout.blocks[:40]:
        match = CODE_IN_NAME.search(block.full)
        if match:
            return match.group(0)
    return None


def same_text_ratio(layout: Layout, printed: Printed, sample: int = 300) -> float | None:
    """한글 원고 문단 첫머리(글자 12자)가 PDF 본문에 보이는 비율. 비교할 문단이 없으면 None."""
    probes = [key[:12] for block in layout.blocks for unit in block.units if len(key := norm(unit.text)) >= 12]
    if not probes:
        return None
    step = max(1, len(probes) // sample)
    probes = probes[::step]
    haystack = "".join(norm(item.text) for page in printed.pages for item in page.items if item.kind == "text")
    return sum(probe in haystack for probe in probes) / len(probes)


# ── 산정 ───────────────────────────────────────────────────────────────


def _span(numbers: list) -> str:
    numbers = [n for n in numbers if n is not None]
    return f"{numbers[0]}~{numbers[-1]}" if numbers else ""


def measure_printed(path: Path | str, layout: Layout, hwp_rows: list[dict], hwp_total: dict, config: VolumeConfig) -> dict:
    """출력본으로 잰 산정표. '사용'이 False면 판단불가 사유와 함께 돌려주고 산정에는 쓰지 않는다."""
    printed = read_printed(path, config)
    code, print_code = manuscript_code(layout), printed.module_code
    ratio = same_text_ratio(layout, printed)
    out: dict = {
        "파일": Path(path).name, "사용": False, "사유": None, "모듈 코드": print_code, "원고 모듈 코드": code,
        "같은 글 비율": None if ratio is None else f"{ratio * 100:.0f}%",
        "전체 쪽 수": len(printed.pages), "한글 물리 쪽 수": layout.pages if layout.measured else None,
        "쪽 수 차이": (len(printed.pages) - layout.pages) if layout.measured else None,
        "측정 구분": [], "구성": [], "합계": None, "쪽별": [], "알림": [],
    }
    if code and print_code and code != print_code:
        out["사유"] = f"{UNDECIDED}: 출력본 「{print_code}」, 원고 「{code}」 — 다른 원고의 출력본이라 쪽을 재지 않음"
        return out
    if not (code and print_code) and ratio is not None and ratio < MIN_SAME_TEXT:
        out["사유"] = (f"{UNDECIDED}: 원고 문단 첫머리 중 출력본에 보이는 것이 {ratio * 100:.0f}%뿐 — "
                      "다른 원고(또는 다른 판)의 출력본으로 보여 쪽을 재지 않음")
        return out
    found = assign_pages(printed)
    if not any(name.startswith("학습 —") for name in found):
        out["사유"] = f"{UNDECIDED}: 출력본에서 학습(내비게이터·필요 지식) 제목을 찾지 못해 구성별 쪽을 나눌 수 없음"
        return out
    if ratio is not None and ratio < MIN_SAME_TEXT:
        out["알림"].append(f"모듈 코드는 같지만 원고 문단 첫머리 중 출력본에 보이는 것이 {ratio * 100:.0f}%뿐입니다 — 최종 원고의 출력본인지 확인하세요.")
    if out["쪽 수 차이"]:
        out["알림"].append(f"출력본 {len(printed.pages)}쪽, 한글 줄 배치 {layout.pages}쪽 — 쪽 수가 {abs(out['쪽 수 차이'])}쪽 "
                          f"{'많습니다' if out['쪽 수 차이'] > 0 else '적습니다'}. 산정에는 출력본 값을 씁니다.")

    pitch = layout.pitch * PT_PER_UNIT
    lpp = layout.lines_per_page
    full_pages, rest, total_fill, visual_total = [], 0.0, 0.0, 0.0
    by_segment: dict[str, dict] = {}
    for page in printed.pages:
        counted = [i for i in page.items if config.counted(i.segment)]
        height, visual = fill(counted, pitch)
        height = min(height, page.body)
        ratio_page = height / page.body if page.body else 0.0
        is_full = bool(counted) and height >= config.half_page * page.body
        if is_full:
            full_pages.append(page.index)
        else:
            rest += height
        total_fill += height / page.body if page.body else 0.0
        visual_total += visual / page.body if page.body else 0.0
        names = list(dict.fromkeys(i.segment for i in page.items if i.segment))
        out["쪽별"].append({"쪽": page.index + 1, "인쇄 쪽": page.folio, "구성": " · ".join(names),
                           "채움": round(ratio_page, 2), "인정": "1쪽" if is_full else ("행" if counted else "제외")})
        for name in names:
            own = [i for i in page.items if i.segment == name]
            seg_height, seg_visual = fill(own, pitch)
            entry = by_segment.setdefault(name, {"쪽": [], "인쇄 쪽": [], "높이": 0.0, "그림": 0.0})
            entry["쪽"].append(page.index + 1)
            entry["인쇄 쪽"].append(page.folio)
            entry["높이"] += seg_height / page.body
            entry["그림"] += seg_visual / page.body
    rest_lines = round(rest / pitch) if pitch else 0
    hwp_by = {row["구성"]: row for row in hwp_rows}
    for name, counted in SEGMENTS:
        entry, hwp = by_segment.get(name), hwp_by.get(name)
        if entry is None and hwp is None:
            continue
        pdf_pages = round(entry["높이"], 2) if entry else None
        hwp_pages = hwp["쪽 환산"] if hwp else None
        out["구성"].append({
            "구성": name, "반영": config.counted(name),
            "출력본 쪽": _span(entry["쪽"]) if entry else "", "인쇄 쪽": _span(entry["인쇄 쪽"]) if entry else "",
            "쪽 수": len(entry["쪽"]) if entry else 0,
            "쪽 환산(출력본)": pdf_pages, "쪽 환산(한글)": hwp_pages,
            "차이": round(pdf_pages - hwp_pages, 2) if pdf_pages is not None and hwp_pages is not None else None,
            "한글 물리 쪽": hwp["물리 쪽"] if hwp else "",
            "시각 자료 제외(쪽)": round(entry["그림"], 2) if entry else None,
        })
    missing = [name for name, _ in SEGMENTS if config.counted(name) and name in hwp_by and name not in by_segment]
    extra = [name for name, _ in SEGMENTS if config.counted(name) and name in by_segment and name not in hwp_by]
    if missing:
        out["알림"].append("한글 원고에는 있으나 출력본에서 찾지 못한 구성: " + ", ".join(missing))
    if extra:
        out["알림"].append("출력본에서만 찾은 구성(한글 원고에서는 제목을 읽지 못함): " + ", ".join(extra))
    entry = len(full_pages) + round_half_up(rest_lines / lpp)
    out["합계"] = {"쪽": len(full_pages), "행": rest_lines, "기입 분량": entry, "쪽 환산": round(total_fill, 2),
                  "시각 자료 제외(쪽)": round(visual_total, 2),
                  "한글 계산 기입 분량": hwp_total["기입 분량"], "차이": entry - hwp_total["기입 분량"]}
    out["측정 구분"] = [
        {"항목": "전체 쪽 수", "방법": "측정", "설명": "출력본 PDF의 쪽 수"},
        {"항목": "구성별 쪽 범위", "방법": "측정", "설명": "출력본 본문 줄·그림 위치로 구성 제목(배너 그림 포함)이 시작하는 쪽"},
        {"항목": "쪽별 채움 높이(½쪽 규칙)", "방법": "측정",
         "설명": f"PDF 글자·표 테두리·그림의 y좌표 — 본문 띠 {config.print_top_mm:g}㎜~{config.print_bottom_mm:g}㎜ 안, 한 줄 = {pitch:g}pt"},
        {"항목": "시각 자료 제외", "방법": "측정", "설명": "PDF 그림(이미지) 상자 중 글과 겹치지 않는 높이. 선으로 그린 도형·차트는 가리지 못함"},
        {"항목": "남은 행(½쪽 미만인 쪽)", "방법": "계산",
         "설명": f"그 쪽들의 채움 높이 합 ÷ 줄 간격 {pitch:g}pt(한글 원고 본문 줄 간격) — PDF에는 빈 줄·표 행 구조가 없음"},
        {"항목": "쪽당 행 수", "방법": "계산", "설명": f"본문 높이 ÷ 한글 원고 본문 줄 간격 = {lpp}행"},
        {"항목": "행 합계·변경 분량", "방법": "한글 줄 배치" if layout.measured else "추정",
         "설명": "PDF로는 행 구조와 바뀐 행을 가릴 수 없어 한글 원고 값을 씀"},
    ]
    out["사용"] = True
    return out
