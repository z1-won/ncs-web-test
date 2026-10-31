"""규칙 추가 지점. 규칙은 ReviewContext 하나를 받아 기존 형식의 행 목록을 돌려준다."""

from ncs_core import Rule

from .rules.contents import check_contents
from .rules.figures import check_figures
from .rules.goals import check_goals
from .rules.navigator import check_navigator
from .rules.numbering import check_numbering
from .rules.sources import check_sources


def _sections(c):
    return [c.manuscript.sections[c.config.front_section], c.manuscript.sections[c.config.body_section]]


DEFAULT_RULES = (
    # ①②③은 같은 내비게이터 묶음을 한 번 읽어 세 항목의 행을 함께 낸다.
    Rule("navigator", "F02-필요지식-", lambda c: check_navigator(c.toc, c.overview, c.body)),
    Rule("contents", "F02-필요지식-④", lambda c: check_contents(c.toc, c.overview, c.body, c.units)),
    Rule("goals", "F02-필요지식-⑤", lambda c: check_goals(c.plan_goals, c.units, similarity=c.config.goal_similarity, whitespace_is_difference=c.config.whitespace_is_difference)),
    Rule("numbering", "F02-필요지식-⑥", lambda c: check_numbering(c.body, c.units, c.table_paragraphs)),
    Rule("figures", "F02-필요지식-⑦", lambda c: check_figures(_sections(c), c.labels, min_agreement=c.config.figtab_min_agreement)),
    Rule("sources", "F02-필요지식-⑧", lambda c: check_sources(_sections(c)[1], 1, c.labels["caps"], c.table_paragraphs, lookback=c.config.source_lookback, lookahead=c.config.source_lookahead)),
)

ALL_ITEM_IDS = tuple("F02-필요지식-" + n for n in "①②③④⑤⑥⑦⑧")
