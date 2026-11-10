"""문서를 한 번 읽어 Document로 만든다. 검수 정책이나 사용자 인터페이스에 의존하지 않는다."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import hwp, hwpx
from .pdf import PDF_MAGIC

Table = dict[str, Any]


@dataclass(frozen=True)
class Document:
    """읽은 문서. 모든 텍스트는 연속 공백이 하나로 정리된 상태다.

    sections: 섹션별 문단 텍스트(표 셀 안 문단 포함, 문서 순서).
    tables:   표 목록(문서 순서). 'styles'는 hwpx일 때만 채워진다.
    images:   (섹션, 문단 인덱스, 원본 그림 이름). hwpx만.
    table_paragraphs: 섹션별 표 셀 안에 든 문단 인덱스 집합. hwp는 표 안 문단을 구분하지 못하므로 None.
    figures:  모든 그림 (섹션, 문단 인덱스, 원본 이름 또는 "", 가로, 세로). 이름 없는 제목 배너를 찾는 데 쓴다. hwpx만.
    styles:   섹션별 문단 스타일 이름('󰊱제목', '재료,기기,안전' …). hwp는 None.
    aside_paragraphs: 섹션별 본문 밖 문단 인덱스(메모·머리말·꼬리말·각주). 본문 문장 검사에서 제외한다. hwp는 None.
    numbers:  섹션별 문단 번호 — 한글 자동 번호(문단 번호·글머리표)를 복원한 글자('1.', '(가)', '•' …) 또는 None.
              텍스트에 번호가 없는 문단의 "보이는 번호"다. hwp는 None.
    page_breaks: 섹션별 새 쪽 시작 문단 인덱스 — '쪽 나누기' 표식이 있거나, 저장된 배치 정보상 쪽 맨 위에서 시작하는 최상위 문단. hwp는 None.
    pictures: 모든 그림의 (섹션, 문단, BinData id). binaries: {BinData id: {'href', 'bytes'}} — 그림 파일 유실 확인용. hwpx만.
    """

    path: Path
    format: str
    sections: list[list[str]]
    tables: list[Table] = field(default_factory=list)
    images: list[tuple[int, int, str]] = field(default_factory=list)
    table_paragraphs: list[frozenset[int]] | None = None
    figures: list[tuple[int, int, str, int, int]] = field(default_factory=list)
    styles: list[list[str]] | None = None
    aside_paragraphs: list[frozenset[int]] | None = None
    numbers: list[list[str | None]] | None = None
    page_breaks: list[frozenset[int]] | None = None
    pictures: list[tuple[int, int, str | None]] = field(default_factory=list)
    binaries: dict[str, dict] = field(default_factory=dict)

    @property
    def has_styles(self) -> bool:
        return self.format == "hwpx"

    def section_tables(self, index: int) -> list[Table]:
        return [t for t in self.tables if t["section"] == index]

    def section_table_paragraphs(self, index: int) -> frozenset[int] | None:
        """해당 섹션에서 표 셀 안에 든 문단 인덱스. 구분할 수 없는 형식(hwp)이면 None, 섹션이 없으면 빈 집합."""
        if self.table_paragraphs is None:
            return None
        return self.table_paragraphs[index] if index < len(self.table_paragraphs) else frozenset()

    def section_figures(self, index: int) -> list[tuple[int, str, int, int]]:
        """해당 섹션의 모든 그림 (문단 인덱스, 이름 또는 "", 가로, 세로)."""
        return [(p, name, w, h) for s, p, name, w, h in self.figures if s == index]

    def section_styles(self, index: int) -> list[str] | None:
        """해당 섹션 문단별 스타일 이름. 형식이 지원하지 않으면(hwp) None."""
        if self.styles is None:
            return None
        return self.styles[index] if index < len(self.styles) else []

    def section_aside_paragraphs(self, index: int) -> frozenset[int] | None:
        """해당 섹션에서 메모·머리말·꼬리말·각주 안 문단 인덱스. hwp는 None."""
        if self.aside_paragraphs is None:
            return None
        return self.aside_paragraphs[index] if index < len(self.aside_paragraphs) else frozenset()

    def section_numbers(self, index: int) -> list[str | None] | None:
        """섹션의 문단별 자동 번호. hwp는 None(복원 불가)."""
        if self.numbers is None:
            return None
        return self.numbers[index] if index < len(self.numbers) else []

    def section_page_breaks(self, index: int) -> frozenset[int] | None:
        """섹션의 쪽 나누기 문단 인덱스. hwp는 None."""
        if self.page_breaks is None:
            return None
        return self.page_breaks[index] if index < len(self.page_breaks) else frozenset()

    def section_pictures(self, index: int) -> list[tuple[int, str | None]]:
        """섹션의 (문단, BinData id) 목록."""
        return [(p, b) for s, p, b in self.pictures if s == index]


def detect_format(path) -> str:
    """파일 내용으로 hwp/hwpx/pdf를 판별한다. 셋 다 아니면 ValueError.

    오류 문구에는 파일 이름만 넣는다 — 웹 서버가 이 문구를 400 응답으로 그대로 내보내므로
    서버 임시 폴더 경로(OS·경로 구조)가 사용자에게 보이지 않게 한다.
    """
    path = Path(path)
    with path.open("rb") as stream:
        head = stream.read(8)
    if head[:5] == PDF_MAGIC:
        return "pdf"
    if head == hwp.OLE_MAGIC:
        if not hwp.is_hwp(path.read_bytes()):
            raise ValueError(f"OLE 파일이지만 HWP 서명이 아님: {path.name}")
        return "hwp"
    if head[:2] == b"PK":
        if hwpx.is_hwpx(path):
            return "hwpx"
        raise ValueError(f"zip이지만 hwpx가 아님: {path.name}")
    raise ValueError(f"hwp/hwpx 둘 다 아님 (머리 바이트 {head!r}): {path.name}")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_document(path) -> Document:
    path = Path(path)
    fmt = detect_format(path)
    if fmt == "pdf":
        raise ValueError(f"PDF는 원고로 읽지 않습니다(표·스타일·구역이 없음). 출력본으로 함께 올리면 쪽수 확인에만 씁니다: {path.name}")
    if fmt == "hwp":
        sections, tables = hwp.load_hwp(path.read_bytes())
        images, table_paragraphs, figures, styles, aside, numbers = [], None, [], None, None, None
        page_breaks, pictures, binary_items = None, [], {}
    else:
        (sections, tables, images, table_paragraphs, figures, styles, aside, numbers,
         page_breaks, pictures, binary_items) = hwpx.load_hwpx(path)
    sections = [[_clean(p) for p in section] for section in sections]
    for table in tables:
        table["cells"] = {key: _clean(value) for key, value in table["cells"].items()}
    if not any(line for section in sections for line in section):
        raise ValueError(f"문단 텍스트를 추출하지 못했습니다: {path.name}")
    document = Document(path, fmt, sections, tables, images, table_paragraphs, figures, styles, aside, numbers,
                        page_breaks, pictures, binary_items)
    return normalize_sections(document)


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


def body_start(document: "Document", section: int = 0) -> int | None:
    """해당 구역에서 본문이 시작하는 문단 인덱스 — 첫 내비게이터(큰학습 스타일), 없으면 개요 뒤 첫 '학습 1' 줄. 없으면 None."""
    paragraphs = document.sections[section]
    styles = document.section_styles(section)
    # 본문은 차례·개요(핵심 용어/내용 체계) 뒤에 온다. 표지에도 큰학습 스타일 문단이 있을 수 있어 그 앞은 보지 않는다.
    toc = toc_title_index(paragraphs)
    toc = -1 if toc is None else toc
    front_end = next((i for i, t in enumerate(paragraphs) if FRONT_END_TEXT.match(t)), None)
    after = max(toc, front_end if front_end is not None else -1, 0)
    if styles:
        for i in range(after + 1, len(styles)):
            if styles[i] and BODY_START_STYLE.match(styles[i]):
                return i
    if front_end is None:
        return None
    return next((i for i in range(front_end + 1, len(paragraphs)) if BODY_START_TEXT.match(paragraphs[i])), None)


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


def _looks_like_body(document: "Document", section: int, head: int = 80) -> bool:
    """구역 머리에 내비게이터(큰학습 스타일) 또는 '학습 1' 줄이 있으면 본문 구역으로 본다."""
    styles = document.section_styles(section)
    if styles and any(name and BODY_START_STYLE.match(name) for name in styles[:head]):
        return True
    return any(BODY_START_TEXT.match(t) for t in document.sections[section][:head])


def normalize_sections(document: "Document") -> "Document":
    """모든 엔진이 가정하는 '구역 0 = 앞부분(위치·차례·개요), 구역 1 = 본문' 배치로 맞춘다.

    실제 원고의 구역 나눔은 제각각이다:
      (a) 구역 하나에 전부          → 본문 시작에서 둘로 나눈다
      (b) 앞부분 / 본문              → 그대로
      (c) 표지 / 차례+개요+본문      → 표지와 앞부분을 합치고 본문 시작에서 나눈다
      (d) 표지 / 차례+개요 / 본문    → 표지와 앞부분을 합친다
    본문 시작 = 첫 내비게이터(큰학습 스타일) 또는 개요 뒤 첫 '학습 1' 줄(body_start). 경계를 못 찾으면 그대로 둔다.
    문단 인덱스는 새 구역 기준으로 다시 매기고, 표·그림·스타일·번호·쪽 나누기·메모도 같이 옮긴다.
    """
    sections = document.sections
    k = toc_section(document)
    if k is None:
        k = 0
    if k + 1 < len(sections) and _looks_like_body(document, k + 1):
        if k == 0:
            return document  # (b)
        at = len(sections[k])  # (d): 차례 구역 전체가 앞부분, 다음 구역이 본문
    else:
        at = body_start(document, k)  # (a)·(c)
        if not at:
            return document  # 경계를 못 찾음
    offsets = [sum(len(sections[j]) for j in range(s)) for s in range(len(sections))]
    split = at < len(sections[k])  # 차례 구역을 둘로 나누는가(a·c), 통째로 앞부분에 두는가(d)
    new_count = 1 + int(split) + (len(sections) - k - 1)

    def move(section: int, paragraph: int) -> tuple[int, int]:
        if section < k:
            return 0, offsets[section] + paragraph
        if section == k:
            return (0, offsets[k] + paragraph) if paragraph < at else (1, paragraph - at)
        return section - k + int(split), paragraph

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
