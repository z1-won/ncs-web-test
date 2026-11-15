"""검수 이력 — 단독 실행(/api/reviews)과 전체 실행 묶음(/api/groups). 저장소가 이력을 지원할 때(PostgreSQL)만 붙는다."""

from urllib.parse import quote

from fastapi import FastAPI, Query, Response
from starlette.exceptions import HTTPException

from ..common import Services
from ..schemas import CheckName


def register(app: FastAPI, services: Services) -> None:
    store = services.store
    if store.supports_history:

        @app.get("/api/reviews")
        def reviews(module_code: str | None = None, check: CheckName | None = None,
                    verdict: str | None = None, standalone: bool = False, limit: int = Query(50, ge=1, le=100),
                    offset: int = Query(0, ge=0)) -> list[dict]:
            # standalone=true: 전체 실행 묶음에 속한 건은 빼고 단독 실행만(묶음은 /api/groups가 한 줄로 보여 준다)
            return store.list_reviews(module_code=module_code, check=check, verdict=verdict, standalone=standalone,
                                      limit=limit, offset=offset)

        @app.get("/api/groups")
        def groups(module_code: str | None = None, limit: int = Query(50, ge=1, le=100),
                   offset: int = Query(0, ge=0)) -> list[dict]:
            return store.list_groups(module_code=module_code, limit=limit, offset=offset)

        @app.get("/api/groups/{group_id}")
        def group_detail(group_id: str) -> dict:
            found = store.get_group(group_id)
            if found is None:
                raise HTTPException(404, "전체 실행 이력을 찾을 수 없습니다")
            return found

        @app.delete("/api/groups/{group_id}", status_code=204)
        def group_delete(group_id: str) -> Response:
            if not store.delete_group(group_id):
                raise HTTPException(404, "전체 실행 이력을 찾을 수 없습니다")
            return Response(status_code=204)

        @app.get("/api/reviews/{run_id}")
        def review_detail(run_id: str) -> dict:
            found = store.get_review(run_id)
            if found is None:
                raise HTTPException(404, "검수 이력을 찾을 수 없습니다")
            return found

        @app.delete("/api/reviews/{run_id}", status_code=204)
        def review_delete(run_id: str) -> Response:
            if not store.delete_review(run_id):
                raise HTTPException(404, "검수 이력을 찾을 수 없습니다")
            return Response(status_code=204)

        @app.get("/api/reviews/{run_id}/zip")
        def review_zip(run_id: str) -> Response:
            exported = store.export_zip(run_id)
            if exported is None:
                raise HTTPException(404, "검수 이력을 찾을 수 없습니다")
            content, filename = exported
            return Response(content, media_type="application/zip", headers={
                "Content-Disposition": f"attachment; filename=review-{quote(run_id)}.zip; filename*=UTF-8''{quote(filename)}",
            })
