"""이미지 저작권 DB(REQ-02-010) — 확정 화면용 조회·수정·확정(/api/images)과 추천용 조회(/api/images/recommendable).

PostgreSQL 저장소일 때만 붙는다(/api/health의 image_db가 그 여부). 실제 일은 ncs_service.images.image_store가 한다.

  GET  /api/images/terms                      허용값 코드 → 이름(화면의 선택 목록)
  GET  /api/images                            관리용 목록 — 모든 그림. status=none은 권리 정보가 없는 그림.
                                              description=none|unchecked|checked로 그림 설명의 확인 여부를 거른다
  GET  /api/images/{id}                       그림 1건: 수록 위치·권리 정보·증빙·수행준거·변경 이력
  GET  /api/images/{id}/file[?upscaled=true]  그림 파일(확정하려면 봐야 하므로 관리용은 모두 내준다)
  POST /api/images/{id}/rights                권리 정보 수정 {by, version?, rights} — 자동 태깅 상태에서만
  POST /api/images/{id}/confirm               기관 확정 {by, version?}
  POST /api/images/{id}/unconfirm             확정 취소 {by, version?}
  POST /api/images/{id}/evidence              증빙 1건 직접 등록 {by, kind, file_ref?, submitted_on?, note?} — 서류 파일은 받지 않는다
  POST /api/images/{id}/evidence/{증빙 id}/delete   증빙 1건 삭제 {by}
  POST /api/images/{id}/description           그림 설명 한 벌을 사람이 읽고 확인 {by, engine, check, kind, scene, objects, visible_text, keywords}
                                              — 고친 내용이 있으면 함께 저장. check=false면 확인만 푼다(REQ-02-011 설명 색인)
  POST /api/images/load                       레코드 JSON 1개 + 그림 파일들을 올려 적재(또는 check_only로 형식만 검사).
                                              이미지 레코드(docs/IMAGE_RECORD.md)와 공공누리 수집 JSON(0.1-PoC, REQ-02-012) 둘 다 받는다
  GET  /api/images/recommendable              추천용 목록 — 기관 확정 + 재사용 범위 확인 + 비공개 아님(REQ-02-011, 생성형 AI가 부르는 쪽)
  GET  /api/images/recommendable/{id}/file    추천 목록에 나오는 그림의 파일만

오류: 없는 그림·증빙 404, 형식·필수 항목 오류 400(사유를 모두 담는다), 확정된 것 수정·버전 불일치·같은 증빙 중복 409.
"""

import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Query, Request, Response, UploadFile
from starlette.exceptions import HTTPException

from ..common import Services, actor
from ..schemas import ImageActionRequest, ImageDescriptionRequest, ImageEvidenceRequest, ImageRightsRequest

LOAD_MAX_BYTES = 50 << 20     # 한 번에 올리는 레코드 JSON + 그림 파일 합계 상한(50MB)
LOAD_MAX_FILES = 300
FILE_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}


