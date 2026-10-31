"""규칙 추가 지점. 규칙은 ReviewContext 하나를 받아 기존 형식의 행 목록을 돌려준다."""

from ncs_core import Rule

from .rules.classification import check_classification
from .rules.emphasis import check_emphasis
from .rules.position import check_position

DEFAULT_RULES = (
    Rule("classification", "F02-위치-①", lambda c: check_classification(c.plan_classification, c.manuscript_classification)),
    Rule("position", "F02-위치-②③④", lambda c: check_position(c.plan_position, c.manuscript_position)),
    Rule(
        "emphasis",
        "F02-위치-⑤",
        lambda c: check_emphasis(c.styled_table, c.module_code, c.plan_module_name, has_styles=c.manuscript.has_styles),
    ),
)

ALL_ITEM_IDS = tuple("F02-위치-" + n for n in "①②③④⑤")
