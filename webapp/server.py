"""FastAPI 기반 로컬 검수 API. 업로드·HTTP 응답을 맡고 실행은 ncs_service에 위임한다."""

import argparse
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Annotated, Any, Literal

import uvicorn
from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException

ROOT = Path(__file__).resolve().parent
CheckName = Literal["position", "toc", "overview", "knowledge"]
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


class SavedPaths(BaseModel):
    folder: str
    zip: str


class ReviewResponse(BaseModel):
    check: CheckName
    module_code: str
    요약: dict[str, Any]
    검수확인서: list[dict[str, Any]]
    진단: dict[str, Any]
    지적사항: list[dict[str, Any]]
    전체: list[dict[str, Any]]
    저장: SavedPaths


class ErrorResponse(BaseModel):
    error: str
    traceback: str | None = None


def error_response(status: int, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": message, **extra}, status_code=status, headers=CORS_HEADERS)


def create_app(
    *, src_dir: str | Path = ROOT.parent / "src", out_dir: str | Path = "결과",
    dist_dir: str | Path | None = None,
) -> FastAPI:
    """경로는 앱 생성 시 실행 위치를 기준으로 확정한다. dist_dir 생략 시 API만 제공한다."""
    src = Path(src_dir).resolve()
    packages = ("ncs_core", "ncs_position", "ncs_toc", "ncs_overview", "ncs_knowledge", "ncs_service")
    missing = [name for name in packages if not (src / name / "__init__.py").is_file()]
    if missing:
        raise ValueError(f"검수 패키지를 찾지 못했습니다: {', '.join(missing)} (찾은 곳: {src})")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from ncs_service import ReviewRequest, execute_review, persist_review

    app = FastAPI(title="F02 검수 API")
    output = Path(out_dir).expanduser().resolve()
    dist = Path(dist_dir).expanduser().resolve() if dist_dir is not None else None

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        messages = []
        for detail in error.errors():
            field = str(detail["loc"][-1])
            if field == "files" and detail["type"] == "missing":
                messages.append("업로드된 파일이 없습니다")
            elif field == "check":
                messages.append("check는 position / toc / overview / knowledge 중 하나여야 합니다")
            else:
                messages.append(f"{field}: {detail['msg']}")
        return error_response(400, "; ".join(messages))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(error.status_code, str(error.detail))

    @app.get("/api/health")
    def health(response: Response) -> dict[str, Any]:
        response.headers.update(CORS_HEADERS)
        return {"ok": True, "checks": ["position", "toc", "overview", "knowledge"]}

    @app.options("/{path:path}", include_in_schema=False)
    def options(path: str) -> Response:
        return Response(status_code=204, headers={
            **CORS_HEADERS,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
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
                if not paths:
                    raise ValueError("업로드된 파일이 없습니다")
                execution = execute_review(ReviewRequest(tuple(paths), check, module_code.strip()))
                saved = persist_review(execution, output)
                result = execution.result
                payload = ReviewResponse(
                    check=execution.check, module_code=result.module_code, 요약=saved.summary,
                    검수확인서=result.sheet, 진단=result.diagnostics, 지적사항=result.findings,
                    전체=result.checklist, 저장=SavedPaths(folder=str(saved.directory), zip=str(saved.zip_path)),
                )
        except ValueError as error:
            return error_response(400, str(error))
        except Exception as error:
            return error_response(500, f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        response.headers.update(CORS_HEADERS)
        return payload

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
    parser.add_argument("--src", default=str(ROOT.parent / "src"))
    parser.add_argument("--out", default="결과", help="결과 저장 폴더 (기본: 실행 위치의 결과/)")
    parser.add_argument("--dist", help="React 빌드 폴더. 생략하면 API만 제공")
    args = parser.parse_args()
    try:
        app = create_app(src_dir=args.src, out_dir=args.out, dist_dir=args.dist)
    except ValueError as error:
        parser.exit(2, f"서버 실행 실패: {error}\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
