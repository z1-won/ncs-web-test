"""F02 검수 공통 코어 (Python 3.10+, 추가 설치 패키지 없음).

두 검수 패키지(ncs_toc, ncs_position)가 공유하는 부분:
문서 읽기, 문자 정규화·판정, 입력 역할 판별, 모듈 코드, 규칙 실행, 결과 저장.
검수 정책(무엇을 X로 볼지)은 여기에 두지 않는다.
"""

from .documents import Document, Table, load_document
from .inputs import detect_role, select_documents, validate_distinct
from .models import ReviewResult, SavedReport
from .module_code import resolve_module_code, validate_module_code
from .reporting import save_report
from .rules import Rule, run_rules
from .text import FAIL, NA, O, PASS, PUA, TRI, UNDECIDED, VERDICTS, X, flatten, make_normalizer, verdict, visible

__all__ = [
    "Document",
    "Table",
    "load_document",
    "detect_role",
    "select_documents",
    "validate_distinct",
    "ReviewResult",
    "SavedReport",
    "resolve_module_code",
    "validate_module_code",
    "save_report",
    "Rule",
    "run_rules",
    "NA",
    "PASS",
    "FAIL",
    "UNDECIDED",
    "VERDICTS",
    "O",
    "PUA",
    "TRI",
    "X",
    "flatten",
    "make_normalizer",
    "verdict",
    "visible",
]
__version__ = "1.0.0"
