"""파이프라인 경계의 데이터 계약. 외부 JSON 키는 v1.1과 동일하다."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

ChecklistItem = TypedDict(
    "ChecklistItem",
    {
        "item_id": str,
        "region_path": str,
        "원고": Any,
        "개발계획서": Any,
        "체크": dict[str, Literal["O", "X", "△", "-"]],
        "판정": str,
        "비고": dict[str, str] | list[str],
        "수정 제안": Any,
    },
)


@dataclass(frozen=True)
class Document:
    path: Path
    format: str
    sections: list[list[str]]
    tables: list[dict]
    formatted_tables: list[dict] | None = None


@dataclass(frozen=True)
class ReviewContext:
    plan: Document
    manuscript: Document
    module_code: str
    module_name: str | None


@dataclass
class ReviewResult:
    module_code: str
    checklist: list[ChecklistItem]
    findings: list[dict]


@dataclass(frozen=True)
class SavedReport:
    directory: Path
    zip_path: Path
    summary: dict
