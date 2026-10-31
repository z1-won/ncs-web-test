"""규칙 추가 지점. 규칙은 ReviewContext 하나를 받아 기존 형식의 행 목록을 돌려준다."""

from ncs_core import Rule

from .rules.goal import check_goal
from .rules.prerequisites import check_prerequisites
from .rules.structure import check_structure_elements, check_structure_names
from .rules.terms import check_terms

DEFAULT_RULES = (
    Rule("goal", "F02-개요-①", lambda c: check_goal(c.overview, c.plan_info)),
    Rule("prerequisites", "F02-개요-②", lambda c: check_prerequisites(c.overview, c.config.max_prerequisites)),
    Rule("structure_names", "F02-개요-⑤", lambda c: check_structure_names(c.overview, c.plan_info)),
    Rule("structure_elements", "F02-개요-⑥", lambda c: check_structure_elements(c.overview, c.plan_info, c.module_code)),
    Rule("terms", "F02-개요-⑧", lambda c: check_terms(c.overview, c.config.max_terms, c.config.term_max_length)),
)

# 개요 항목 ①~⑧ 중 규칙이 없는 것은 진단의 not_implemented로 보고한다.
# ③ 선수학습 코드 병기, ④ 선수학습 능력단위 수준(NCS 수준 자료 필요), ⑦ 통합 개발 시 요소 전부 기재(통합 사례 필요).
ALL_ITEM_IDS = tuple("F02-개요-" + n for n in "①②③④⑤⑥⑦⑧")
