"""개요 검수 규칙이 쓰는 판정용 패턴. 양식 제목·내용체계 인식 패턴은 ncs_core.manuscript.patterns에 있다."""
import re

GOAL_END = re.compile(r"할\s*수\s*있다\s*\.$")
# 능력단위 정의 → 학습모듈의 목표: 주어('…란/이란/은/는') 삭제, '~하는 능력이다' → '~할 수 있다'
DEFINITION_SUBJECT = re.compile(r"^.*?(?:이란|란|은|는)\s+")
DEFINITION_END = re.compile(r"(하|할 수 있)는\s*능력이다\s*\.?$")
# ⑧ 단어(명사형)가 아닐 가능성이 있는 종결
TERM_PREDICATE = re.compile(r"(다|하기|함|됨|하는|되는|할 것|것)$")
