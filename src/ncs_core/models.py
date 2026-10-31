"""파이프라인 경계의 공통 데이터 계약. 체크리스트 행의 한국어 JSON 키는 기존과 같다."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

ChecklistItem = TypedDict(
    "ChecklistItem",
    {
        "item_id": str,
        "region_path": str,
        "원고": Any,
        "체크": dict[str, Literal["O", "X", "△", "-"]],
        "판정": str,
        "비고": dict[str, str] | list[str],
        "수정 제안": Any,
    },
)


@dataclass
class ReviewResult:
    """한 번의 검사 결과. 저장 형식과 무관하다."""

    module_code: str
    checklist: list[ChecklistItem]
    findings: list[dict]
    diagnostics: dict[str, Any] = field(default_factory=dict)
    context: Any = None
    sheet: list[dict[str, Any]] = field(default_factory=list)  # 검수 확인서(F02) 표 행


@dataclass(frozen=True)
class SavedReport:
    directory: Path
    zip_path: Path
    summary: dict[str, Any]
