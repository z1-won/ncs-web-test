"""PDF 학습모듈 → 그림 자리가 든 Document(009 태깅용). 규칙만, 판정 없음.

hwp·hwpx와 달리 PDF에는 문단·표 구조가 없다. 그래서 쪽마다 글자 줄과 그림(이미지 XObject)을 y좌표로 위에서 아래로 늘어놓고,
그림 자리에 빈 문단을 하나씩 끼워 넣어 '문단 목록 + 그림 자리'를 만든다. 그러면 hwpx와 같은 figure_contexts가
그림 아래·위의 '[그림 N-M]' 캡션, 출처 줄, AI 활용 줄, 앞뒤 글을 그대로 찾는다.

- 쪽: 그림이 놓인 물리 쪽의 인쇄 쪽 번호(ncs_core.pdf의 쪽 번호 읽기와 같음). PDF만 쪽을 바로 준다.
- 머리말·꼬리말 띠(위·아래 8 %)의 글은 뺀다(학습명이 매 쪽 반복되므로). 캡션은 띠 안이라도 둔다.
- 표 안 그림·글상자는 구분하지 못한다(PDF에 그런 정보가 없음).
- 쪽 전체를 덮는 그림(표지 배경)과 아주 작은 그림(아이콘)은 그림 자리로 넣지 않는다.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .documents import Document, normalize_sections, toc_title_index
from .pdf import _CAPTION, BAND, _clean, _group_lines, is_pdf, read_folio

PT_TO_HWPUNIT = 100              # 1pt = 1/72인치, 1 HWPUNIT = 1/7200인치
MIN_SIDE_PT = 20                 # 이보다 작은 그림(아이콘·글머리 기호)은 뺀다
FULL_PAGE = 0.9                  # 쪽 가로·세로의 90 % 이상을 덮는 그림은 표지 배경
NAVIGATOR = re.compile(r"^학\s*습\s*1(?!\s*\.)(?:\s|$)")   # 본문 내비게이터 — PDF에서는 '학습 1 요구사항 분석하기'처럼 학습명과 한 줄
SOURCE_HEAD = re.compile(r"^\s*출\s*처\s*[:：]")
STOP = re.compile(r"^\s*[\[〔<〈]\s*(그림|표)\s*\d|^\s*출\s*처\s*[:：]|활용하여\s*(생성|수정\s*보완)\s*함")
WRAP_GAP = 18                    # pt. 출처 줄이 길어 다음 줄로 넘어간 것으로 보는 줄 간격(본문 10pt 글자의 줄 간격이 15~16pt)
SIDE_BY_SIDE = re.compile(r"(?<=\S)\s*(?=[\[〔]\s*그림\s*\d+\s*-\s*\d+\s*[\]〕]|출\s*처\s*[:：])")   # 나란히 놓인 두 그림의 캡션·출처가 한 줄로 붙음


def load_pdf_figures(path) -> tuple[Document, dict[str, dict]]:
    """(Document, {그림 id: {'page': 물리 쪽(1부터), 'folio': 인쇄 쪽, 'folio_source'}}). 그림 파일은 Document.binaries[id]['data']."""
    path = Path(path)
    if not is_pdf(path):
        raise ValueError(f"PDF 파일이 아닙니다: {path.name}")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("PDF 읽기에는 pypdf가 필요합니다: pip install -e \".[pdf]\"") from None
    reader = PdfReader(str(path))
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise ValueError(f"암호가 걸린 PDF는 읽을 수 없습니다: {path.name}")
    paragraphs: list[str] = []
    pictures, figures, binaries, where = [], [], {}, {}
    folios = []
    for index, page in enumerate(reader.pages):
        lines, images, bands = _read(page)
        folio = read_folio(bands["footer"]) or read_folio(bands["header"])
        folios.append(folio)
        for y, kind, value in sorted(lines + images, key=lambda e: -e[0]):
            if kind == "text":
                paragraphs.append(value)
                continue
            name, data, w, h = value
            key = f"p{index + 1}-{name.strip('/')}"
            pictures.append((0, len(paragraphs), key))
            figures.append((0, len(paragraphs), "", round(w * PT_TO_HWPUNIT), round(h * PT_TO_HWPUNIT)))
            binaries[key] = {"href": None, "bytes": len(data), "data": data}
            where[key] = {"page": index + 1, "folio": folio}
            paragraphs.append("")
    # 못 읽은 쪽 번호는 읽은 쪽들의 차이(다수결)로 채운다 — ncs_core.pdf와 같은 방식
    offsets = Counter(int(f) - i for i, f in enumerate(folios) if f and f.isdigit())
    offset = offsets.most_common(1)[0][0] if offsets else None
    for info in where.values():
        info["folio_source"] = "읽음" if info["folio"] else None
        if info["folio"] is None and offset is not None and info["page"] - 1 + offset >= 1:
            info["folio"], info["folio_source"] = str(info["page"] - 1 + offset), "추정"
    if not any(paragraphs):
        raise ValueError(f"글자를 추출할 수 없는 PDF입니다(스캔본이거나 글꼴 매핑이 없음): {path.name}")
    at = _body_start(paragraphs)
    if at is None:                     # 본문 시작을 못 찾으면 공통 규칙(normalize_sections)에 맡긴다
        document = Document(path, "pdf", [paragraphs], figures=figures, pictures=pictures, binaries=binaries)
        return normalize_sections(document), where

    def move(p):
        return (0, p) if p < at else (1, p - at)

    document = Document(path, "pdf", [paragraphs[:at], paragraphs[at:]],
                        figures=[(*move(p), n, w, h) for _s, p, n, w, h in figures],
                        pictures=[(*move(p), b) for _s, p, b in pictures], binaries=binaries,
                        layout={"결과": "나눔", "설명": f"PDF {at}번째 줄(차례 뒤 첫 '학습 1' 내비게이터)에서 본문 시작", "원래 구역 수": 1})
    return document, where


def _body_start(paragraphs: list[str]) -> int | None:
    """차례 뒤 첫 '학습 1 …' 내비게이터 줄. 차례 안의 '학습 1. …' 줄은 건너뛴다."""
    toc = toc_title_index(paragraphs)
    if toc is None:
        return None
    return next((i for i in range(toc + 1, len(paragraphs)) if NAVIGATOR.match(paragraphs[i])), None)


def _read(page) -> tuple[list, list, dict]:
    """한 쪽 → (본문 줄 [(y, 'text', 글)], 그림 [(y 위쪽, 'image', (이름, 파일, 가로pt, 세로pt))], 띠 {'header','footer'})."""
    height = float(page.mediabox.height) or 1.0
    width = float(page.mediabox.width) or 1.0
    chunks, placed = [], []

    def text(value, cm, tm, font_dict, font_size):  # noqa: ARG001 — pypdf 콜백 서명
        if value and value.strip():
            # 글자 자리(tm)를 쪽 좌표로: 한글 PDF는 cm에 위아래 뒤집기(d<0)를 넣고 tm을 그 안의 좌표로 쓴다
            x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            chunks.append((y, x, value))

    def operand(op, args, cm, tm):  # noqa: ARG001
        if op == b"Do" and args:
            placed.append((str(args[0]), [float(v) for v in cm]))

    page.extract_text(visitor_text=text, visitor_operand_before=operand)
    lines, bands = [], {"header": [], "footer": []}
    for y, line in _group_lines(chunks):
        frac = y / height
        zone = "header" if frac >= 1 - BAND else "footer" if frac <= BAND else "body"
        if zone == "body" or _CAPTION.match(line):
            for part in SIDE_BY_SIDE.split(line):
                part = _clean(part)
                if not part:
                    continue
                last = lines[-1] if lines else None
                # 넘어간 출처 줄을 앞 줄에 붙인다 — 그림 하나의 출처는 한 문단이어야 figure_contexts가 통째로 읽는다
                if (last and SOURCE_HEAD.match(last[2]) and 0 < last[3] - y <= WRAP_GAP and not STOP.search(part)):
                    lines[-1] = (last[0], "text", f"{last[2]} {part}", y)
                    continue
                lines.append((y, "text", part, y))
        else:
            bands[zone].append(line)
    images = []
    lines = [(y, kind, text) for y, kind, text, _bottom in lines]
    for name, cm in placed:
        w, h = abs(cm[0]), abs(cm[3])
        if w < MIN_SIDE_PT or h < MIN_SIDE_PT or (w >= width * FULL_PAGE and h >= height * FULL_PAGE):
            continue
        try:
            data = page.images[name].data
        except Exception:  # noqa: BLE001 — 폼 XObject·읽지 못하는 그림은 건너뜀
            continue
        top = cm[5] + h
        images.append((top, "image", (name, data, w, h)))
    return lines, images, bands
