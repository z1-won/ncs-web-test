"""그림 기능 패키지 — REQ-02-009(이미지 추출·출처 태깅)와 REQ-02-005(원고 이미지 검수).

F02 검수 엔진이 아니다(ENGINES에 등록하지 않음). 코어(ncs_core)만 import하고, 그림 디코딩에 Pillow를 쓴다(web extra).
결과 행 모양은 엔진과 같게 해서 메모 원고(ncs_service.annotate)·화면 표를 그대로 쓴다. 설계: 설계서_LLM이미지검수_통합.md 8·16장.
"""

from .pipeline import prepare_figures, review_figures, run_review, save_result

__all__ = ["prepare_figures", "review_figures", "run_review", "save_result"]
