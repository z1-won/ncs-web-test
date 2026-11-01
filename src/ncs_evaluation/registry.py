"""평가 규칙 등록. ①(학습 내용명) ②(평가 준거 학습 목표) ③(평가 방법 수) ⑤(방법별 피드백)."""
from ncs_core import Rule

from .rules.feedback import check_feedback
from .rules.goals import check_criteria_goals
from .rules.methods import check_methods
from .rules.names import check_names

DEFAULT_RULES = (
    Rule("names", "F02-평가-①", check_names),
    Rule("criteria_goals", "F02-평가-②", lambda c: check_criteria_goals(c.regions, c.plan_goals)),
    Rule("methods", "F02-평가-③", lambda c: check_methods(c.regions, min_methods=c.config.min_methods)),
    Rule("feedback", "F02-평가-⑤", lambda c: check_feedback(c.regions)),
)
ALL_ITEM_IDS = tuple("F02-평가-" + n for n in "①②③④⑤")