def register(app: FastAPI, services: Services) -> None:
    store = services.store
    if not store.supports_history:
        return
    from ncs_service.images import image_store   # psycopg는 PostgreSQL 저장소일 때만 필요하다

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

    def embed_after_load() -> dict | None:
        """그림 임베딩이 켜져 있으면 방금 넣은 그림의 벡터를 계산한다(이 컴퓨터에서, 외부 전송 없음). 꺼져 있으면 None.
        실패해도 적재는 이미 끝났으므로 오류로 만들지 않고 까닭만 돌려준다 — 나중에 python -m ncs_service.images.image_embed로 채울 수 있다."""
        from ncs_recommend import embed
        from ncs_service.images import image_embed

        if not embed.model_name():
            return None
        try:
            return image_embed.embed_missing(dsn)
        except Exception as error:      # noqa: BLE001
            return {"모델": embed.model_name(), "오류": str(error)[:300]}

    def file_response(found: tuple[bytes, str]) -> Response:
        content, media_type = found
        return Response(content, media_type=media_type, headers=FILE_HEADERS)

    @app.get("/api/images/terms")
    def image_terms() -> dict:
        return image_store.terms()

    @app.post("/api/images/load")
    def image_load(request: Request, files: Annotated[list[UploadFile], File()], by: Annotated[str, Form()] = "",
                   check_only: Annotated[bool, Form()] = False) -> dict:
        """레코드 JSON 1개와 그 레코드가 가리키는 그림 파일들을 함께 올린다. 그림은 파일 이름으로 짝짓는다(폴더 경로는 무시).

        check_only면 DB에 넣지 않고 형식만 검사한다. 응답은 적재 보고서(전체·적재·거부 사유·필수 항목 충족률) 또는 검사 결과.
        """
        from ncs_service.images import image_db, kogl_import
        from ncs_service.images.image_records import read_records

        named = [item for item in files if item.filename]
        if len(named) > LOAD_MAX_FILES:
            raise HTTPException(400, f"한 번에 {LOAD_MAX_FILES}개까지 올릴 수 있습니다")
        if not check_only:
            editor_only(request)
        by = actor(request, by)      # 로그인했으면 계정 이름 — 보낸 이름은 쓰지 않는다
        if not check_only and not by:
            raise HTTPException(400, "by(적재한 사람)가 필요합니다 — 변경 이력에 남습니다")
        with tempfile.TemporaryDirectory(prefix="ncs_image_load_") as folder:
            base, total, record_files = Path(folder), 0, []
            for item in named:
                name = Path(item.filename.replace("\\", "/")).name     # 브라우저가 보낸 경로는 버리고 이름만 쓴다
                if not name or name in (".", "..") or (base / name).exists():
                    raise HTTPException(400, f"파일 이름이 겹치거나 쓸 수 없습니다: {item.filename}")
                data = item.file.read(LOAD_MAX_BYTES - total + 1)
                total += len(data)
                if total > LOAD_MAX_BYTES:
                    raise HTTPException(400, f"올린 파일의 합계가 {LOAD_MAX_BYTES >> 20}MB를 넘습니다")
                (base / name).write_bytes(data)
                if name.lower().endswith(".json"):
                    record_files.append(base / name)
            if len(record_files) != 1:
                raise HTTPException(400, f"레코드 JSON 파일을 1개 올려 주세요(지금 {len(record_files)}개)")
            try:
                data = json.loads(record_files[0].read_text(encoding="utf-8-sig"))
            except (ValueError, UnicodeDecodeError) as error:
                raise HTTPException(400, f"레코드 JSON을 읽지 못했습니다: {error}") from None
            if kogl_import.is_dataset(data):      # 공공누리 수집 JSON(0.1-PoC, REQ-02-012) — 이미지 레코드로 바꿔 넣는다
                try:
                    report = {"check_only": check_only,
                              **kogl_import.run(dsn, data, base_dir=base, by=by, check_only=check_only)}
                    return report if check_only else {**report, "그림 임베딩": embed_after_load()}
                except ValueError as error:
                    raise HTTPException(400, str(error)) from None
            try:
                records, _ = read_records(record_files[0])
            except ValueError as error:      # schema 불일치·records 모양
                raise HTTPException(400, f"레코드 JSON을 읽지 못했습니다: {error}") from None
            records = image_db.flatten_file_names(records)
            if check_only:
                return {"check_only": True, "형식": "이미지 레코드", **image_db.check_records(records, base_dir=base), "안내": []}
            return {"check_only": False, "형식": "이미지 레코드",
                    **image_db.load_records(dsn, records, changed_by=by, base_dir=base).as_dict(), "안내": [],
                    "그림 임베딩": embed_after_load()}

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
               q: str | None = Query(None, max_length=100), kind: str | None = None, description: str | None = None,
               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
        return run(image_store.list_images, status=status, category=category, license_scheme=license_scheme,
                   kogl_type=kogl_type, reuse_scope=reuse_scope, module_code=module_code, unit_code=unit_code,
                   keyword=keyword, q=q, kind=kind, description=description or None, limit=limit, offset=offset)

    @app.get("/api/images/{image_id}")
    def image_detail(image_id: str) -> dict:
        return run(image_store.get_image, image_id)

    @app.get("/api/images/{image_id}/file")
    def image_file(image_id: str, upscaled: bool = False) -> Response:
        return file_response(run(image_store.image_file, image_id, upscaled=upscaled))

    def editor_only(request: Request) -> None:
        """이미지 저작권 DB를 바꾸는 일(적재, 권리 정보 수정, 확정, 증빙)은 에디터와 직능연 계정만 한다. 보는 것은 로그인한 누구나."""
        from ncs_service.workflow.flow import MANAGER_ROLES

        account = getattr(request.state, "account", None)
        if account is not None and account.get("role") not in MANAGER_ROLES:
            raise HTTPException(403, "이미지 저작권 DB를 바꾸는 일은 에디터와 직능연 계정만 할 수 있습니다")

    def who(request: Request, given: str) -> str:
        editor_only(request)
        name = actor(request, given)
        if not name:
            raise HTTPException(400, "변경한 사람을 알 수 없습니다. 로그인해 주세요")
        return name

    @app.post("/api/images/{image_id}/rights")
    def image_rights(image_id: str, body: ImageRightsRequest, request: Request) -> dict:
        return run(image_store.update_rights, image_id, body.rights, by=who(request, body.by), version=body.version)

    @app.post("/api/images/{image_id}/confirm")
    def image_confirm(image_id: str, body: ImageActionRequest, request: Request) -> dict:
        return run(image_store.confirm, image_id, by=who(request, body.by), version=body.version)

    @app.post("/api/images/{image_id}/unconfirm")
    def image_unconfirm(image_id: str, body: ImageActionRequest, request: Request) -> dict:
        return run(image_store.unconfirm, image_id, by=who(request, body.by), version=body.version)

    @app.post("/api/images/{image_id}/description")
    def image_description(image_id: str, body: ImageDescriptionRequest, request: Request) -> dict:
        """그림 설명을 사람이 읽고 확인한다(고친 내용 저장 포함). 추천은 사람이 확인한 설명을 먼저 읽는다."""
        by = who(request, body.by)
        if not body.check:
            return run(image_store.uncheck_description, image_id, body.engine, by=by)
        description = {"kind": body.kind, "scene": body.scene, "objects": body.objects, "visible_text": body.visible_text, "keywords": body.keywords}
        return run(image_store.check_description, image_id, body.engine, description, by=by)

    @app.post("/api/images/{image_id}/evidence")
    def image_evidence_add(image_id: str, body: ImageEvidenceRequest, request: Request) -> dict:
        return run(image_store.register_evidence, image_id, body.kind, by=who(request, body.by), file_ref=body.file_ref,
                   submitted_on=body.submitted_on, note=body.note)

    @app.post("/api/images/{image_id}/evidence/{evidence_id}/delete")
    def image_evidence_remove(image_id: str, evidence_id: str, body: ImageActionRequest, request: Request) -> dict:
        return run(image_store.remove_evidence, image_id, evidence_id, by=who(request, body.by))
