"""수행 내용 규칙의 입력 문맥."""
from dataclasses import dataclass

from ncs_core import Document

from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    manuscript: Document
    plan: Document | None
    module_code: str
    config: CheckConfig
    blocks: list[dict]  # blocks.split_perform_blocks 결과
    has_styles: bool  # 문단 스타일 이름을 읽었는가(hwpx). 없으면 첫 글자로 번호 수준을 추정한다
