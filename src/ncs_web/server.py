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

from . import auth
from .common import Services, allowed_origins, error_response, logger
from .routes import (aiimage, cases, export, figures, history, images, llm_review, opinion, plan, progress, recommend, review, rights, sources,
                     suggest, upscale, volume)
from .uploads import UploadStore


# 화면은 이 서버가 내는 파일만 쓴다(외부 CDN 없음). 그림 미리 보기는 data:·blob: 주소를 쓰고, KRDS와 React가 style 속성을 쓴다.
# 다른 사이트의 틀 안에 넣지 못하게 하고(클릭재킹), 파일 형식을 내용으로 추측하지 않게 하며, 나가는 링크에 주소를 싣지 않는다.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
                                "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"),
}


# 입력 칸 이름(코드) → 화면의 이름. 입력 오류를 이용자가 읽을 말로 알리는 데 쓴다(없는 이름은 '입력값')
FIELD_NAMES = {
    "unit_price": "원고료 단가", "contract_pages": "계약 분량", "manual_pages": "수작업으로 센 쪽수", "manuscript": "원고",
    "previous": "기존 원고", "print_copy": "출력본 PDF", "print_pdf": "출력본 PDF", "opinions": "의견서", "rounds": "의견서 차수",
    "forms": "제출 서류", "text": "문장", "kind": "종류", "file": "파일", "base": "기준 파일", "target": "대상 파일", "plan": "개발계획서",
    "duty": "세분류 코드", "module_code": "모듈 코드", "by": "변경한 사람", "rows": "결과 행", "tasks": "검토 항목", "limit": "개수",
}
FILE_FIELDS = {"manuscript", "previous", "print_copy", "print_pdf", "opinions", "forms", "file", "base", "target", "plan"}


def _particle(word: str, with_final: str, without: str) -> str:
    """받침에 맞는 조사('단가는', '의견서를')."""
    last = word.rstrip(")")[-1:] if word else ""
    final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_final if final else without)


def _input_message(field: str, detail: dict) -> str:
    """요청 검증 오류 한 건 → 한국어 안내. 영어 문구와 내부 칸 이름을 그대로 보이지 않는다(2026-11-23 QA)."""
    name = FIELD_NAMES.get(field, "입력값")
    kind = detail.get("type", "")
    limit = (detail.get("ctx") or {})
    if kind == "missing":
        return f"{_particle(name, '을', '를')} 올려 주세요" if field in FILE_FIELDS else f"{_particle(name, '을', '를')} 넣어 주세요"
    if kind in ("int_parsing", "float_parsing", "int_from_float", "decimal_parsing"):
        return f"{_particle(name, '은', '는')} 숫자로 적어 주세요"
    if kind in ("greater_than", "greater_than_equal"):
        bound = limit.get("gt", limit.get("ge"))
        return f"{_particle(name, '은', '는')} {bound:g}보다 커야 합니다" if kind == "greater_than" else f"{_particle(name, '은', '는')} {bound:g} 이상이어야 합니다"
    if kind in ("less_than", "less_than_equal"):
        bound = limit.get("lt", limit.get("le"))
        return f"{_particle(name, '은', '는')} {bound:g}보다 작아야 합니다" if kind == "less_than" else f"{_particle(name, '은', '는')} {bound:g} 이하여야 합니다"
    if kind.startswith("string_too_long") or kind == "too_long":
        return f"{_particle(name, '이', '가')} 너무 깁니다"
    return f"{_particle(name, '의', '의')} 값이 올바르지 않습니다"


