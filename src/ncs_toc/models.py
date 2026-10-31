"""파서와 규칙 사이의 경계. 결과 모델(ReviewResult 등)은 ncs_core.models를 쓴다."""

from dataclasses import dataclass
from typing import Any

from ncs_core import Document

from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    """읽은 문서와 추출 결과. 규칙은 이 객체 하나를 받는다."""

    manuscript: Document
    plan: Document | None
    module_code: str
    config: CheckConfig
    toc: dict[str, Any]
    overview: dict[str, Any] | None
    plan_toc: dict[str, Any] | None
    body: dict[str, Any]
    presence: dict[str, Any]
    eval_tables: list[tuple[int, str, list[str]]]
