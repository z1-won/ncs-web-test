"""실행 조정 계층의 입력·결과. 웹 프레임워크와 독립적인 데이터 계약."""

from dataclasses import dataclass
from pathlib import Path

from ncs_core import ReviewResult


@dataclass(frozen=True)
class ReviewRequest:
    paths: tuple[Path, ...]
    check: str = "position"
    module_code: str = ""
    roles: dict[str, str] | None = None


@dataclass(frozen=True)
class ExecutedReview:
    check: str
    result: ReviewResult
