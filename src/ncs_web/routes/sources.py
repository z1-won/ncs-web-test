"""출처 검토(REQ-02-008) — 규칙만 쓰므로 형식 검수 뒤 화면이 바로 부른다(API 비용 없음). 실행은 ncs_sources가 맡는다.

결과는 업로드 폴더 아래 _sources/result.json에 남고 토큰과 함께 지워진다.
"""

import json
import os
import traceback
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from ..common import Services, error_response, logger


def _preload() -> None:
    """요청 스레드가 처음으로 동시에 모듈을 읽다 막히지 않게(그림 검수와 같은 이유) 서버를 만들 때 미리 읽는다."""
    try:
        import ncs_sources.service  # noqa: F401
    except ImportError:
        pass


def register(app: FastAPI, services: Services) -> None:
    uploads_store = services.uploads
    _preload()

    def _upload(token: str) -> tuple[Path, Path]:
        kept = uploads_store.touch(token)
        if kept is None:
            raise ValueError("업로드 토큰이 없거나 만료되었습니다. 파일을 다시 올려 주세요")
        name = (kept.roles or {}).get("manuscript")
        path = next((p for n, p in kept.files if n == name), None)
        if path is None:
            raise ValueError("업로드에서 원고를 찾지 못했습니다")
        return path, kept.directory / "_sources"

    def _call(action):
        try:
            return action()
        except ValueError as error:
            return error_response(400, str(error))
        except Exception as error:
            logger.exception("출처 검토 실패: %s", error)
            debug = {"traceback": traceback.format_exc()} if os.getenv("NCS_WEB_DEBUG") == "1" else {}
            return error_response(500, f"{type(error).__name__}: {error}", **debug)

    def _result(manuscript: Path, work: Path, module_code: str = "") -> dict:
        target = work / "result.json"
        if target.is_file():
            return json.loads(target.read_text(encoding="utf-8"))
        from ncs_sources import review_sources
        result = review_sources(manuscript, module_code=module_code)
        work.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return result

    @app.get("/api/uploads/{token}/sources")
    def sources_review(token: str, module_code: str = "") -> Response:
        def action():
            manuscript, work = _upload(token)
            result = _result(manuscript, work, module_code)
            uploads_store.touch(token)
            return JSONResponse(result)
        return _call(action)

    @app.get("/api/uploads/{token}/sources/list.csv")
    def sources_csv(token: str) -> Response:
        def action():
            from ncs_sources.__main__ import write_csv
            manuscript, work = _upload(token)
            result = _result(manuscript, work)
            path = work / "list.csv"
            write_csv(result, path)
            name = f"{manuscript.stem}_출처목록.csv"
            return Response(path.read_bytes(), media_type="text/csv; charset=utf-8", headers={
                "Content-Disposition": f"attachment; filename=sources.csv; filename*=UTF-8''{quote(name)}"})
        return _call(action)
