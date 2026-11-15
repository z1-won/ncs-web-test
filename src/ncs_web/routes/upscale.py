"""그림 업스케일 — 업로드 토큰의 원고 그림 목록·원본·업스케일·결과·제안본 hwpx. 실행은 ncs_upscale.service가 맡는다."""

import json
import os
import re
import traceback
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, Form, Query, Response
from fastapi.responses import JSONResponse

from ..common import Services, error_response, logger
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
    def picture_upscale(token: str, bin_id: str, target_dpi: int = Query(300, ge=50, le=1200)) -> Response:
        """그림 하나를 업스케일(x2 20~40초, x4는 약 4배). GPU가 하나라 다른 업스케일이 돌고 있으면 끝날 때까지 기다린다."""
        def action():
            from ncs_upscale import service
            manuscript, work = _picture_upload(token)
            info = service.upscale_one(manuscript, bin_id, work, target_dpi=target_dpi,
                                       tools=app.state.upscale_tools, runner=app.state.upscale_runner)
            uploads_store.touch(token)
            return JSONResponse(info)
        return _picture_call(action)

    @app.get("/api/uploads/{token}/pictures/{bin_id}/upscaled")
    def picture_upscaled(token: str, bin_id: str, download: str = "") -> Response:
        """업스케일 결과(제안본에 들어갈 파일 그대로). download=파일 이름이면 내려받기로."""
        def action():
            from ncs_upscale import service
            _, work = _picture_upload(token)
            content, media, ext = service.upscaled_file(work, bin_id)
            name = None
            if download:
                # 캡션의 '/' 등 파일 이름에 못 쓰는 글자는 '_'로(Path로 자르면 '/' 앞이 사라진다)
                name = (re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", download).strip(" .") or bin_id) + ext
            return _png_response(content, media, name)
        return _picture_call(action)

    @app.post("/api/uploads/{token}/proposal", responses={400: {"model": ErrorResponse}})
    def picture_proposal(token: str, module_code: Annotated[str, Form()] = "",
                         target_dpi: Annotated[int | None, Form(ge=50, le=1200)] = None) -> Response:
        """업스케일에 성공한 그림만 같은 자리에 넣은 원고 사본(hwpx). 본문·그림 크기·위치는 그대로."""
        def action():
            from ncs_upscale import service
            manuscript, work = _picture_upload(token)
            content, summary = service.build_proposal(manuscript, work, target_dpi=target_dpi)
            filename = f"{manuscript.stem}_업스케일제안.hwpx"
            return Response(content, media_type="application/hwp+zip", headers={
                "Content-Disposition": f"attachment; filename=upscaled_{quote(module_code or 'manuscript')}.hwpx; filename*=UTF-8''{quote(filename)}",
                "X-Upscale-Summary": json.dumps(summary),
            })
        return _picture_call(action)
