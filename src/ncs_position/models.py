"""파서와 규칙 사이의 경계. 결과 모델(ReviewResult 등)은 ncs_core.models를 쓴다."""

from dataclasses import dataclass
from typing import Any

from ncs_core import Document, Table

from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    """읽은 문서와 추출 결과. 규칙은 이 객체 하나를 받는다."""

    manuscript: Document
    plan: Document
    module_code: str
    config: CheckConfig
    plan_classification: dict[str, str]
    manuscript_classification: dict[str, str]
    plan_position: dict[str, Any]
    manuscript_position: dict[str, Any]
    styled_table: Table | None
    plan_module_name: str | None
