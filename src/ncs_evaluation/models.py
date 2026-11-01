"""평가 규칙의 입력 문맥."""
from dataclasses import dataclass
from ncs_core import Document
from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    manuscript: Document
    plan: Document | None
    module_code: str
    config: CheckConfig
    toc: dict | None
    overview: dict | None
    plan_toc: dict | None
    body: dict
