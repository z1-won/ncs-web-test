"""규칙 추가 지점. 규칙은 ReviewContext 하나를 받아 기존 형식의 행 목록을 돌려준다."""

from ncs_core import Rule

from .rules.consistency import check_toc3
from .rules.names import check_toc1
from .rules.placement import check_toc4
from .rules.tail import check_toc5, check_toc6


def _check_toc4(c):
    images = [(p, name) for s, p, name in c.manuscript.images if s == c.config.body_section]
    return check_toc4(c.toc, c.body, images, lines_to_raw=lambda k: c.body["lines"][k][0])


DEFAULT_RULES = (
    Rule("names", "F02-차례-①", lambda c: check_toc1(c.plan_toc, c.toc)),
    Rule("consistency", "F02-차례-③", lambda c: check_toc3(c.plan_toc, c.toc, c.overview, c.body, c.eval_tables)),
    Rule("placement", "F02-차례-④", _check_toc4),
    Rule("references", "F02-차례-⑤", lambda c: check_toc5(c.presence, c.toc)),
    Rule("appendix", "F02-차례-⑥", lambda c: check_toc6(c.presence, c.toc)),
)

# 차례 항목 ①~⑦ 중 규칙이 없는 것은 진단의 not_implemented로 보고한다.
ALL_ITEM_IDS = tuple("F02-차례-" + n for n in "①②③④⑤⑥⑦")
