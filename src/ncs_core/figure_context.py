"""그림 맥락(FigureContext) — 그림이 놓인 자리마다 캡션·출처 줄·AI 활용 줄·본문 참조·앞뒤 문단·위치를 모은다.

그림 태깅(REQ-02-009)과 원고 이미지 검수(REQ-02-005)가 같은 입력으로 쓰는 공통 단계다. 판정은 하지 않는다.
표준 라이브러리만 쓴다. hwpx만 지원한다(hwp는 그림 개체를 읽지 못함 — picture_records가 빈 목록).

학습 번호는 캡션의 그림 번호 N(`[그림 N-M]`)에서 먼저 읽는다 — 본문 구조 파서가 학습 1을 놓치는 원고(앞 구역에 학습 1이
든 최종본)에서도 맞게. 본문 구조로 읽은 학습 번호는 lesson_by_structure에 따로 두어 둘이 다르면 사람이 볼 수 있게 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .manuscript import parse_body, parse_toc, section_presence, unit_regions
from .pictures import CAPTION, CAPTION_AFTER, CAPTION_BEFORE, picture_records
from .source_line import find_ai_marker, find_source_line

LABEL = re.compile(r"\[\s*그림\s*(\d+)\s*-\s*(\d+)\s*\]\s*(.*)")
BEFORE, AFTER = 3, 2          # 앞뒤 문맥 문단 수(설계메모 6장 '그림 중심 조각')
CLIP = 200                    # 문맥 문단 하나의 최대 글자
MAX_REFERENCES = 3
TABLE_WINDOW = 6              # 표 안 그림이면 앞뒤 이 범위의 표 칸 문단을 표 맥락으로


@dataclass(frozen=True)
class FigureContext:
    section: int
    para: int
    bin_id: str | None
    format: str | None
    px: tuple[int, int]
    size_hwp: tuple[int, int]
    mm: tuple[int, int]
    dpi: int | None
    data: bytes = field(repr=False)
    caption: str = ""
    caption_para: int | None = None
    figure_label: str | None = None            # "그림 3-4"
    figure_title: str | None = None
    source_line: str | None = None
    source_para: int | None = None
    ai_marker_line: str | None = None
    ai_marker_para: int | None = None
    references: tuple[str, ...] = ()
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    in_table: bool = False                     # 자료 표의 칸 안 그림(그림 틀 표는 아님)
    in_frame: bool = False                     # 그림·출처·캡션을 담은 그림 틀 표 안 — 문단 사이의 그림으로 본다
    table_context: tuple[str, ...] = ()
    lesson: int | None = None                  # 캡션 번호 N
    lesson_by_structure: int | None = None     # 본문 구조로 읽은 학습(본문 구역만)
    content_no: str | None = None              # "3-2"
    content_title: str | None = None
    region_path: str = ""
    page: int | None = None                    # 인쇄 쪽(출력본 PDF가 있을 때 — 아직 채우지 않음)
    page_estimate: int | None = None


def caption_index(paragraphs: list[str], para: int) -> int | None:
    """caption_near와 같은 순서(그림 아래 → 위)로 찾은 캡션 문단 인덱스."""
    order = list(range(para, min(len(paragraphs), para + CAPTION_AFTER + 1))) + \
        list(range(para - 1, max(-1, para - CAPTION_BEFORE - 1), -1))
    return next((j for j in order if CAPTION.search((paragraphs[j] or "").strip())), None)


def body_structure(document, *, front_section: int = 0, body_section: int = 1) -> dict | None:
    """본문 구조(parse_body·unit_regions) — 엔진 pipeline과 같은 방법. 차례를 못 읽으면 None(위치 없이 계속)."""
    if max(front_section, body_section) >= len(document.sections):
        return None
    sections = [document.sections[front_section], document.sections[body_section]]
    toc = parse_toc(sections)
    if not toc or not toc.get("학습"):
        return None
    images = [(p, name) for s, p, name in document.images if s == body_section]
    presence = section_presence(sections, images, figures=document.section_figures(body_section),
                                tables=document.section_tables(body_section), media_complete=document.format == "hwpx")
    body = parse_body(sections, len(toc["학습"]), cutoff=presence["참고 자료"]["k"],
                      table_paragraphs=document.section_table_paragraphs(body_section),
                      aside_paragraphs=document.section_aside_paragraphs(body_section),
                      styles=document.section_styles(body_section))
    return {"body_section": body_section, "body": body, "units": unit_regions(body)}


def _clip(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= CLIP else text[:CLIP] + "…"


def _place(structure: dict | None, section: int, para: int) -> tuple[int | None, str | None, str | None]:
    """(구조상 학습, 학습 내용 N-M, 학습 내용 제목). 본문 구역이 아니거나 구조가 없으면 None들."""
    if not structure or section != structure["body_section"]:
        return None, None, None
    body = structure["body"]
    lines = body["lines"]
    raw = lambda k: lines[k][0] if k < len(lines) else float("inf")  # noqa: E731 — lines 인덱스 → 원래 문단 인덱스
    lesson = next((item["no"] for item in body["lessons"] if item["raw_span"][0] <= para < item["raw_span"][1]), None)
    for unit in structure["units"]:
        if raw(unit["k0"]) <= para < raw(unit["k1"]):
            return lesson, f"{unit['no']}-{unit['sub']}", unit["text"]
    return lesson, None, None


def figure_contexts(document, *, structure: dict | None = None, records: list[dict] | None = None,
                    lookback: int = 3) -> list[FigureContext]:
    """그림 자리마다 FigureContext(picture_records 순서). structure를 주지 않으면 body_structure로 만든다.

    records: 테스트용 — picture_records 대신 넣는 그림 목록(같은 키).
    """
    if records is None:
        records = picture_records(document)
    if not records:
        return []
    if structure is None:
        structure = body_structure(document)
    out = []
    for r in records:
        s, p = r["section"], r["para"]
        paragraphs = document.sections[s]
        aside = document.section_aside_paragraphs(s) or frozenset()
        in_table_set = document.section_table_paragraphs(s) or frozenset()
        cap_i = caption_index(paragraphs, p)
        caption = (paragraphs[cap_i] or "").strip() if cap_i is not None else ""
        label = LABEL.search(caption)
        src_i = find_source_line(paragraphs, cap_i, lookback=lookback) if cap_i is not None else None
        ai_i = find_ai_marker(paragraphs, cap_i, src_i) if cap_i is not None else None
        own = {i for i in (p, cap_i, src_i, ai_i) if i is not None}
        top, bottom = min(own), max(own)
        before = [paragraphs[i] for i in range(top - 1, -1, -1) if (paragraphs[i] or "").strip() and i not in aside][:BEFORE]
        after = [paragraphs[i] for i in range(bottom + 1, len(paragraphs)) if (paragraphs[i] or "").strip() and i not in aside][:AFTER]
        references: list[str] = []
        if label:
            ref = re.compile(rf"그림\s*{label.group(1)}\s*-\s*{label.group(2)}(?!\d)")
            references = [_clip(t) for i, t in enumerate(paragraphs)
                          if t and i not in own and i not in aside and ref.search(t) and not CAPTION.match(t.strip())][:MAX_REFERENCES]
        # 그림 틀 표: 그림·출처·캡션을 1열 표(최종본은 3행×1열)에 넣어 배치한 것 — 눈에는 문단 사이의 그림이다.
        # 그림부터 캡션까지가 모두 같은 표 문단으로 이어지면 틀로 보고, '표 안의 그림'(자료 표의 칸에 든 그림)과 구별한다.
        in_frame = (p in in_table_set and cap_i is not None and cap_i > p
                    and all(i in in_table_set for i in range(p, cap_i + 1)))
        in_table = p in in_table_set and not in_frame
        table_context =tuple(_clip(paragraphs[i]) for i in range(max(0, p - TABLE_WINDOW), min(len(paragraphs), p + TABLE_WINDOW + 1))
                              if i != p and i in in_table_set and (paragraphs[i] or "").strip() and i not in own) if in_table else ()
        lesson_struct, content_no, content_title = _place(structure, s, p)
        lesson = int(label.group(1)) if label else lesson_struct
        parts = [f"section{s}"]
        if lesson:
            parts.append(f"학습 {lesson}")
        if content_no:
            parts.append(f"{content_no}. {content_title}".strip())
        if label:
            parts.append(f"[그림 {label.group(1)}-{label.group(2)}]")
        else:
            parts.append(f"p{p}")
        out.append(FigureContext(
            section=s, para=p, bin_id=r["bin_id"], format=r["format"], px=tuple(r["px"]), size_hwp=tuple(r["size_hwp"]),
            mm=tuple(r["mm"]), dpi=r["dpi"], data=r["data"],
            caption=caption, caption_para=cap_i,
            figure_label=f"그림 {label.group(1)}-{label.group(2)}" if label else None,
            figure_title=label.group(3).strip() or None if label else None,
            source_line=(paragraphs[src_i] or "").strip() if src_i is not None else None, source_para=src_i,
            ai_marker_line=(paragraphs[ai_i] or "").strip() if ai_i is not None else None, ai_marker_para=ai_i,
            references=tuple(references), before=tuple(_clip(t) for t in reversed(before)), after=tuple(_clip(t) for t in after),
            in_table=in_table, in_frame=in_frame, table_context=table_context,
            lesson=lesson, lesson_by_structure=lesson_struct, content_no=content_no, content_title=content_title,
            region_path=" > ".join(parts),
        ))
    return out
