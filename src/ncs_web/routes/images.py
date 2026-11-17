"""이미지 저작권 DB(REQ-02-010) — 확정 화면용 조회·수정·확정(/api/images)과 추천용 조회(/api/images/recommendable).

PostgreSQL 저장소일 때만 붙는다(/api/health의 image_db가 그 여부). 실제 일은 ncs_service.image_store가 한다.

  GET  /api/images/terms                      허용값 코드 → 이름(화면의 선택 목록)
  GET  /api/images                            관리용 목록 — 모든 그림. status=none은 권리 정보가 없는 그림
  GET  /api/images/{id}                       그림 1건: 수록 위치·권리 정보·증빙·수행준거·변경 이력
  GET  /api/images/{id}/file[?upscaled=true]  그림 파일(확정하려면 봐야 하므로 관리용은 모두 내준다)
  POST /api/images/{id}/rights                권리 정보 수정 {by, version?, rights} — 자동 태깅 상태에서만
  POST /api/images/{id}/confirm               기관 확정 {by, version?}
  POST /api/images/{id}/unconfirm             확정 취소 {by, version?}
  GET  /api/images/recommendable              추천용 목록 — 기관 확정 + 재사용 범위 확인 + 비공개 아님(REQ-02-011, 생성형 AI가 부르는 쪽)
  GET  /api/images/recommendable/{id}/file    추천 목록에 나오는 그림의 파일만

오류: 없는 그림 404, 형식·필수 항목 오류 400(사유를 모두 담는다), 확정된 것 수정·버전 불일치 409.
"""

from fastapi import FastAPI, Query, Response
from starlette.exceptions import HTTPException

from ..common import Services
from ..schemas import ImageActionRequest, ImageRightsRequest

FILE_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}


def register(app: FastAPI, services: Services) -> None:
    store = services.store
    if not store.supports_history:
        return
    from ncs_service import image_store   # psycopg는 PostgreSQL 저장소일 때만 필요하다

    dsn = store.dsn

    def run(action, *args, **kwargs):
        """image_store의 오류를 HTTP 상태로 옮긴다."""
        try:
            return action(dsn, *args, **kwargs)
        except image_store.ImageNotFound as error:
            raise HTTPException(404, str(error)) from None
        except image_store.ImageConflict as error:
            raise HTTPException(409, str(error)) from None
        except image_store.RecordError as error:
            raise HTTPException(400, "; ".join(error.reasons)) from None
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    def file_response(found: tuple[bytes, str]) -> Response:
        content, media_type = found
        return Response(content, media_type=media_type, headers=FILE_HEADERS)

    @app.get("/api/images/terms")
    def image_terms() -> dict:
        return image_store.terms()

    @app.get("/api/images/recommendable")
    def recommendable(module_code: str | None = None, unit_code: str | None = None, keyword: str | None = None,
                      q: str | None = Query(None, max_length=100), kind: str | None = None,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
        return run(image_store.list_recommendable, module_code=module_code, unit_code=unit_code, keyword=keyword,
                   q=q, kind=kind, limit=limit, offset=offset)

    @app.get("/api/images/recommendable/{image_id}/file")
    def recommendable_file(image_id: str, upscaled: bool = False) -> Response:
        return file_response(run(image_store.recommendable_file, image_id, upscaled=upscaled))

    @app.get("/api/images")
    def images(status: str | None = None, category: str | None = None, license_scheme: str | None = None,
               kogl_type: int | None = Query(None, ge=0, le=4), reuse_scope: str | None = None,
               module_code: str | None = None, unit_code: str | None = None, keyword: str | None = None,
               q: str | None = Query(None, max_length=100), kind: str | None = None,
               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
        return run(image_store.list_images, status=status, category=category, license_scheme=license_scheme,
                   kogl_type=kogl_type, reuse_scope=reuse_scope, module_code=module_code, unit_code=unit_code,
                   keyword=keyword, q=q, kind=kind, limit=limit, offset=offset)

    @app.get("/api/images/{image_id}")
    def image_detail(image_id: str) -> dict:
        return run(image_store.get_image, image_id)

    @app.get("/api/images/{image_id}/file")
    def image_file(image_id: str, upscaled: bool = False) -> Response:
        return file_response(run(image_store.image_file, image_id, upscaled=upscaled))

    @app.post("/api/images/{image_id}/rights")
    def image_rights(image_id: str, body: ImageRightsRequest) -> dict:
        return run(image_store.update_rights, image_id, body.rights, by=body.by, version=body.version)

    @app.post("/api/images/{image_id}/confirm")
    def image_confirm(image_id: str, body: ImageActionRequest) -> dict:
        return run(image_store.confirm, image_id, by=body.by, version=body.version)

    @app.post("/api/images/{image_id}/unconfirm")
    def image_unconfirm(image_id: str, body: ImageActionRequest) -> dict:
        return run(image_store.unconfirm, image_id, by=body.by, version=body.version)
