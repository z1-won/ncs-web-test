"""규칙 등록. ①②③. ④(기존 모듈 그림 출처)는 이전 판본 자료가 있어야 해서 미구현."""

from ncs_core import Rule

from .rules.coverage import check_coverage
from .rules.format import check_format
from .rules.order import check_order

DEFAULT_RULES = (
    Rule("coverage", "F02-참고자료-①", lambda c: check_coverage(c.entries, c.citations)),
    Rule("format", "F02-참고자료-②", lambda c: check_format(c.entries, c.citations)),
    Rule("order", "F02-참고자료-③", lambda c: check_order(c.entries)),
)

ALL_ITEM_IDS = tuple("F02-참고자료-" + n for n in "①②③④")
