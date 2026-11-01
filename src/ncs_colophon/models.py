"""판권 규칙의 입력 문맥."""
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
    histories: list[dict[str, Any]]   # tables.read_histories — 'NCS학습모듈 개발이력' 표들
    colophons: list[dict[str, Any]]   # tables.read_colophons — 판권 표들
