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
        _record(manuscript.name, result, module_code)
        return result

    def _record(manuscript: str, result: dict, module_code: str) -> None:
        """원고 진행 현황(REQ-02-007)의 저작권 검수 진행도에 쓸 개수만 남긴다(DB 모드). 출처 원문은 남기지 않는다. 실패해도 검토 결과는 그대로 준다."""
        from ncs_service.workflow.progress import SOURCES, summarize_sources

        try:
            services.store.save_work_record(SOURCES, manuscript, summarize_sources(result), [{"role": "manuscript", "filename": manuscript}],
                                            module_code=module_code)
        except Exception as error:
            logger.exception("출처 검토 개수 기록 실패: %s", error)

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

    @app.get("/api/uploads/{token}/sources/memo")
    def sources_memo(token: str) -> Response:
        """출처 검토의 부적합·판단불가 줄마다 사유와 고칠 꼴을 메모로 단 원고 사본(hwpx만) — 사람 작업 3번 '한글에 교정하여 저장하고 전달'.
        원고 본문은 바꾸지 않는다: 출처의 저자·연도·쪽은 사람이 확인해 고쳐야 한다."""
        def action():
            from ncs_service.annotate import annotate_hwpx
            manuscript, work = _upload(token)
            if manuscript.suffix.lower() != ".hwpx":
                raise ValueError("메모 원고는 hwpx만 만들 수 있습니다. 한글에서 hwpx로 저장해 다시 올려 주세요")
            result = _result(manuscript, work)
            rows = [row for row in result.get("rows", []) if row.get("판정") != "적합"]
            if not rows:
                raise ValueError("메모로 남길 출처 지적이 없습니다")
            content, summary = annotate_hwpx(manuscript.read_bytes(), rows, author="출처 검토")
            name = f"{manuscript.stem}_출처검토메모.hwpx"
            return Response(content, media_type="application/hwp+zip", headers={
                "Content-Disposition": f"attachment; filename=sources_memo.hwpx; filename*=UTF-8''{quote(name)}",
                "X-Memo-Summary": json.dumps(summary)})
        return _call(action)
