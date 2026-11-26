"""LLM 검토 — 형식 검수 뒤에 사용자가 'LLM 검토'를 눌렀을 때만 실행(토큰을 쓰는 유일한 경로). 실행은 ncs_llmreview가 맡는다.

결과는 업로드 폴더 아래 _llm_review/result.json에 남고 토큰과 함께 지워진다. 같은 원고·같은 항목은 응답 캐시로 다시 과금하지 않는다.
app.state.llm_review_generate: 테스트용 Claude 대역((system, user, *, task) -> {'data','usage','cached','model'}).
"""

import json
import os
import traceback
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import JSONResponse

from ..common import Services, error_response, logger, manager_only


WHAT = "LLM 검토는"      # manager_only가 403에 적는 주어


def register(app: FastAPI, services: Services) -> None:
    uploads_store = services.uploads
    app.state.llm_review_generate = None

    def _upload(token: str) -> tuple[Path, Path]:
        kept = uploads_store.touch(token)
        if kept is None:
            raise ValueError("업로드 토큰이 없거나 만료되었습니다. 파일을 다시 올려 주세요")
        name = (kept.roles or {}).get("manuscript")
        path = next((p for n, p in kept.files if n == name), None)
        if path is None:
            raise ValueError("업로드에서 원고를 찾지 못했습니다")
        return path, kept.directory / "_llm_review"

    def _call(action):
        try:
            return action()
        except ImportError as error:
            return error_response(500, f"LLM 검토에 필요한 패키지가 없습니다(pip install -r requirements/web.txt): {error}")
        except ValueError as error:
            return error_response(400, str(error))
        except Exception as error:
            logger.exception("LLM 검토 실패: %s", error)
            debug = {"traceback": traceback.format_exc()} if os.getenv("NCS_WEB_DEBUG") == "1" else {}
            return error_response(500, f"{type(error).__name__}: {error}", **debug)

    @app.get("/api/llm-review/status")
    def llm_review_status() -> Response:
        """키·반출 승인·모델 — 화면이 'LLM 검토' 버튼을 켤지 정한다. 테스트 대역이 있으면 쓸 수 있는 것으로 본다."""
        def action():
            from ncs_llmreview import status
            body = status()
            if app.state.llm_review_generate is not None:
                body.update(available=True, problem=None, model="test")
            return JSONResponse(body)
        return _call(action)

    @app.get("/api/uploads/{token}/llm-review")
    def llm_review_previous(token: str, request: Request) -> Response:
        manager_only(request, WHAT)
        def action():
            _, work = _upload(token)
            path = work / "result.json"
            if not path.is_file():
                return error_response(404, "아직 LLM 검토를 하지 않았습니다")
            return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
        return _call(action)

    @app.post("/api/uploads/{token}/llm-review")
    def llm_review_run(token: str, request: Request, tasks: Annotated[str, Form()] = "", module_code: Annotated[str, Form()] = "") -> Response:
        """tasks: 쉼표로 구분한 항목(비우면 전부). 원고 크기에 따라 수십 초~수 분. 비용이 드는 검토라 에디터와 직능연 계정만 한다."""
        manager_only(request, WHAT)
        def action():
            from ncs_llmreview import review_manuscript
            manuscript, work = _upload(token)
            chosen = [t.strip() for t in tasks.split(",") if t.strip()] or None
            result = review_manuscript(manuscript, tasks=chosen, module_code=module_code, generate=app.state.llm_review_generate)
            work.mkdir(parents=True, exist_ok=True)
            (work / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            uploads_store.touch(token)
            return JSONResponse(result)
        return _call(action)

    @app.get("/api/uploads/{token}/llm-review/result.json")
    def llm_review_json(token: str, request: Request) -> Response:
        manager_only(request, WHAT)
        def action():
            manuscript, work = _upload(token)
            path = work / "result.json"
            if not path.is_file():
                return error_response(404, "아직 LLM 검토를 하지 않았습니다")
            name = f"{manuscript.stem}_LLM검토.json"
            return Response(path.read_bytes(), media_type="application/json", headers={
                "Content-Disposition": f"attachment; filename=llm_review.json; filename*=UTF-8''{quote(name)}"})
        return _call(action)

    @app.get("/api/uploads/{token}/llm-review/memo")
    def llm_review_memo(token: str, request: Request) -> Response:
        """LLM 수정 후보를 메모로 단 원고 사본(hwpx만). 원고 본문은 바꾸지 않는다."""
        manager_only(request, WHAT)
        def action():
            from ncs_llmreview import to_rows
            from ncs_service.annotate import annotate_hwpx
            manuscript, work = _upload(token)
            if manuscript.suffix.lower() != ".hwpx":
                raise ValueError("메모 원고는 hwpx만 만들 수 있습니다. 한글에서 hwpx로 저장해 다시 올리세요")
            path = work / "result.json"
            if not path.is_file():
                raise ValueError("아직 LLM 검토를 하지 않았습니다")
            result = json.loads(path.read_text(encoding="utf-8"))
            content, summary = annotate_hwpx(manuscript.read_bytes(), to_rows(result), author="LLM 검토", created_at=result.get("created_at"))
            name = f"{manuscript.stem}_LLM검토메모.hwpx"
            return Response(content, media_type="application/hwp+zip", headers={
                "Content-Disposition": f"attachment; filename=llm_review_memo.hwpx; filename*=UTF-8''{quote(name)}",
                "X-Memo-Summary": json.dumps(summary)})
        return _call(action)
