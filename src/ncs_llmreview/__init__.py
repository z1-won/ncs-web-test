"""LLM 검토 — 형식 검수(엔진) 뒤에 사용자가 'LLM 검토'를 눌렀을 때만 Claude로 문장을 검토해 수정 후보를 낸다.

수정해야 하는 부분(원문) · 근거(문제 종류·이유) · 수정 방안(수정 문장)을 항목별로 돌려준다. 결과는 사람 확인(△) 후보일 뿐이다.
구조 기반 조각(학습 1 포함) → 원고 한 덩어리(프롬프트 캐시) + 검토 항목 여러 개를 한 번에 → Claude →
답 검증(보낸 줄 번호·인용이 원문에 있는가). 같은 입력은 디스크 캐시에서 다시 읽어 토큰을 다시 쓰지 않는다.

계층: ncs_service와 같은 층 — 엔진(ncs_perform·ncs_evaluation)의 추출기를 쓰고, ncs_web은 모른다. 공식 anthropic SDK를 쓴다(web extra).
"""

from .service import TASKS, review_manuscript, status, to_rows

__all__ = ["TASKS", "review_manuscript", "status", "to_rows"]
