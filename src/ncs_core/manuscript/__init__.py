"""원고·개발계획서의 구조 파서 (차례·개요·본문·꼬리 섹션·명칭 비교). 검수 정책은 두지 않는다.

네 검수 패키지가 같은 파서 위에 선다. 파서는 I/O 없이 Document 또는 문단 섹션 목록을 받는다.
"""

from .body import parse_body
from .config import DEFAULT_PARSE_CONFIG, ParseConfig
from .names import HEAD_NUMBER, diff_list, norm, pua_note, same
from .overview import parse_overview, parse_plan, split_items
from .plan_goals import parse_plan_goals
from .presence import section_presence
from .structure import BodyBoundary, detect_body_boundary
from .toc import parse_plan_toc, parse_toc
from .units import HEAD_MARK, MEMO_LINE, mark, unit_regions

__all__ = [
    "BodyBoundary",
    "detect_body_boundary",
    "DEFAULT_PARSE_CONFIG",
    "HEAD_NUMBER",
    "ParseConfig",
    "diff_list",
    "norm",
    "parse_body",
    "parse_overview",
    "parse_plan",
    "parse_plan_goals",
    "parse_plan_toc",
    "parse_toc",
    "pua_note",
    "same",
    "section_presence",
    "split_items",
    "HEAD_MARK",
    "MEMO_LINE",
    "mark",
    "unit_regions",
]
