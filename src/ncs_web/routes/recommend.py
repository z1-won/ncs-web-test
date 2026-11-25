"""수행준거 문맥 기반 이미지 추천(REQ-02-011).

  POST /api/recommend/images          {text, unit_code?, criterion_no?, limit?, use_llm?} → 요약·핵심어·그림이 필요한 지점 + 추천 목록
  POST /api/recommend/choices         {text, unit_code?, criterion_no?, image_id, choice, rank?, score?, detail?} → 선택 기록(쓸 그림 / 맞지 않음 / 지움)
  POST /api/recommend/choices/mine    {text, unit_code?, criterion_no?} → 이 사람이 이 문단에서 남긴 선택 {그림 id: 선택}
  GET  /api/recommend/choices/export  선택 기록을 정답 세트(ncs_recommend.evaluate 형식)로 — 에디터와 직능연 계정만
PostgreSQL 저장소일 때만 붙는다(이미지 저작권 DB가 있어야 한다). 추천되는 것은 기관이 확정했고 재사용 범위가 확인된 그림뿐이며,
그림 파일은 /api/images/recommendable/{id}/file로 받는다.
생성형 AI는 키와 원고 외부 전송 승인(LLM_ALLOW_UPLOAD=1)이 둘 다 있을 때만 부르고, 아니면 규칙으로 핵심어를 뽑는다.
선택 기록은 문단 글을 DB에 남긴다(추천을 재는 정답 세트의 재료 — 개인정보처리방침에 적혀 있다).
"""

from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException

from ..common import Services, actor, manager_only
from ..schemas import RecommendChoiceRequest, RecommendRequest

DETAIL_LIMIT = 4000      # 선택 기록에 함께 남기는 근거(JSON 글자 수) 상한


def register(app: FastAPI, services: Services) -> None:
    store = services.store
    if not store.supports_history:
        return
    from ncs_service.images import image_choices, image_recommend
    from ncs_service.images.image_store import ImageNotFound

    @app.post("/api/recommend/images")
    def recommend_images(body: RecommendRequest) -> dict:
        try:
            return image_recommend.recommend(store.dsn, text=body.text, unit_code=body.unit_code, criterion_no=body.criterion_no,
                                             limit=body.limit, use_llm=body.use_llm)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    def chooser(request: Request, given: str) -> str:
        by = actor(request, given)      # 로그인했으면 계정 이름 — 보낸 이름은 쓰지 않는다
        return by or "이름 없음"        # 로그인을 쓰지 않는 서버에서 이름을 주지 않은 경우

    @app.post("/api/recommend/choices")
    def recommend_choice(request: Request, body: RecommendChoiceRequest) -> dict:
        """추천된 그림에 대한 선택을 남기거나(used, rejected) 지운다(none). 같은 사람이 같은 문단·같은 그림을 다시 고르면 바뀐다."""
        import json

        if len(json.dumps(body.detail, ensure_ascii=False)) > DETAIL_LIMIT:
            raise HTTPException(400, "detail이 너무 큽니다")
        try:
            return image_choices.record(store.dsn, by=chooser(request, body.by), image_id=body.image_id, choice=body.choice, text=body.text,
                                        unit_code=body.unit_code, criterion_no=body.criterion_no, rank=body.rank, score=body.score,
                                        detail=body.detail)
        except ImageNotFound as error:
            raise HTTPException(404, str(error)) from None
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @app.post("/api/recommend/choices/mine")
    def recommend_choices_mine(request: Request, body: RecommendRequest) -> dict:
        return {"choices": image_choices.mine(store.dsn, by=chooser(request, ""), text=body.text, unit_code=body.unit_code,
                                              criterion_no=body.criterion_no)}

    @app.get("/api/recommend/choices/export")
    def recommend_choices_export(request: Request) -> dict:
        """선택 기록 전체를 정답 세트로. 다른 사람이 넣은 문단 글이 들어 있으므로 에디터와 직능연 계정만 받는다."""
        manager_only(request, "추천 선택 기록 내려받기는")
        return {**image_choices.export_gold(store.dsn), "counts": image_choices.counts(store.dsn)}
