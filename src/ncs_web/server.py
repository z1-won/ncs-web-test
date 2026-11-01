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

CheckName = Literal["position", "toc", "overview", "knowledge", "perform", "teaching", "evaluation"]
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


class SavedPaths(BaseModel):
    folder: str
    zip: str


class ReviewResponse(BaseModel):
    id: str | None = None
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
    from ncs_service import ReviewRequest, execute_review, open_store

    app = FastAPI(title="F02 검수 API")
    dist = Path(dist_dir).expanduser().resolve() if dist_dir is not None else None
    store = open_store(out_dir=out_dir, database_url=database_url)
    store.prepare()

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        messages = []
        for detail in error.errors():
            field = str(detail["loc"][-1])
            if field == "files" and detail["type"] == "missing":
                messages.append("업로드된 파일이 없습니다")
            elif field == "check":
                messages.append("check는 position / toc / overview / knowledge / perform / teaching / evaluation 중 하나여야 합니다")
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
        return {"ok": True, "checks": ["position", "toc", "overview", "knowledge", "perform", "teaching", "evaluation"], "history": store.supports_history}

    @app.options("/{path:path}", include_in_schema=False)
    def options(path: str) -> Response:
        return Response(status_code=204, headers={
            **CORS_HEADERS,
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })

    @app.post(
        "/api/review", response_model=ReviewResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    def review(
        response: Response,
        files: Annotated[list[UploadFile], File()],
        check: Annotated[CheckName, Form()] = "position",
        module_code: Annotated[str, Form()] = "",
    ) -> ReviewResponse | JSONResponse:
        # 동기 엔진은 일반 def 경로 함수의 스레드풀에서 실행한다.
        try:
            with tempfile.TemporaryDirectory(prefix="ncs_upload_") as folder:
                paths = []
                uploads = []
                for index, upload in enumerate(files):
                    if not upload.filename:
                        continue
                    name = Path(upload.filename).name
                    if name in ("", ".", ".."):
                        raise ValueError("유효하지 않은 업로드 파일명입니다")
                    # 동일 파일명도 서로 덮어쓰지 않으며 모듈 코드 추출용 원래 이름은 보존한다.
                    directory = Path(folder) / str(index)
                    directory.mkdir()
                    path = directory / name
                    with path.open("wb") as target:
                        shutil.copyfileobj(upload.file, target)
                    if path.stat().st_size:
                        paths.append(path)
                        uploads.append((name, path))
                if not paths:
                    raise ValueError("업로드된 파일이 없습니다")
                execution = execute_review(ReviewRequest(tuple(paths), check, module_code.strip()))
                result = execution.result
                stored = store.save(execution, uploads)
                saved_paths = (
                    SavedPaths(folder=str(stored.directory), zip=str(stored.zip_path))
                    if stored.directory is not None else None
                )
                payload = ReviewResponse(
                    id=stored.run_id, check=execution.check, module_code=result.module_code, 요약=stored.summary,
                    검수확인서=result.sheet, 진단=result.diagnostics, 지적사항=result.findings,
                    전체=result.checklist, 저장=saved_paths,
                )
        except ValueError as error:
            return error_response(400, str(error))
        except Exception as error:
            return error_response(500, f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        response.headers.update(CORS_HEADERS)
        return payload

    if store.supports_history:

        @app.get("/api/reviews")
        def reviews(module_code: str | None = None, check: CheckName | None = None,
                    verdict: str | None = None, limit: int = Query(50, ge=1, le=100),
                    offset: int = Query(0, ge=0)) -> list[dict]:
            return store.list_reviews(module_code=module_code, check=check, verdict=verdict, limit=limit, offset=offset)

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
        schema["paths"]["/api/review"]["post"]["responses"].pop("422", None)
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
