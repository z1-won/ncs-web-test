"""내려받기 — F02 검수 확인서(xlsx/hwpx)와 수정 메모 원고(hwpx)."""

import json
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import FastAPI, Form, Query, Response

from ..common import Services, error_response
from ..schemas import ErrorResponse, SheetExportRequest


def register(app: FastAPI, services: Services) -> None:
    store, uploads_store = services.store, services.uploads

    @app.post("/api/export/sheet", responses={400: {"model": ErrorResponse}})
    def export_sheet(body: SheetExportRequest, format: Literal["xlsx", "hwpx"] = Query("xlsx")) -> Response:
        """F02 검수 확인서 파일. xlsx(열람·편집) 또는 hwpx(원본 양식에 ✓·비고를 채운 제출본)."""
        from ncs_service import export

        code = body.module_code.strip() or "모듈"
        meta = export.module_meta(code)
        if body.created_at:
            meta["실행시각"] = body.created_at
        try:
            if format == "hwpx":
                content, media = export.build_hwpx(code, body.rows, meta=meta), "application/hwp+zip"
            else:
                content, media = export.build_xlsx(code, body.rows, meta=meta), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except ValueError as error:
            return error_response(400, str(error))
        filename = f"F02_검수확인서_{code}.{format}"
        return Response(content, media_type=media, headers={
            "Content-Disposition": f"attachment; filename=F02_sheet_{quote(code)}.{format}; filename*=UTF-8''{quote(filename)}",
        })

    @app.post("/api/export/annotated", responses={400: {"model": ErrorResponse}})
    def export_annotated(
        rows: Annotated[str, Form()],
        upload: Annotated[str, Form()] = "",
        run_id: Annotated[str, Form()] = "",
        module_code: Annotated[str, Form()] = "",
        created_at: Annotated[str, Form()] = "",
    ) -> Response:
        """원고 hwpx에 지적사항을 한글 메모로 단 파일. 원고는 둘 중 하나로 찾는다 — upload=업로드 토큰(방금 올린 원고),
        run_id=이력 실행 id(실행과 함께 보관된 원고; PostgreSQL 이력에서만). rows=체크리스트 행 JSON 배열,
        created_at=검사 실행 시각(ISO, 메모 날짜로 쓴다. 없으면 내보내는 시각)."""
        from ncs_core import detect_role, load_document
        from ncs_service.annotate import annotate_hwpx

        try:
            parsed = json.loads(rows)
            if not isinstance(parsed, list):
                raise ValueError
        except ValueError:
            return error_response(400, "rows는 체크리스트 행의 JSON 배열이어야 합니다")
        # 원고 찾기: 업로드 토큰(아직 살아 있으면) → 이력에 보관된 원고(run_id). 토큰이 만료돼도 run_id가 있으면 이어서 쓴다.
        name, source = None, None
        kept = uploads_store.get(upload) if upload else None
        if kept is not None:
            for file_name, path in kept.files:
                if not file_name.lower().endswith(".hwpx"):
                    continue
                # 업로드 칸이 역할을 정했으면 그대로, 아니면 내용으로 판별
                role = kept.assigned.get(str(path)) or detect_role(load_document(path).sections)
                if role == "manuscript":
                    name, source = file_name, path.read_bytes()
                    break
            if source is None:
                return error_response(400, "메모는 hwpx 원고에만 달 수 있습니다(hwp는 한글에서 hwpx로 저장 후 다시 올리세요)")
        elif run_id:
            found = store.get_manuscript(run_id)
            if found is None:
                return error_response(404, "이 실행에는 보관된 원고 hwpx가 없습니다(원고 보관 기능 이전의 실행이거나 hwp 원고, 또는 파일 저장소 모드)")
            name, source = found
        elif upload:
            return error_response(400, "업로드 토큰이 없거나 만료되었습니다. 파일을 다시 올려 주세요")
        else:
            return error_response(400, "upload 토큰 또는 run_id가 필요합니다")
        try:
            content, summary = annotate_hwpx(source, parsed, created_at=created_at or None)
        except ValueError as error:
            return error_response(400, str(error))
        stem = Path(name).stem
        filename = f"{stem}_검수메모.hwpx"
        return Response(content, media_type="application/hwp+zip", headers={
            "Content-Disposition": f"attachment; filename=annotated_{quote(module_code or 'manuscript')}.hwpx; filename*=UTF-8''{quote(filename)}",
            "X-Memo-Summary": json.dumps(summary),
        })
