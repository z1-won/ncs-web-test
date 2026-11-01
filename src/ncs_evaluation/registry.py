"""평가 ① 규칙만 등록한다."""
from ncs_core import Rule
from .rules.names import check_names

DEFAULT_RULES = (Rule("names", "F02-평가-①", check_names),)
ALL_ITEM_IDS = tuple("F02-평가-" + n for n in "①②③④⑤")
