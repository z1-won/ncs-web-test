"""F02 검수 공통 코어 (Python 3.10+, 추가 설치 패키지 없음).

검수 엔진 10개(ncs_position … ncs_misc)와 기능 패키지(ncs_plan 개발계획서, ncs_upscale 그림 업스케일)가 함께 쓰는 부분:
문서 읽기(hwp·hwpx·pdf·그림), 문자 정규화·판정, 입력 역할별 읽기, 모듈 코드, 규칙 실행, 확인서 접기, 결과 저장,
기준 데이터(NCS 목록·행동명사·법령명), 그리고 원고·개발계획서 구조 파서(하위 패키지 ncs_core.manuscript — 명시적으로 import한다).
검수 정책(무엇을 X로 볼지)은 여기에 두지 않는다 — 각 패키지의 rules/에 둔다.
"""

from .documents import Document, Table, load_document
from .inputs import select_documents, validate_distinct
from .models import ReviewResult, SavedReport
from .module_code import resolve_module_code, validate_module_code
from .reporting import report_summary, save_report
from .rules import Rule, run_rules
from .goals import compare_lists, difference, normalize
from .sentences import judge_action_sentence
from .text import FAIL, NA, O, PASS, PUA, TRI, UNDECIDED, VERDICTS, X, flatten, make_normalizer, verdict, visible

__all__ = [
    "Document",
    "Table",
    "load_document",
    "select_documents",
    "validate_distinct",
    "ReviewResult",
    "SavedReport",
    "resolve_module_code",
    "validate_module_code",
    "report_summary",
    "save_report",
    "Rule",
    "run_rules",
    "compare_lists",
    "difference",
    "normalize",
    "judge_action_sentence",
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
