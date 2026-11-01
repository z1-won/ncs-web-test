"""참고 자료 규칙의 입력 문맥."""
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
    presence: dict[str, Any]       # section_presence — 참고 자료 구역 위치
    entries: list[dict[str, Any]]  # entries.collect_entries — 참고 자료 항목
    citations: list[dict[str, Any]]  # entries.collect_citations — 본문 '출처:' 줄
