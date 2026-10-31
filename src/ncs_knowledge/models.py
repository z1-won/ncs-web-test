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
    toc: dict[str, Any]                 # ncs_toc.parsers.parse_toc
    overview: dict[str, Any] | None     # ncs_overview.parsers.parse_overview 의 '내용체계' (표 기준)
    body: dict[str, Any]                # ncs_toc.parsers.parse_body
    units: list[dict[str, Any]]         # structure.unit_regions — 학습 내용(N-M) 구간
    plan_goals: dict[str, Any] | None   # plan.parse_plan_goals — 계획서 학습 내용별 학습 목표
    table_paragraphs: set[int] | None   # 본문 섹션에서 표 셀 안에 든 문단 인덱스 (hwpx만, hwp는 None)
    labels: dict[str, Any]              # figtab.collect_labels — flat, caps, refs, bare, lesson_spans
