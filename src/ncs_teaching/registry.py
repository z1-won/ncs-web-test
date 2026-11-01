"""규칙 추가 지점. 규칙은 ReviewContext 하나를 받아 기존 형식의 행 목록을 돌려준다."""

from ncs_core import Rule

from .rules.counts import check_counts
from .rules.sentences import check_sentences

DEFAULT_RULES = (
    Rule("teach_count", "F02-교수학습-①", lambda c: check_counts(c.blocks, "교수", min_items=c.config.min_items)),
    Rule("teach_sentences", "F02-교수학습-②", lambda c: check_sentences(c.blocks, "교수")),
    Rule("learn_count", "F02-교수학습-③", lambda c: check_counts(c.blocks, "학습", min_items=c.config.min_items)),
    Rule("learn_sentences", "F02-교수학습-④", lambda c: check_sentences(c.blocks, "학습")),
)

ALL_ITEM_IDS = tuple("F02-교수학습-" + n for n in "①②③④")