def create_app(
    *, out_dir: str | Path = "결과",
    dist_dir: str | Path | None = None,
    database_url: str | None = None,
    data_dir: str | Path | None = None,
    require_login: bool | None = None,
) -> FastAPI:
    """경로는 앱 생성 시 실행 위치를 기준으로 확정한다. dist_dir 생략 시 API만 제공한다.

    저장소는 open_store()가 고른다: database_url이 있으면 PostgreSQL 이력, 없으면 out_dir의 파일 폴더.
    data_dir는 기준정보 폴더(ncs_core.refdata) — 운영 중에 NCS·법제처에서 받아 온 기준정보를 두는 곳. 주지 않으면(None)
    환경 변수 NCS_DATA_DIR를 따르고, 그것도 없으면 운영 중 조회를 하지 않는다(패키지에 든 표만 쓴다).
    require_login: 로그인한 사람만 /api를 쓰게 할지(ncs_web.auth). 주지 않으면(None) 데이터베이스가 있을 때 켠다 — 계정을 둘 곳이
    있어야 하기 때문이다. DB 없이 띄운 서버는 로그인이 없고 이 컴퓨터(127.0.0.1)에서만 열린다. False는 테스트에서만 쓴다.
    """
    from ncs_core import refdata
    from ncs_service import open_store

    refdata.set_data_dir(data_dir)

    # API 문서(/docs, /redoc, /openapi.json)는 경로와 인자를 모두 보여 주므로 기본으로 닫는다(KISA 3장 4. 관리자페이지 노출).
    # 로그인 검사는 /api/ 아래만 보므로 열어 두면 로그인 없이 보인다. 개발할 때만 NCS_WEB_DEBUG=1로 연다.
    debug = os.getenv("NCS_WEB_DEBUG") == "1"
    app = FastAPI(title="F02 검수 API", docs_url="/docs" if debug else None, redoc_url="/redoc" if debug else None,
                  openapi_url="/openapi.json" if debug else None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        """모든 응답에 보안 머리글(KISA 3장 제2절). 이미 정한 값(그림 파일의 Cache-Control 등)은 덮어쓰지 않는다."""
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    app.add_middleware(
        CORSMiddleware, allow_origins=allowed_origins(), allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition", "X-Memo-Summary", "X-Upscale-Summary"],
    )
    dist = Path(dist_dir).expanduser().resolve() if dist_dir is not None else None
    store = open_store(out_dir=out_dir, database_url=database_url)
    store.prepare()
    try:        # 보관 일수를 넘긴 생성형 AI 응답 캐시(원고 문장이 평문으로 들어 있음)를 서버를 띄울 때 지운다
        from ncs_llmreview import claude

        claude.prune_cache()
    except Exception as error:      # noqa: BLE001 — 정리에 실패해도 서버는 뜬다
        logger.warning("생성형 AI 응답 캐시 정리 실패: %s", error)
    uploads_store = UploadStore()
    app.state.uploads = uploads_store
    if require_login and not store.supports_history:
        raise ValueError("로그인을 쓰려면 데이터베이스(DATABASE_URL)가 필요합니다")
    auth.install(app, store, require_login=store.supports_history if require_login is None else require_login)

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
                messages.append(_input_message(field, detail))
        return error_response(400, "; ".join(dict.fromkeys(messages)))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(error.status_code, str(error.detail))

    # 기능별 경로 — 새 기능은 routes/에 모듈을 더하고 여기에 한 줄을 붙인다
    services = Services(store=store, uploads=uploads_store)
    for module in (review, history, export, plan, upscale, images, rights, recommend, volume, opinion, suggest, progress, cases, aiimage,
                   llm_review, figures, sources):
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
    parser.add_argument("--data", default=os.getenv("NCS_DATA_DIR") or "기준정보",
                        help="기준정보 폴더 — 운영 중에 NCS·법제처에서 받아 온 기준정보를 두는 곳 (기본: NCS_DATA_DIR 또는 실행 위치의 기준정보/)")
    args = parser.parse_args()
    try:
        app = create_app(out_dir=args.out, dist_dir=args.dist, database_url=os.getenv("DATABASE_URL"), data_dir=args.data)
    except ValueError as error:
        parser.exit(2, f"서버 실행 실패: {error}\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
