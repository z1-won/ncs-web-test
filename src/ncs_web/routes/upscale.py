"""그림 업스케일 — 업로드 토큰의 원고 그림 목록·원본·업스케일·결과·제안본 hwpx. 실행은 ncs_upscale.service가 맡는다.

화질 보정은 AI 수정 보완(REQ-02-006 ②)이므로 제안본을 만들 때 보정한 그림의 캡션 위에 AI 활용 줄을 함께 넣을 수 있고(ai_mark — ncs_aiimage),
보정한 그림을 이미지 저작권 DB에 AI 활용 정보와 함께 올릴 수 있다(/pictures/register — ncs_service.ai_register, PostgreSQL일 때만).
"""

import json
import os
import re
import traceback
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, Form, Query, Request, Response
from fastapi.responses import JSONResponse

from ..common import Services, actor, error_response, logger
from ..schemas import ErrorResponse


def register(app: FastAPI, services: Services) -> None:
    uploads_store = services.uploads

    # ── 그림 업스케일: 원고 그림을 보여 주고, 고른 그림만 한 장씩 키워 내려받고, 그 그림들로 제안본 hwpx를 만든다.
    # 실행은 ncs_upscale.service가 맡는다(Pillow 필요 — 없으면 이 경로들만 500). 결과는 업로드 폴더 아래에 남아 토큰과 함께 지워진다.
    # app.state.upscale_runner: 테스트용 엔진 대역(runner(src, out, scale)), app.state.upscale_tools: 엔진 도구 폴더.
    app.state.upscale_runner = None
    app.state.upscale_tools = None

    def _picture_upload(token: str) -> tuple[Path, Path]:
        """(원고 hwpx 경로, 업스케일 결과 폴더). 토큰 만료를 미룬다."""
        kept = uploads_store.touch(token)
        if kept is None:
            raise ValueError("업로드 토큰이 없거나 만료되었습니다. 파일을 다시 올려 주세요")
        name = (kept.roles or {}).get("manuscript")
        path = next((p for n, p in kept.files if n == name), None)
        if path is None:
            raise ValueError("업로드에서 원고를 찾지 못했습니다")
        if path.suffix.lower() != ".hwpx":
            raise ValueError("hwp 원고는 그림을 읽지 못합니다. 한글에서 hwpx로 저장해 다시 올리세요")
        return path, kept.directory / "_upscale"

    def _ai_day(text: str) -> date:
        if not (text or "").strip():
            return date.today()
        try:
            return date.fromisoformat(text.strip())
        except ValueError:
            raise ValueError("AI 활용 일자는 YYYY-MM-DD 날짜여야 합니다") from None

    def _picture_call(action):
        try:
            return action()
        except ImportError as error:
            return error_response(500, f"그림 업스케일에는 Pillow가 필요합니다(pip install -r requirements/web.txt): {error}")
        except ValueError as error:   # PictureError 포함
            return error_response(400, str(error))
        except Exception as error:
            # 검수 실행과 같이 traceback은 서버 로그에만 남기고, 응답에는 NCS_WEB_DEBUG=1일 때만 싣는다.
            logger.exception("그림 업스케일 실패: %s", error)
            debug = {"traceback": traceback.format_exc()} if os.getenv("NCS_WEB_DEBUG") == "1" else {}
            return error_response(500, f"{type(error).__name__}: {error}", **debug)

    def _png_response(content: bytes, media: str = "image/png", filename: str | None = None) -> Response:
        headers = {"Cache-Control": "no-store"}
        if filename:
            headers["Content-Disposition"] = f"attachment; filename=upscaled{Path(filename).suffix}; filename*=UTF-8''{quote(filename)}"
        return Response(content, media_type=media, headers=headers)

    @app.get("/api/uploads/{token}/pictures")
    def pictures(token: str, target_dpi: int = Query(300, ge=50, le=1200)) -> Response:
        """목표 DPI 미만 그림 파일 목록(원고에 나오는 순서)과 업스케일 엔진 상태."""
        def action():
            from ncs_upscale import service
            manuscript, work = _picture_upload(token)
            body = {**service.list_pictures(manuscript, work, target_dpi=target_dpi),
                    "engine": service.engine_status(app.state.upscale_tools) if app.state.upscale_runner is None
                    else {"name": "test", "note": "", "available": True, "problem": None}}
            # engines: '이 그림만 업스케일링'에서 고를 수 있는 모델(앞의 것이 기본). 테스트 대역을 쓰면 모두 쓸 수 있는 것으로 본다
            body["engines"] = [{**choice, **({"available": True, "problem": None} if app.state.upscale_runner is not None else {})}
                               for choice in service.engine_choices(app.state.upscale_tools)]
            return JSONResponse(body)
        return _picture_call(action)

    @app.get("/api/uploads/{token}/pictures/{bin_id}/original")
    def picture_original(token: str, bin_id: str) -> Response:
        def action():
            from ncs_upscale import service
            manuscript, _ = _picture_upload(token)
            return _png_response(service.original_png(manuscript, bin_id))
        return _picture_call(action)

    @app.post("/api/uploads/{token}/pictures/{bin_id}/upscale")
    def picture_upscale(token: str, bin_id: str, target_dpi: int = Query(300, ge=50, le=1200), engine: str = Query("")) -> Response:
        """그림 하나를 업스케일(x2 20~40초, x4는 약 4배). GPU가 하나라 다른 업스케일이 돌고 있으면 끝날 때까지 기다린다.
        engine: 모델 이름(목록 응답의 engines[].name). 비우면 기본 모델."""
        def action():
            from ncs_upscale import service
            manuscript, work = _picture_upload(token)
            info = service.upscale_one(manuscript, bin_id, work, target_dpi=target_dpi,
                                       tools=app.state.upscale_tools, runner=app.state.upscale_runner, engine=engine or None)
            uploads_store.touch(token)
            return JSONResponse(info)
        return _picture_call(action)

    @app.get("/api/uploads/{token}/pictures/{bin_id}/upscaled")
    def picture_upscaled(token: str, bin_id: str, download: str = "", engine: str = "") -> Response:
        """업스케일 결과(제안본에 들어갈 파일 그대로). download=파일 이름이면 내려받기로. engine=모델 이름이면 그 모델로 키운 결과."""
        def action():
            from ncs_upscale import service
            _, work = _picture_upload(token)
            content, media, ext = service.upscaled_file(work, bin_id, engine or None)
            name = None
            if download:
                # 캡션의 '/' 등 파일 이름에 못 쓰는 글자는 '_'로(Path로 자르면 '/' 앞이 사라진다)
                name = (re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", download).strip(" .") or bin_id) + ext
            return _png_response(content, media, name)
        return _picture_call(action)

    @app.post("/api/uploads/{token}/proposal", responses={400: {"model": ErrorResponse}})
    def picture_proposal(token: str, module_code: Annotated[str, Form()] = "",
                         target_dpi: Annotated[int | None, Form(ge=50, le=1200)] = None,
                         ai_mark: Annotated[bool, Form()] = False, ai_date: Annotated[str, Form()] = "") -> Response:
        """업스케일에 성공한 그림만 같은 자리에 넣은 원고 사본(hwpx). 본문·그림 크기·위치는 그대로.
        ai_mark=true면 보정한 그림의 캡션 위에 AI 활용 줄('OO를 활용하여 수정 보완함. 일자')을 넣는다(이미 있는 그림은 그대로).
        ai_date: 활용 일자(YYYY-MM-DD, 비우면 오늘). 요약의 'AI 표기'에 넣은 수·이미 있던 수·넣지 못한 수가 실린다."""
        def action():
            from ncs_upscale import service
            manuscript, work = _picture_upload(token)
            content, summary = service.build_proposal(manuscript, work, target_dpi=target_dpi)
            if ai_mark:
                from ncs_aiimage import mark_pictures

                engines = {info["bin_id"]: service.tool_name(info.get("engine")) for info in service.finished(work, target_dpi)}
                content, marked = mark_pictures(manuscript, content, {bin_id: engines[bin_id] for bin_id in summary["그림"] if bin_id in engines},
                                                on=_ai_day(ai_date))
                summary["AI 표기"] = {"넣음": len(marked["넣음"]), "이미 있음": len(marked["이미 있음"]),
                                      "넣지 못함": len(marked["넣지 못함"]) + len(marked["캡션 없음"])}
            filename = f"{manuscript.stem}_업스케일제안.hwpx"
            return Response(content, media_type="application/hwp+zip", headers={
                "Content-Disposition": f"attachment; filename=upscaled_{quote(module_code or 'manuscript')}.hwpx; filename*=UTF-8''{quote(filename)}",
                "X-Upscale-Summary": json.dumps(summary),
            })
        return _picture_call(action)

    @app.post("/api/uploads/{token}/pictures/register", responses={400: {"model": ErrorResponse}})
    def picture_register(request: Request, token: str, module_code: Annotated[str, Form()] = "",
                         target_dpi: Annotated[int | None, Form(ge=50, le=1200)] = None,
                         ai_date: Annotated[str, Form()] = "", by: Annotated[str, Form()] = "") -> Response:
        """보정한 그림(원본과 업스케일본)을 이미지 저작권 DB에 올린다 — AI 활용 유형 3(기존 이미지 보정, 수정 보완)·도구·일자·원본 출처와 함께.
        에디터와 직능연만 한다. 기관이 확정한 그림의 권리 정보는 바꾸지 않는다. 모듈 코드는 원고 파일 이름에서 읽거나 module_code로 준다."""
        def action():
            from ncs_core.module_code import resolve_module_code
            from ncs_service.ai_register import register_upscaled
            from ncs_service.flow import MANAGER_ROLES

            account = getattr(request.state, "account", None)
            if account is not None and account.get("role") not in MANAGER_ROLES:
                return error_response(403, "이미지 저작권 DB에 올리는 일은 에디터와 직능연 계정만 할 수 있습니다")
            if not services.store.supports_history:
                raise ValueError("이미지 저작권 DB에 올리려면 데이터베이스(DATABASE_URL)가 필요합니다")
            who = actor(request, by)
            if not who:
                raise ValueError("by(변경한 사람)가 필요합니다. 변경 이력에 남습니다")
            manuscript, work = _picture_upload(token)
            try:
                code = resolve_module_code(manuscript, module_code)
            except ValueError as error:
                raise ValueError(f"이미지 저작권 DB에 올리려면 모듈 코드가 필요합니다: {error}") from None
            return JSONResponse({"모듈 코드": code, **register_upscaled(services.store.dsn, manuscript, work, code, by=who,
                                                                      on=_ai_day(ai_date), target_dpi=target_dpi)})
        return _picture_call(action)
