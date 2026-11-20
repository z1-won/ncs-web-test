"""원고 집필 내용 생성 — 문장 추천(REQ-02-004). 작성 규칙에 어긋난 문장을 원고에서 찾아 순위 붙인 정정 후보(최대 5개)를 낸다.

검수 엔진이 아닌 기능 패키지다(ncs_plan·ncs_upscale·ncs_volume과 같은 층, ncs_core만 import). 판정(O/X)이 아니라 후보를 낸다.
종류별 규정 꼴은 kinds.py, 종결형 읽기·활용은 endings.py, 표현 규칙·순위는 rewrite.py, 원고에서 문장 모으기는 extract.py,
참고 예문은 examples.py, AI 후보(설정·승인·허용 목록이 있을 때만)는 llm_suggest.py, 묶음은 pipeline.py. 설정값과 근거는 config.py.
"""

from .config import DEFAULT_CONFIG, KINDS, SuggestConfig
from .pipeline import suggest_manuscript, suggest_sentence

__all__ = ["DEFAULT_CONFIG", "KINDS", "SuggestConfig", "suggest_manuscript", "suggest_sentence"]
