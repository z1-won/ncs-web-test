"""규칙 추가 지점. 규칙은 ReviewContext 하나를 받아 기존 형식의 행 목록을 돌려준다."""

from ncs_core import Rule

from .rules.brands import check_brands
from .rules.sentences import check_perform_sentences
from .rules.title import check_perform_title

DEFAULT_RULES = (
    Rule("title", "F02-수행-①", lambda c: check_perform_title(c.blocks)),
    Rule("brands", "F02-수행-②", lambda c: check_brands(c.blocks)),
    Rule("sentences", "F02-수행-④", lambda c: check_perform_sentences(c.blocks, has_styles=c.has_styles)),
)

# ②는 LLM 후보(△) — ncs_core.llm 설정이 없으면 △ '미설정'. ③(안전사항 추상성)은 아직 규칙 없음.
ALL_ITEM_IDS = tuple("F02-수행-" + n for n in "①②③④")
