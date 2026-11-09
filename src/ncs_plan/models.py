"""개발계획서 규칙의 입력 문맥."""
from dataclasses import dataclass
from typing import Any

from ncs_core import Document
from ncs_core.lexicon import ActionNounLexicon
from ncs_core.ncs_catalog import Catalog

from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    manuscript: Document | None      # 계획서 점검에는 쓰지 않는다. 함께 올라오면 모듈 코드 추출에만
    plan: Document
    module_code: str
    config: CheckConfig
    data: dict[str, Any]             # parsers.read_plan — 기본·대조표·총괄표·위치·모듈
    catalog: Catalog | None
    lexicon: ActionNounLexicon
    module_cells: list[str]          # 모듈 표의 모든 셀 글(자리표시 탐지용)
