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
    """

    path: Path
    format: str
    sections: list[list[str]]
    tables: list[Table] = field(default_factory=list)
    images: list[tuple[int, int, str]] = field(default_factory=list)
    table_paragraphs: list[frozenset[int]] | None = None
    figures: list[tuple[int, int, str, int, int]] = field(default_factory=list)

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
        images, table_paragraphs, figures = [], None, []
    else:
        sections, tables, images, table_paragraphs, figures = hwpx.load_hwpx(path)
    sections = [[_clean(p) for p in section] for section in sections]
    for table in tables:
        table["cells"] = {key: _clean(value) for key, value in table["cells"].items()}
    if not any(line for section in sections for line in section):
        raise ValueError(f"문단 텍스트를 추출하지 못했습니다: {path}")
    return Document(path, fmt, sections, tables, images, table_paragraphs, figures)
