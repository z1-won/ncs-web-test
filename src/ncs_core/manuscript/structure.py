"""원고의 본문 경계를 탐지하고 물리 구역을 앞부분·본문으로 정규화한다. 검수 판정과 파일 I/O는 하지 않는다."""

import re
from dataclasses import dataclass

from ..documents import Document

BODY_START_STYLE = re.compile(r"^큰학습")                 # 내비게이터(학습 N 큰 제목)의 문단 스타일
BODY_START_TEXT = re.compile(r"^학\s*습\s*1$")           # 스타일이 없을 때: 개요 뒤 첫 '학습 1' 줄
FRONT_END_TEXT = re.compile(r"^(핵심\s*용어|학습\s*모듈의\s*내용\s*체계)")
TOC_TITLE = re.compile(r"^차\s*례$")
TOC_LESSON_LINE = re.compile(r"^학습\s*\d+\.\s*\S")   # 차례 안의 '학습 1. 명' 줄
TOC_LOOKAHEAD = 60                                      # 차례 제목 뒤 이 범위 안에 '학습 N.' 줄이 있어야 진짜 차례


def toc_title_index(paragraphs: list[str]) -> int | None:
    """진짜 차례 제목 줄의 인덱스 — '차례' 뒤 TOC_LOOKAHEAD 문단 안에 '학습 N.' 줄이 따르는 것.

    원고에 따라 '차례' 제목이 두 번 나온다(앞 구역에 자동 차례 필드가 깨진 채 남은 경우: '차 례' 뒤에 쪽수 숫자만 있음).
    그런 가짜 차례를 고르면 학습명을 읽지 못해 차례·개요·필요 지식·기타 엔진이 모두 실패하므로, 학습 줄이 따르는 차례를 우선한다.
    그런 것이 없으면 첫 '차례'(없으면 None).
    """
    titles = [i for i, t in enumerate(paragraphs) if TOC_TITLE.match(t)]
    for n, i in enumerate(titles):
        # 다음 '차례' 제목 전까지만 본다 — 가짜 차례가 진짜 차례의 학습 줄을 제 것으로 셈하지 않게
        stop = min(i + 1 + TOC_LOOKAHEAD, titles[n + 1] if n + 1 < len(titles) else len(paragraphs))
        if any(TOC_LESSON_LINE.match(t) for t in paragraphs[i + 1:stop]):
            return i
    return titles[0] if titles else None


BODY_LESSON = re.compile(r"^학\s*습\s*(\d+)$")
SUB_HEADING = re.compile(r"^(\d+)-(\d+)\.\s*(.*)$")
GOAL_LABEL = re.compile(r"^학\s*습\s*목\s*표$")
CONTENT_LABEL = re.compile(r"^(필요\s*지식|수행\s*내용)$")
CONTEXT_LIMIT = 80


@dataclass(frozen=True)
class BodyBoundary:
    """원본 구역·문단 위치와 채택 근거. 찾지 못한 경계는 None으로 표현한다."""

    section: int
    paragraph: int
    evidence: tuple[str, ...]


def _body_candidate(document: Document, section: int) -> BodyBoundary | None:
    """알려진 양식 단서 또는 학습 제목·하위 제목·목표/내용의 조합으로 경계를 찾는다."""
    paragraphs = document.sections[section]
    styles = document.section_styles(section)
    aside = document.section_aside_paragraphs(section) or frozenset()
    in_table = document.section_table_paragraphs(section) or frozenset()
    # 본문은 차례·개요(핵심 용어/내용 체계) 뒤에 온다. 표지에도 큰학습 스타일 문단이 있을 수 있어 그 앞은 보지 않는다.
    toc = toc_title_index(paragraphs)
    toc = -1 if toc is None else toc
    front_end = next((i for i, t in enumerate(paragraphs) if FRONT_END_TEXT.match(t)), None)
    after = max(toc, front_end if front_end is not None else -1)
    for index in range(after + 1, len(paragraphs)):
        if index in aside or index in in_table:
            continue
        style = styles[index] if styles and index < len(styles) else ""
        # 앞부분을 확인한 경우에만 기존 스타일 단독 인식을 유지한다.
        if after >= 0 and style and BODY_START_STYLE.match(style):
            return BodyBoundary(section, index, ("앞부분 뒤 큰학습 스타일",))
        if front_end is not None and BODY_START_TEXT.match(paragraphs[index]):
            return BodyBoundary(section, index, ("개요 종료 뒤 학습 1",))
        if not BODY_LESSON.fullmatch(paragraphs[index]):
            continue
        stop = min(index + 1 + CONTEXT_LIMIT, len(paragraphs))
        following = [(pos, paragraphs[pos]) for pos in range(index + 1, stop) if pos not in aside]
        # 내비게이터에는 여러 학습 번호가 나올 수 있다. 첫 하위 제목으로 현재 학습을 찾는다.
        sub = next(((pos, match) for pos, text in following
                    if pos not in in_table and (match := SUB_HEADING.fullmatch(text))
                    and not re.search(r"\s\d+$", text)), None)
        if sub is None:
            continue
        sub_index, sub_match = sub
        nav_numbers = {int(match.group(1)) for pos in range(index, sub_index)
                       if pos not in aside and pos not in in_table
                       and (match := BODY_LESSON.fullmatch(paragraphs[pos]))}
        if int(sub_match.group(1)) not in nav_numbers:
            continue
        # 다음 학습·하위 제목·평가의 목표를 현재 제목의 근거로 빌리지 않는다.
        stop = next((pos for pos, text in following if pos > sub_index
                     and (BODY_LESSON.fullmatch(text) or SUB_HEADING.fullmatch(text)
                          or re.fullmatch(r"평\s*가", text))), stop)
        context = [text for pos, text in following if sub_index < pos < stop]
        has_goal = any(GOAL_LABEL.fullmatch(text) for text in context)
        has_content = any(CONTENT_LABEL.fullmatch(text) for text in context)
        table_goal = any(
            sub_index < table["paragraph"] < stop and table["paragraph"] not in aside
            and any(GOAL_LABEL.fullmatch(text) for text in table["cells"].values())
            for table in document.section_tables(section)
        )
        if has_goal or has_content or table_goal:
            evidence = ("학습 번호", "번호가 연결되는 하위 제목",
                        "목표 표" if table_goal else "학습 목표" if has_goal else "본문 내용 표식")
            return BodyBoundary(section, index, evidence)
    return None


