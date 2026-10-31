"""실행 조정 계층의 입력·결과. 웹 프레임워크와 독립적인 데이터 계약."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ncs_core import ReviewResult, Rule

if TYPE_CHECKING:
    from ncs_knowledge.config import CheckConfig as KnowledgeConfig
    from ncs_overview.config import CheckConfig as OverviewConfig
    from ncs_position.config import CheckConfig as PositionConfig
    from ncs_toc.config import CheckConfig as TocConfig


@dataclass(frozen=True)
class ReviewRequest:
    """config/rules가 None이면 엔진 기본값, rules=()이면 규칙을 실행하지 않는다."""

    paths: tuple[Path, ...]
    check: str = "position"
    module_code: str = ""
    roles: dict[str, str] | None = None
    config: PositionConfig | TocConfig | OverviewConfig | KnowledgeConfig | None = None
    rules: Sequence[Rule] | None = None


@dataclass(frozen=True)
class ExecutedReview:
    check: str
    result: ReviewResult
