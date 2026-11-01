"""교수·학습 방법 규칙의 입력 문맥."""
from dataclasses import dataclass

from ncs_core import Document

from .config import CheckConfig


@dataclass(frozen=True)
class ReviewContext:
    manuscript: Document
    plan: Document | None
    module_code: str
    config: CheckConfig
    blocks: list[dict]   # blocks.split_teaching_blocks 결과 — 학습마다 하나
    has_styles: bool     # 문단 스타일 이름을 읽었는가(hwpx)
