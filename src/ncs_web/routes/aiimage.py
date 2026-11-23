"""AI 활용 표기와 생성형 AI 결과물 현황(REQ-02-006 ③④⑤) — 원고를 올려 그림을 읽고, 표기를 넣은 사본과 현황표를 받는다.

  GET  /api/ai-image/notice    유의 안내(근거와 항목) — 원고를 올리기 전에 화면이 보인다
  POST /api/ai-image/figures   manuscript(원고 hwp·hwpx) + print_copy(출력본 PDF, 선택) → 그림 목록, 이미 있는 AI 표기, 유의 안내
  POST /api/ai-image/preview   + marks(JSON) → 그림마다 표기 세 줄과 결과물 현황 줄(원고는 바꾸지 않는다)
  POST /api/ai-image/marked    manuscript(hwpx) + marks → AI 활용 줄을 넣은 원고 사본(hwpx). 요약은 X-Ai-Summary 머리글
  POST /api/ai-image/results   manuscript + print_copy + marks → 생성형 AI 결과물 현황 xlsx
  POST /api/ai-image/source    manuscript(hwpx) + key(그림) + credit(출처 문구) → 그 그림의 캡션 위에 출처 줄을 넣은 원고 사본(이미지 추천이 쓴다)
marks: [{"key": 그림 목록의 key, "tool": 도구 이름, "mode": "generated"|"modified", "date": "YYYY-MM-DD"}]
실행은 ncs_aiimage가 맡는다. 올린 파일은 읽는 동안만 임시 폴더에 두고 지운다. 데이터베이스에 남기는 것은 없다.
"""

import json
import re
import tempfile
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Response, UploadFile

from ..common import Services, error_response
from ..schemas import ErrorResponse

MAX_BYTES = 200 << 20      # 원고 + 출력본 합계 상한(업로드 보관함과 같은 200MB)


def _save(folder: Path, upload: UploadFile, fallback: str, budget: list[int]) -> Path:
    """올린 이름으로 임시 폴더에 쓴다. 경로 구분자 등은 '_'로 바꾼다. budget[0]: 남은 바이트."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", Path((upload.filename or fallback).replace("\\", "/")).name).strip(" .") or fallback
    data = upload.file.read(budget[0] + 1)
    budget[0] -= len(data)
    if budget[0] < 0:
        raise ValueError(f"올린 파일의 합계가 {MAX_BYTES >> 20}MB를 넘습니다")
    path = folder / name
    path.write_bytes(data)
    return path


def _marks(text: str) -> list:
    if not (text or "").strip():
        return []
    try:
        return json.loads(text)
    except ValueError:
        raise ValueError("marks는 JSON 목록이어야 합니다") from None


def register(app: FastAPI, services: Services) -> None:
    def _run(manuscript: UploadFile, print_copy: UploadFile | None, action) -> Any:
        with tempfile.TemporaryDirectory(prefix="ncs_aiimage_") as folder:
            try:
                budget = [MAX_BYTES]
                root = Path(folder)
                (root / "m").mkdir()
                (root / "p").mkdir()
                path = _save(root / "m", manuscript, "원고.hwpx", budget)
                pdf = _save(root / "p", print_copy, "출력본.pdf", budget) if print_copy is not None and print_copy.filename else None
                return action(path, pdf)
            except ValueError as error:
                return error_response(400, str(error))

    @app.get("/api/ai-image/notice")
    def notice() -> dict:
        from ncs_aiimage.notice import BASIS, NOTICE

        return {"근거": BASIS, "항목": list(NOTICE)}

    @app.post("/api/ai-image/figures", responses={400: {"model": ErrorResponse}})
    def figures(manuscript: Annotated[UploadFile, File()], print_copy: Annotated[UploadFile | None, File()] = None) -> Any:
        from ncs_aiimage import inspect

        return _run(manuscript, print_copy, lambda path, pdf: inspect(path, print_copy=pdf))

    @app.post("/api/ai-image/preview", responses={400: {"model": ErrorResponse}})
    def preview(manuscript: Annotated[UploadFile, File()], marks: Annotated[str, Form()] = "",
                print_copy: Annotated[UploadFile | None, File()] = None) -> Any:
        from ncs_aiimage import preview as build

        return _run(manuscript, print_copy, lambda path, pdf: build(path, _marks(marks), print_copy=pdf))

    @app.post("/api/ai-image/marked", responses={400: {"model": ErrorResponse}})
    def marked(manuscript: Annotated[UploadFile, File()], marks: Annotated[str, Form()] = "") -> Any:
        from ncs_aiimage import marked_copy

        def action(path: Path, _pdf) -> Response:
            content, summary = marked_copy(path, _marks(marks))
            filename = f"{path.stem}_AI표기.hwpx"
            brief = {"넣음": len(summary["넣음"]), "이미 있음": len(summary["이미 있음"]), "넣지 못함": len(summary["넣지 못함"]),
                     "다시 읽기": summary["다시 읽기"]}
            return Response(content, media_type="application/hwp+zip", headers={
                "Content-Disposition": f"attachment; filename=ai_marked.hwpx; filename*=UTF-8''{quote(filename)}",
                "X-Ai-Summary": json.dumps(brief), "Cache-Control": "no-store"})
        return _run(manuscript, None, action)

    @app.post("/api/ai-image/results", responses={400: {"model": ErrorResponse}})
    def results(manuscript: Annotated[UploadFile, File()], marks: Annotated[str, Form()] = "",
                print_copy: Annotated[UploadFile | None, File()] = None) -> Any:
        from ncs_aiimage import build_xlsx
        from ncs_aiimage import preview as build

        def action(path: Path, pdf) -> Response:
            rows = build(path, _marks(marks), print_copy=pdf)["현황"]
            if not rows:
                raise ValueError("AI 활용 표기가 있는 그림이 없어 현황에 적을 것이 없습니다")
            filename = f"{path.stem}_생성형AI결과물현황.xlsx"
            return Response(build_xlsx(rows, manuscript=path.name),
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
                                "Content-Disposition": f"attachment; filename=ai_results.xlsx; filename*=UTF-8''{quote(filename)}",
                                "X-Ai-Summary": json.dumps({"현황": len(rows)}), "Cache-Control": "no-store"})
        return _run(manuscript, print_copy, action)

    @app.post("/api/ai-image/source", responses={400: {"model": ErrorResponse}})
    def source(manuscript: Annotated[UploadFile, File()], key: Annotated[str, Form()], credit: Annotated[str, Form()]) -> Any:
        """출처 줄이 없는 그림 하나에 출처 줄을 넣은 원고 사본 — 이미지 추천(REQ-02-011)의 출처 문구를 원고에 넣는다. 이미 출처 줄이 있으면 400."""
        from ncs_aiimage import source_copy

        def action(path: Path, _pdf) -> Response:
            content, summary = source_copy(path, key, credit)
            filename = f"{path.stem}_출처표기.hwpx"
            return Response(content, media_type="application/hwp+zip", headers={
                "Content-Disposition": f"attachment; filename=source_marked.hwpx; filename*=UTF-8''{quote(filename)}",
                "X-Ai-Summary": json.dumps({"넣음": summary["넣음"]}), "Cache-Control": "no-store"})
        return _run(manuscript, None, action)
