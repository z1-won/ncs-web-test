"""파서와 규칙 사이의 경계. 결과 모델(ReviewResult 등)은 ncs_core.models를 쓴다."""

from dataclasses import dataclass
from typing import Any

from ncs_core import Document, Table

from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    """읽은 문서와 추출 결과. 규칙은 이 객체 하나를 받는다."""

    manuscript: Document
    plan: Document
    module_code: str
    config: CheckConfig
    plan_classification: dict[str, str]
    manuscript_classification: dict[str, str]
    plan_position: dict[str, Any]
    manuscript_position: dict[str, Any]
    styled_table: Table | None
    plan_module_name: str | None
    # 기준 출처: 'NCS 목록'(ncs_core.ncs_catalog에 해당 세분류가 있을 때) 또는 '개발계획서'.
    # NCS 목록이 기준일 때 plan_classification/plan_position에는 목록 값이 들어가고, 개발계획서에서 읽은 값은 아래에 따로 둔다(목록↔계획서 대조용).
    reference_source: str = "개발계획서"
    plan_only_classification: dict[str, str] | None = None
    plan_only_position: dict[str, Any] | None = None
    # ⑤의 '해당 행'을 고르는 데 쓴 학습모듈명(plan_module_name)의 출처: '개발계획서'(학습 모듈명 칸) /
    # 'NCS 목록'(능력단위 코드로 찾은 능력단위명) / '… 위치 표'(기준 표의 능력단위 번호째 행). 못 찾으면 코드 번호 순번으로 돌아간다.
    module_name_source: str = "개발계획서"
