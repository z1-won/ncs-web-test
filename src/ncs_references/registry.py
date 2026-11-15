"""규칙 등록. ①②③④. ④는 옛 학습모듈 출처 줄의 여섯 요소만 본다(이전 판본과의 대조는 하지 않음)."""

from ncs_core import Rule

from .rules.coverage import check_coverage
from .rules.format import check_format
from .rules.old_module import check_old_module
from .rules.order import check_order

DEFAULT_RULES = (
    Rule("coverage", "F02-참고자료-①", lambda c: check_coverage(c.entries, c.citations)),
    Rule("format", "F02-참고자료-②", lambda c: check_format(c.entries, c.citations)),
    Rule("order", "F02-참고자료-③", lambda c: check_order(c.entries)),
    Rule("old_module", "F02-참고자료-④", lambda c: check_old_module(c.citations)),
)

ALL_ITEM_IDS = tuple("F02-참고자료-" + n for n in "①②③④")
