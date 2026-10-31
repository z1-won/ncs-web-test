"""F02 필요 지식 ①~⑧ 검수. 읽기·판정·저장은 ncs_core, 차례·본문 파서는 ncs_toc, 내용체계·계획서 파서는 ncs_overview를 쓴다."""

from ncs_core import ReviewResult, SavedReport

from .config import CheckConfig
from .pipeline import evaluate_review, prepare_review, run_review
from .registry import DEFAULT_RULES
from .reporting import save_results

__all__ = [
    "CheckConfig",
    "DEFAULT_RULES",
    "ReviewResult",
    "SavedReport",
    "prepare_review",
    "evaluate_review",
    "run_review",
    "save_results",
]
__version__ = "2.0.0"
