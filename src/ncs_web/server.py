"""FastAPI 기반 로컬 검수 API. 업로드·HTTP 응답을 맡고 실행은 ncs_service에 위임한다."""

import argparse
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
                payload = _run(kept.files, check, module_code, group or kept.group_id)
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
