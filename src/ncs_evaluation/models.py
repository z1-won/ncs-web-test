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
    regions: list[dict]          # region.eval_regions — 학습별 평가 구역(준거 표·방법 목록)
    plan_goals: dict | None      # ncs_core.manuscript.parse_plan_goals — 계획서 학습 내용별 학습 목표
