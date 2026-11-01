"""문서를 한 번 읽어 Document로 만든다. 검수 정책이나 사용자 인터페이스에 의존하지 않는다."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import hwp, hwpx

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
    page_breaks: 섹션별 '쪽 나누기' 문단 인덱스(그 문단 앞에서 새 쪽 시작). hwp는 None.
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
    """파일 내용으로 hwp/hwpx를 판별한다. 둘 다 아니면 ValueError."""
    path = Path(path)
    with path.open("rb") as stream:
        head = stream.read(8)
    if head == hwp.OLE_MAGIC:
        if not hwp.is_hwp(path.read_bytes()):
            raise ValueError(f"OLE 파일이지만 HWP 서명이 아님: {path}")
        return "hwp"
    if head[:2] == b"PK":
        if hwpx.is_hwpx(path):
            return "hwpx"
        raise ValueError(f"zip이지만 hwpx가 아님: {path}")
    raise ValueError(f"hwp/hwpx 둘 다 아님 (머리 바이트 {head!r}): {path}")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_document(path) -> Document:
    path = Path(path)
    fmt = detect_format(path)
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
        raise ValueError(f"문단 텍스트를 추출하지 못했습니다: {path}")
    document = Document(path, fmt, sections, tables, images, table_paragraphs, figures, styles, aside, numbers,
                        page_breaks, pictures, binary_items)
    return split_single_section(document)


BODY_START_STYLE = re.compile(r"^큰학습")                 # 내비게이터(학습 N 큰 제목)의 문단 스타일
BODY_START_TEXT = re.compile(r"^학\s*습\s*1$")           # 스타일이 없을 때: 개요 뒤 첫 '학습 1' 줄
FRONT_END_TEXT = re.compile(r"^(핵심\s*용어|학습\s*모듈의\s*내용\s*체계)")


def body_start(document: "Document") -> int | None:
    """구역이 하나뿐인 원고에서 본문이 시작하는 문단 인덱스 — 첫 내비게이터(큰학습 스타일), 없으면 개요 뒤 첫 '학습 1' 줄."""
    paragraphs = document.sections[0]
    styles = document.section_styles(0)
    if styles:
        for i, name in enumerate(styles):
            if name and BODY_START_STYLE.match(name) and i > 0:
                return i
    front_end = next((i for i, t in enumerate(paragraphs) if FRONT_END_TEXT.match(t)), None)
    if front_end is None:
        return None
    return next((i for i in range(front_end + 1, len(paragraphs)) if BODY_START_TEXT.match(paragraphs[i])), None)


def split_single_section(document: "Document") -> "Document":
    """구역이 하나뿐이면 앞부분(위치·차례·개요)과 본문을 두 구역으로 나눠 돌려준다 — 모든 엔진이 '구역 0 = 앞부분, 구역 1 = 본문'을 가정한다.

    문단 인덱스는 본문 구역 기준으로 다시 매기고, 표·그림·스타일·번호·쪽 나누기·메모도 같이 옮긴다. 경계를 못 찾으면 그대로 둔다.
    """
    if len(document.sections) != 1:
        return document
    at = body_start(document)
    if not at:
        return document

    def split_list(values):
        return None if values is None else [values[0][:at], values[0][at:]]

    def split_set(values):
        return None if values is None else [frozenset(i for i in values[0] if i < at), frozenset(i - at for i in values[0] if i >= at)]

    def move(section: int, paragraph: int) -> tuple[int, int]:
        return (0, paragraph) if paragraph < at else (1, paragraph - at)

    tables = []
    for table in document.tables:
        section, paragraph = move(table["section"], table["paragraph"])
        tables.append({**table, "section": section, "paragraph": paragraph})
    return Document(
        document.path, document.format, split_list(document.sections), tables,
        [(*move(s, p), name) for s, p, name in document.images],
        split_set(document.table_paragraphs),
        [(*move(s, p), name, w, h) for s, p, name, w, h in document.figures],
        split_list(document.styles), split_set(document.aside_paragraphs), split_list(document.numbers),
        split_set(document.page_breaks),
        [(*move(s, p), b) for s, p, b in document.pictures], document.binaries,
    )
