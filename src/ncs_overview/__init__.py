"""F02 학습모듈의 개요 ①·②·⑤·⑥·⑧ 검수. 읽기·판정·저장은 ncs_core를 쓴다."""

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
__version__ = "1.0.0"
