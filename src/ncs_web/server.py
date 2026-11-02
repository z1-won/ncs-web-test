"""FastAPI 기반 로컬 검수 API. 업로드·HTTP 응답을 맡고 실행은 ncs_service에 위임한다."""

import argparse
import json
import os
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from .uploads import UploadStore

CheckName = Literal["position", "toc", "overview", "knowledge", "perform", "teaching", "evaluation", "references", "colophon", "misc"]
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


class SavedPaths(BaseModel):
    folder: str
    zip: str


class ReviewResponse(BaseModel):
    id: str | None = None
    group: str | None = None   # 전체 실행 묶음 id(업로드 토큰으로 실행했을 때)
    check: CheckName
    module_code: str
    요약: dict[str, Any]
    검수확인서: list[dict[str, Any]]
    진단: dict[str, Any]
    지적사항: list[dict[str, Any]]
    전체: list[dict[str, Any]]
    저장: SavedPaths | None = None


class ErrorResponse(BaseModel):
    error: str
    traceback: str | None = None


class SheetExportRequest(BaseModel):
    """확인서 내보내기 입력 — 화면이 가진 확인서 행을 그대로 보낸다(DB 모드든 파일 모드든, 저장 전 결과든 같은 길)."""

    module_code: str
    rows: list[dict[str, Any]]          # 여러 구성요소의 검수확인서 행을 이어 붙인 것
    created_at: str | None = None


class UploadResponse(BaseModel):
    """전체 실행용 업로드 토큰. upload를 /api/review에 files 대신 넘기면 같은 파일로 검수를 여러 번 돌릴 수 있다."""

    upload: str
    group: str                    # 이 토큰으로 실행한 검수들의 이력 묶음 id
    files: list[str]
    roles: dict[str, str | None]  # 내용으로 판별한 역할 → 파일 이름. plan이 None이면 개발계획서 없음
    expires_in: int               # 초


def error_response(status: int, message: str, **extra: Any) -> JSONResponse:
    # charset을 명시해 브라우저가 JSON을 직접 표시할 때 한국어 메시지가 깨지지 않게 한다.
    return JSONResponse({"error": message, **extra}, status_code=status, headers=CORS_HEADERS,
                        media_type="application/json; charset=utf-8")


