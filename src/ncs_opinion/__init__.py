"""검토의견서·심의의견서 반영 여부 검토(REQ-02-003 「원고 집필 내용 검수」 중) — 1·2차 검토의견서와 심의의견서의 의견이 최종 원고에 반영되었는지 후보를 낸다.

검수 엔진이 아닌 기능 패키지다(ncs_plan·ncs_upscale·ncs_volume과 같은 층, ncs_core만 import). 최종 판단은 사람이 한다.
판정은 LLM이 하고(llm_check.py), 규칙 코드는 문서 읽기(sheet.py 의견서, regions.py 원고 문단 지도), 보낼 범위 고르기(regions.py),
LLM 출력 검증과 정책(judge.py)만 맡는다. 의견의 표·그림 참조 읽기는 keys.py, 묶어 돌리기는 pipeline.py, 설정값과 근거는 config.py.
"""

from .config import DEFAULT_CONFIG, OpinionConfig
from .pipeline import error_rate, read_manuscript, read_sheet, review, summarize

__all__ = ["DEFAULT_CONFIG", "OpinionConfig", "error_rate", "read_manuscript", "read_sheet", "review", "summarize"]
