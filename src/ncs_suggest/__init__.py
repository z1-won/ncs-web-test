"""원고 집필 내용 생성 — 문장 추천(REQ-02-004). 작성 규칙에 어긋난 문장을 AI가 찾아 순위 붙인 정정 후보(최대 5개)를 낸다.

검수 엔진이 아닌 기능 패키지다(ncs_plan·ncs_upscale·ncs_volume과 같은 층, ncs_core만 import). 판정(O/X)이 아니라 후보를 낸다.
고칠 문장과 후보는 AI가 낸다(llm_suggest.py). 규칙 코드는 원고에서 문장 모으기(extract.py)와 AI 후보 검증(llm_suggest.validate,
규정 꼴 재검사는 kinds.py)만 맡는다. 참고 예문은 examples.py, 묶음은 pipeline.py, 설정값과 근거는 config.py.
AI에는 문장의 문맥(자리·앞뒤 문장)을 함께 보내고, 후보에는 참고 문장 묶음(corpus.py — 기존 학습모듈·공공저작물)의 근거 문장을 붙인다.
산출물 '문장 정정 필요 후보문장표'는 pipeline.candidate_table.
"""

from .config import DEFAULT_CONFIG, KINDS, SuggestConfig
from .corpus import Corpus, Reference
from .pipeline import candidate_table, suggest_manuscript, suggest_sentence

__all__ = ["DEFAULT_CONFIG", "KINDS", "Corpus", "Reference", "SuggestConfig", "candidate_table", "suggest_manuscript", "suggest_sentence"]
