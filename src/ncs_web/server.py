"""FastAPI 기반 로컬 검수 API. 앱을 조립하고(미들웨어·오류 응답·화면 제공) 기능별 경로는 routes/에 맡긴다. 실행은 ncs_service에 위임한다."""

import argparse
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .common import Services, allowed_origins, error_response
from .routes import export, history, opinion, plan, review, upscale
from .uploads import UploadStore


def create_app(
    *, out_dir: str | Path = "결과",
    dist_dir: str | Path | None = None,
    database_url: str | None = None,
) -> FastAPI:
    """경로는 앱 생성 시 실행 위치를 기준으로 확정한다. dist_dir 생략 시 API만 제공한다.

    저장소는 open_store()가 고른다: database_url이 있으면 PostgreSQL 이력, 없으면 out_dir의 파일 폴더.
    """
    from ncs_service import open_store

    app = FastAPI(title="F02 검수 API")
    app.add_middleware(
        CORSMiddleware, allow_origins=allowed_origins(), allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition", "X-Memo-Summary", "X-Upscale-Summary"],
    )
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
                messages.append("check는 position / toc / overview / knowledge / perform / teaching / evaluation / references / colophon / misc / plan 중 하나여야 합니다")
            else:
                messages.append(f"{field}: {detail['msg']}")
        return error_response(400, "; ".join(messages))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(error.status_code, str(error.detail))

    # 기능별 경로 — 새 기능은 routes/에 모듈을 더하고 여기에 한 줄을 붙인다
    services = Services(store=store, uploads=uploads_store)
    for module in (review, history, export, plan, upscale, opinion):
        module.register(app, services)

    # FastAPI가 자동 추가하는 422 대신 기존 프런트엔드와 호환되는 400을 문서화한다.
    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        schema = default_openapi()
        for route in ("/api/review", "/api/uploads"):
            schema["paths"][route]["post"]["responses"].pop("422", None)
        return schema

    app.openapi = openapi
    if dist is not None and dist.is_dir():
        index_html = dist / "index.html"

        @app.exception_handler(404)
        async def spa_fallback(request: Request, error: HTTPException) -> Response:
            # 화면은 react-router(BrowserRouter)라 /plan 같은 경로를 새로 고침해도 index.html을 줘야 한다.
            # API 404와 파일처럼 생긴 경로(마지막 조각에 '.'이 있는 /결과/x.zip 등)는 그대로 404.
            path = request.url.path
            if (request.method == "GET" and not path.startswith("/api/") and "." not in path.rsplit("/", 1)[-1]
                    and index_html.is_file()):
                return Response(index_html.read_bytes(), media_type="text/html")
            return error_response(404, str(error.detail) if isinstance(error, HTTPException) else "없는 경로입니다")

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
