"""파서와 규칙 사이의 경계. 결과 모델(ReviewResult 등)은 ncs_core.models를 쓴다."""

from dataclasses import dataclass
from typing import Any

from ncs_core import Document

from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    manuscript: Document
    plan: Document | None
    module_code: str
    config: CheckConfig
    overview: dict[str, Any]          # parsers.parse_overview 결과
    plan_info: dict[str, Any] | None  # parsers.parse_plan 결과 (계획서 없으면 None)