def create_app(
    *, out_dir: str | Path = "결과",
    dist_dir: str | Path | None = None,
    database_url: str | None = None,
) -> FastAPI:
    """경로는 앱 생성 시 실행 위치를 기준으로 확정한다. dist_dir 생략 시 API만 제공한다.

    저장소는 open_store()가 고른다: database_url이 있으면 PostgreSQL 이력, 없으면 out_dir의 파일 폴더.
    """
    from ncs_core import select_documents
    from ncs_service import ReviewRequest, execute_review, open_store
    from ncs_service.registry import ENGINES, describe_engines

    app = FastAPI(title="F02 검수 API")
    dist = Path(dist_dir).expanduser().resolve() if dist_dir is not None else None
    store = open_store(out_dir=out_dir, database_url=database_url)
    store.prepare()
    uploads_store = UploadStore()
    app.state.uploads = uploads_store

    @app.post("/api/export/sheet", responses={400: {"model": ErrorResponse}})
    def export_sheet(body: SheetExportRequest, format: Literal["xlsx", "hwpx"] = Query("xlsx")) -> Response:
        """F02 검수 확인서 파일. xlsx(열람·편집) 또는 hwpx(원본 양식에 ✓·비고를 채운 제출본)."""
        from ncs_service import export

        code = body.module_code.strip() or "모듈"
        meta = export.module_meta(code)
        if body.created_at:
            meta["실행시각"] = body.created_at
        try:
            if format == "hwpx":
                content, media = export.build_hwpx(code, body.rows, meta=meta), "application/hwp+zip"
            else:
                content, media = export.build_xlsx(code, body.rows, meta=meta), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except ValueError as error:
            return error_response(400, str(error))
        filename = f"F02_검수확인서_{code}.{format}"
        return Response(content, media_type=media, headers={
            **CORS_HEADERS,
            "Content-Disposition": f"attachment; filename=F02_sheet_{quote(code)}.{format}; filename*=UTF-8''{quote(filename)}",
        })

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        messages = []
        for detail in error.errors():
            field = str(detail["loc"][-1])
            if field in ("files", "upload") and detail["type"] == "missing":
                messages.append("업로드된 파일이 없습니다")
            elif field == "check":
                messages.append("check는 position / toc / overview / knowledge / perform / teaching / evaluation / references / colophon / misc 중 하나여야 합니다")
            else:
                messages.append(f"{field}: {detail['msg']}")
        return error_response(400, "; ".join(messages))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(error.status_code, str(error.detail))

    @app.get("/api/health")
    def health(response: Response) -> dict[str, Any]:
        response.headers.update(CORS_HEADERS)
        # history: 이력 API(/api/reviews)가 등록되어 있는가. 화면이 이력 영역을 켤지 결정하는 데 쓴다.
        # engines: 검수 항목마다 구성요소 이름과 구현된 확인서 항목 번호 — 화면의 선택 목록 글이 여기서 나온다
        return {"ok": True, "checks": list(ENGINES), "engines": describe_engines(), "history": store.supports_history}

    @app.options("/{path:path}", include_in_schema=False)
    def options(path: str) -> Response:
        return Response(status_code=204, headers={
            **CORS_HEADERS,
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })

    @app.post(
        "/api/uploads", response_model=UploadResponse,
        responses={400: {"model": ErrorResponse}},
    )
    def create_upload(response: Response, files: Annotated[list[UploadFile], File()]) -> UploadResponse | JSONResponse:
        """전체 실행 1단계: 파일을 한 번만 올려 두고 토큰을 받는다. 역할(원고/개발계획서)을 내용으로 판별해 함께 알려 준다."""
        try:
            upload = uploads_store.put([(item.filename or "", item.file.read()) for item in files])
            try:
                # 역할을 미리 확인해 두면 화면이 '개발계획서 없음 → 위치 건너뜀'을 실행 전에 알 수 있다
                documents = select_documents([path for _, path in upload.files], required=())
            except ValueError:
                uploads_store.release(upload.token)
                raise
            names = dict(upload.files)
            by_path = {str(path): name for name, path in upload.files}
            upload.roles = {role: by_path.get(str(document.path)) for role, document in documents.items()}
            upload.roles.setdefault("manuscript", None)
            upload.roles.setdefault("plan", None)
            response.headers.update(CORS_HEADERS)
            return UploadResponse(upload=upload.token, group=upload.group_id, files=list(names),
                                  roles=upload.roles, expires_in=int(uploads_store.ttl))
        except ValueError as error:
            return error_response(400, str(error))

    @app.post("/api/export/annotated", responses={400: {"model": ErrorResponse}})
    def export_annotated(
        rows: Annotated[str, Form()],
        upload: Annotated[str, Form()] = "",
        run_id: Annotated[str, Form()] = "",
        module_code: Annotated[str, Form()] = "",
        created_at: Annotated[str, Form()] = "",
    ) -> Response:
        """원고 hwpx에 지적사항을 한글 메모로 단 파일. 원고는 둘 중 하나로 찾는다 — upload=업로드 토큰(방금 올린 원고),
        run_id=이력 실행 id(실행과 함께 보관된 원고; PostgreSQL 이력에서만). rows=체크리스트 행 JSON 배열,
        created_at=검사 실행 시각(ISO, 메모 날짜로 쓴다. 없으면 내보내는 시각)."""
        from ncs_core import detect_role, load_document
        from ncs_service.annotate import annotate_hwpx

        try:
            parsed = json.loads(rows)
            if not isinstance(parsed, list):
                raise ValueError
        except ValueError:
            return error_response(400, "rows는 체크리스트 행의 JSON 배열이어야 합니다")
        # 원고 찾기: 업로드 토큰(아직 살아 있으면) → 이력에 보관된 원고(run_id). 토큰이 만료돼도 run_id가 있으면 이어서 쓴다.
        name, source = None, None
        kept = uploads_store.get(upload) if upload else None
        if kept is not None:
            for file_name, path in kept.files:
                if file_name.lower().endswith(".hwpx") and detect_role(load_document(path).sections) == "manuscript":
                    name, source = file_name, path.read_bytes()
                    break
            if source is None:
                return error_response(400, "메모는 hwpx 원고에만 달 수 있습니다(hwp는 한글에서 hwpx로 저장 후 다시 올리세요)")
        elif run_id:
            found = store.get_manuscript(run_id)
            if found is None:
                return error_response(404, "이 실행에는 보관된 원고 hwpx가 없습니다(원고 보관 기능 이전의 실행이거나 hwp 원고, 또는 파일 저장소 모드)")
            name, source = found
        elif upload:
            return error_response(400, "업로드 토큰이 없거나 만료되었습니다. 파일을 다시 올려 주세요")
        else:
            return error_response(400, "upload 토큰 또는 run_id가 필요합니다")
        try:
            content, summary = annotate_hwpx(source, parsed, created_at=created_at or None)
        except ValueError as error:
            return error_response(400, str(error))
        stem = Path(name).stem
        filename = f"{stem}_검수메모.hwpx"
        return Response(content, media_type="application/hwp+zip", headers={
            **CORS_HEADERS,
            "Content-Disposition": f"attachment; filename=annotated_{quote(module_code or 'manuscript')}.hwpx; filename*=UTF-8''{quote(filename)}",
            "X-Memo-Summary": json.dumps(summary),
        })

    @app.delete("/api/uploads/{token}", status_code=204)
    def delete_upload(token: str) -> Response:
        """전체 실행이 끝나면 화면이 바로 지운다. 지우지 않아도 만료 시간이 지나면 정리된다."""
        if not uploads_store.release(token):
            raise HTTPException(404, "업로드 토큰이 없거나 만료되었습니다")
        return Response(status_code=204, headers=CORS_HEADERS)

    @app.post(
        "/api/review", response_model=ReviewResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    def review(
        response: Response,
        files: Annotated[list[UploadFile] | None, File()] = None,
        check: Annotated[CheckName, Form()] = "position",
        module_code: Annotated[str, Form()] = "",
        upload: Annotated[str, Form()] = "",
        group: Annotated[str, Form()] = "",
    ) -> ReviewResponse | JSONResponse:
        """files로 직접 올리거나, /api/uploads 토큰(upload)으로 올려 둔 파일을 쓴다. group은 이력 묶음 id(토큰 응답의 group)."""
        # 동기 엔진은 일반 def 경로 함수의 스레드풀에서 실행한다.
        try:
            if upload:
                kept = uploads_store.get(upload)
                if kept is None:
                    raise ValueError("업로드 토큰이 없거나 만료되었습니다. 파일을 다시 올려 주세요")
                if group and group != kept.group_id:
                    raise ValueError("group이 업로드 토큰의 묶음 id와 다릅니다")
                # group을 보내지 않으면 단독 실행(묶음 없음) — 화면이 파일을 미리 올려 두고 토큰만으로 1건 돌리는 경우
                payload = _run(kept.files, check, module_code, group or None)
            else:
                if group:
                    raise ValueError("group은 upload 토큰과 함께만 쓸 수 있습니다")
                with tempfile.TemporaryDirectory(prefix="ncs_upload_") as folder:
                    saved = []
                    for index, item in enumerate(files or []):
                        if not item.filename:
                            continue
                        name = Path(item.filename).name
                        if name in ("", ".", ".."):
                            raise ValueError("유효하지 않은 업로드 파일명입니다")
                        # 동일 파일명도 서로 덮어쓰지 않으며 모듈 코드 추출용 원래 이름은 보존한다.
                        directory = Path(folder) / str(index)
                        directory.mkdir()
                        path = directory / name
                        with path.open("wb") as target:
                            shutil.copyfileobj(item.file, target)
                        if path.stat().st_size:
                            saved.append((name, path))
                    if not saved:
                        raise ValueError("업로드된 파일이 없습니다")
                    payload = _run(saved, check, module_code, None)
        except ValueError as error:
            return error_response(400, str(error))
        except Exception as error:
            return error_response(500, f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        response.headers.update(CORS_HEADERS)
        return payload

    def _run(saved: list[tuple[str, Path]], check: str, module_code: str, group_id: str | None) -> ReviewResponse:
        paths = tuple(path for _, path in saved)
        execution = execute_review(ReviewRequest(paths, check, module_code.strip()))
        result = execution.result
        stored = store.save(execution, saved, group_id=group_id)
        saved_paths = (
            SavedPaths(folder=str(stored.directory), zip=str(stored.zip_path))
            if stored.directory is not None else None
        )
        return ReviewResponse(
            id=stored.run_id, group=group_id, check=execution.check, module_code=result.module_code, 요약=stored.summary,
            검수확인서=result.sheet, 진단=result.diagnostics, 지적사항=result.findings,
            전체=result.checklist, 저장=saved_paths,
        )

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
                "Content-Disposition": f"attachment; filename=review-{run_id}.zip; filename*=UTF-8''{quote(filename)}",
            })

    # FastAPI가 자동 추가하는 422 대신 기존 프런트엔드와 호환되는 400을 문서화한다.
    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        schema = default_openapi()
        for route in ("/api/review", "/api/uploads"):
            schema["paths"][route]["post"]["responses"].pop("422", None)
        return schema

    app.openapi = openapi
    if dist is not None and dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    else:
        @app.get("/", include_in_schema=False)
        def no_frontend() -> JSONResponse:
            message = (
                f"화면 빌드 폴더를 찾을 수 없습니다: {dist}"
                if dist is not None
                else "화면 빌드 폴더가 지정되지 않았습니다"
            )
            return error_response(404, message + ". --dist로 빌드 경로를 지정하거나 Vite dev 서버로 여세요")
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="F02 FastAPI 로컬 서버")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--out", default="결과", help="결과 저장 폴더 (기본: 실행 위치의 결과/)")
    parser.add_argument("--dist", help="React 빌드 폴더. 생략하면 API만 제공")
    args = parser.parse_args()
    try:
        app = create_app(out_dir=args.out, dist_dir=args.dist, database_url=os.getenv("DATABASE_URL"))
    except ValueError as error:
        parser.exit(2, f"서버 실행 실패: {error}\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
