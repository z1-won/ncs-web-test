"""규칙 등록. 판권 ①."""

from ncs_core import Rule

from .rules.colophon import check_colophon

DEFAULT_RULES = (Rule("colophon", "F02-판권-①", lambda c: check_colophon(c.histories, c.colophons, c.module_code, c.config)),)
ALL_ITEM_IDS = ("F02-판권-①",)
