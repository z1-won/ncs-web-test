"""규칙 추가 지점. 규칙은 ReviewContext 하나를 받아 기존 형식의 행 목록을 돌려준다."""

from ncs_core import Rule

from .rules.sentences import check_perform_sentences
from .rules.title import check_perform_title

DEFAULT_RULES = (
    Rule("title", "F02-수행-①", lambda c: check_perform_title(c.blocks)),
    Rule("sentences", "F02-수행-④", lambda c: check_perform_sentences(c.blocks, has_styles=c.has_styles)),
)

# 수행 내용 ①~④ 중 규칙이 없는 것(②: 금칙어 사전 필요, ③: 추상성은 의미 판단)은 진단의 not_implemented로 보고한다.
ALL_ITEM_IDS = tuple("F02-수행-" + n for n in "①②③④")