def body_start(document: Document, section: int = 0) -> int | None:
    """해당 구역의 본문 시작. 근거가 부족하거나 구역이 없으면 None."""
    if not 0 <= section < len(document.sections):
        return None
    boundary = _body_candidate(document, section)
    return boundary.paragraph if boundary else None


def toc_section(document: "Document") -> int | None:
    """진짜 차례('학습 N.' 줄이 따르는 차례 제목)가 있는 첫 구역. 그런 구역이 없으면 '차례' 제목이 있는 첫 구역."""
    fallback = None
    for index, paragraphs in enumerate(document.sections):
        found = toc_title_index(paragraphs)
        if found is None:
            continue
        following = paragraphs[found + 1:found + 1 + TOC_LOOKAHEAD]
        if any(TOC_LESSON_LINE.match(t) for t in following):
            return index
        if fallback is None:
            fallback = index
    return fallback


def detect_body_boundary(document: Document) -> BodyBoundary | None:
    """차례가 있는 구역부터 전체 구역을 탐색한다. 근거 부족 시 경계를 만들지 않는다."""
    toc = toc_section(document)
    start = toc if toc is not None else 0
    for section in range(start, len(document.sections)):
        boundary = _body_candidate(document, section)
        if boundary is not None:
            return boundary
        # 기존의 분리된 앞부분/본문 양식 호환: 차례 다음 구역의 첫 유효 문단.
        if toc is not None and section == toc + 1:
            aside = document.section_aside_paragraphs(section) or frozenset()
            in_table = document.section_table_paragraphs(section) or frozenset()
            first = next((index for index, text in enumerate(document.sections[section])
                          if text and index not in aside and index not in in_table), None)
            if first is not None and BODY_START_TEXT.fullmatch(document.sections[section][first]):
                return BodyBoundary(section, first, ("차례 다음 구역 첫 학습 1",))
    return None


def normalize_sections(document: Document) -> Document:
    """탐지 경계 앞을 구역 0, 뒤를 구역 1로 합치고 문단에 연결된 모든 메타데이터를 옮긴다.

    원문은 수정하지 않는다. 경계가 불명확하면 원본을 유지한다.
    여러 물리 구역에 나뉜 본문도 하나로 합쳐 기존 엔진이 전체 본문을 읽도록 한다.
    """
    boundary = detect_body_boundary(document)
    if boundary is None:
        return document
    sections = document.sections
    offsets = []
    total = 0
    for paragraphs in sections:
        offsets.append(total)
        total += len(paragraphs)
    cut = offsets[boundary.section] + boundary.paragraph
    if cut == 0 or cut == total:
        return document  # 앞부분 없는 문서는 기존 엔진의 두 구역 계약으로 변환하지 않는다.
    if len(sections) == 2 and cut == len(sections[0]):
        return document
    new_count = 2

    def move(section: int, paragraph: int) -> tuple[int, int]:
        position = offsets[section] + paragraph
        return (0, position) if position < cut else (1, position - cut)

    def move_lists(values):
        if values is None:
            return None
        out = [[] for _ in range(new_count)]
        for s, items in enumerate(values):
            for p, item in enumerate(items):
                out[move(s, p)[0]].append(item)
        return out

    def move_sets(values):
        if values is None:
            return None
        out = [set() for _ in range(new_count)]
        for s, items in enumerate(values):
            for p in items:
                ns, np_ = move(s, p)
                out[ns].add(np_)
        return [frozenset(x) for x in out]

    tables = []
    for table in document.tables:
        section, paragraph = move(table["section"], table["paragraph"])
        tables.append({**table, "section": section, "paragraph": paragraph})
    new_sections = move_lists(sections)
    if not new_sections[1]:
        return document  # 본문이 비면 원래 배치를 유지한다
    return Document(
        document.path, document.format, new_sections, tables,
        [(*move(s, p), name) for s, p, name in document.images],
        move_sets(document.table_paragraphs),
        [(*move(s, p), name, w, h) for s, p, name, w, h in document.figures],
        move_lists(document.styles), move_sets(document.aside_paragraphs), move_lists(document.numbers),
        move_sets(document.page_breaks),
        [(*move(s, p), b) for s, p, b in document.pictures], document.binaries,
    )


def split_single_section(document: "Document") -> "Document":
    """이전 이름. normalize_sections를 쓴다."""
    return normalize_sections(document)
