"""파서와 규칙 사이의 경계. 결과 모델(ReviewResult 등)은 ncs_core.models를 쓴다."""

from dataclasses import dataclass
from typing import Any

from ncs_core import Document
from ncs_core.pdf import PdfDocument

from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    """읽은 문서와 추출 결과. 규칙은 이 객체 하나를 받는다."""

    manuscript: Document
    plan: Document | None
    module_code: str
    config: CheckConfig
    toc: dict[str, Any]
    overview: dict[str, Any] | None
    plan_toc: dict[str, Any] | None
    body: dict[str, Any]
    presence: dict[str, Any]
    eval_tables: list[tuple[int, str, list[str]]]
    print_copy: PdfDocument | None = None       # 출력본 PDF(선택). ⑦ 쪽수 비교에만 쓴다
    headings: dict[str, dict] | None = None     # 출력본에서 찾은 제목 시작 쪽(manuscript.pages.locate_headings)
    print_error: str | None = None              # 출력본을 받았지만 못 읽은 이유
