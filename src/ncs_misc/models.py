"""기타 규칙의 입력 문맥."""
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
    toc: dict[str, Any]
    body: dict[str, Any]          # parse_body — lines/spans/lessons
    units: list[dict[str, Any]]   # unit_regions — 학습 내용(N-M) 구간
    presence: dict[str, Any]      # section_presence — 참고 자료·활용 서식·부록 위치
