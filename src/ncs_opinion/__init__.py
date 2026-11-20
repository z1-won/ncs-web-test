"""검토의견서 반영 여부 검토(REQ-02-003 「원고 집필 내용 검수」 중) — 1·2차 검토의견서의 의견이 최종 원고에 반영되었는지 후보를 낸다.

검수 엔진이 아닌 기능 패키지다(ncs_plan·ncs_upscale·ncs_volume과 같은 층, ncs_core만 import). 최종 판단은 사람이 한다.
의견서 읽기는 sheet.py, 의견 문장 읽기(유형·핵심어)는 keys.py, 원고 범위는 regions.py, 1차 판정은 judge.py,
LLM 2차 판정(선택)은 llm_check.py, 묶어 돌리기는 pipeline.py, 설정값과 근거는 config.py.
"""

from .config import DEFAULT_CONFIG, OpinionConfig
from .pipeline import error_rate, read_manuscript, read_sheet, review, summarize

__all__ = ["DEFAULT_CONFIG", "OpinionConfig", "error_rate", "read_manuscript", "read_sheet", "review", "summarize"]
