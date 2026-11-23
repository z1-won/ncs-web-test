"""수행준거 문맥 기반 이미지 추천(REQ-02-011).

  POST /api/recommend/images   {text, unit_code?, criterion_no?, limit?, use_llm?} → 요약·핵심어 + 추천 목록
PostgreSQL 저장소일 때만 붙는다(이미지 저작권 DB가 있어야 한다). 추천되는 것은 기관이 확정했고 재사용 범위가 확인된 그림뿐이며,
그림 파일은 /api/images/recommendable/{id}/file로 받는다.
생성형 AI는 키와 원고 외부 전송 승인(LLM_ALLOW_UPLOAD=1)이 둘 다 있을 때만 부르고, 아니면 규칙으로 핵심어를 뽑는다.
"""

from fastapi import FastAPI
from starlette.exceptions import HTTPException

from ..common import Services
from ..schemas import RecommendRequest


def register(app: FastAPI, services: Services) -> None:
    store = services.store
    if not store.supports_history:
        return
    from ncs_service.images import image_recommend

    @app.post("/api/recommend/images")
    def recommend_images(body: RecommendRequest) -> dict:
        try:
            return image_recommend.recommend(store.dsn, text=body.text, unit_code=body.unit_code, criterion_no=body.criterion_no,
                                             limit=body.limit, use_llm=body.use_llm)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
