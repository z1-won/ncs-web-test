"""원고 분량 산정(REQ-02-013) — 최종 원고(+ 기존 원고, 출력본 PDF)를 받아 구성별 행·쪽 산정표와 집필료를 돌려준다. 계산은 ncs_volume이 맡는다.

올린 파일은 임시 폴더에서 읽고 바로 지운다(원고는 보관하지 않는다). 저장소가 이력을 지원하면(PostgreSQL) 산정표와 넣은 값,
입력 파일의 이름·해시를 이력에 남기고(/api/volumes로 다시 연다) 응답에 id를 싣는다 — 집필료 정산 근거를 나중에 다시 보기 위해서다.
이력에 쓰지 못해도 산정 결과는 돌려주고 '저장 오류'로 알린다(계산을 다시 하게 만들지 않는다).
"""

import re
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Query, Request, Response, UploadFile
from starlette.exceptions import HTTPException

from ..common import Services, error_response, logger, own_and_link, scope_of
from ..schemas import ErrorResponse


def _save(folder: Path, upload: UploadFile, fallback: str) -> Path:
    """올린 이름(결과에 그대로 보인다)으로 임시 폴더에 쓴다. 경로 구분자 등은 '_'로."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", Path(upload.filename or fallback).name).strip(" .") or fallback
    path = folder / name
    if path.exists():
        path = folder / f"기존_{name}"
    path.write_bytes(upload.file.read())
    return path


def register(app: FastAPI, services: Services) -> None:
    store = services.store

    @app.post("/api/volume", responses={400: {"model": ErrorResponse}})
    def volume(
        request: Request,
        manuscript: Annotated[UploadFile, File()],
        previous: Annotated[UploadFile | None, File()] = None,
        manual_pages: Annotated[float | None, Form(gt=0)] = None,
        include_appendix: Annotated[bool, Form()] = True,
        print_copy: Annotated[UploadFile | None, File()] = None,
        unit_price: Annotated[int | None, Form(gt=0)] = None,
        contract_pages: Annotated[int | None, Form(gt=0)] = None,
        case_volume: Annotated[str, Form()] = "",     # 세분류 건의 권에서 열어 돌린 것이면 그 권 id와 단계 — 산정 기록이 그 단계에 붙는다
        case_stage: Annotated[str, Form()] = "",
        case_version: Annotated[str, Form()] = "",    # 보관한 판본을 그대로 쓴 것이면 그 판본 id
    ) -> Any:
        """산정표 JSON(ncs_volume.measure). previous: 비교할 기존 원고, manual_pages: 수작업 산정 쪽수(오차율),
        include_appendix: 부록을 산정에 넣을지(기본: 계약서 제13조 4항대로 넣는다),
        print_copy: 원고를 한글에서 PDF로 저장한 출력본(쪽을 PDF에서 잰다), unit_price: 원고료 단가(원/쪽, 없으면 예산지침 상한),
        contract_pages: 계약서에 적은 원고 분량(매, 초과분은 인정하지 않음).
        이력을 지원하는 저장소면 응답에 id(이력 id)를 싣는다. 저장하지 못했으면 id는 null이고 '저장 오류'에 이유가 있다."""
        from ncs_volume import DEFAULT_CONFIG, measure

        config = replace(DEFAULT_CONFIG, include_appendix=include_appendix)
        with tempfile.TemporaryDirectory(prefix="ncs_volume_") as folder:
            try:
                final = _save(Path(folder), manuscript, "원고.hwp")
                old = _save(Path(folder), previous, "기존원고.hwp") if previous is not None and previous.filename else None
                printed = _save(Path(folder), print_copy, "출력본.pdf") if print_copy is not None and print_copy.filename else None
                result = measure(final, previous=old, manual_pages=manual_pages, config=config, print_pdf=printed,
                                 fee_unit=unit_price, contract_pages=contract_pages)
            except ValueError as error:
                return error_response(400, str(error))
            if not store.supports_history:
                return result
            # 해시는 임시 파일이 지워지기 전에 낸다. 이름은 사용자가 올린 그대로(임시 폴더에서 '기존_'이 붙었을 수 있다)
            files = [("manuscript", final.name, final)]
            if old is not None:
                files.append(("previous", Path(previous.filename).name, old))
            if printed is not None:
                files.append(("print", Path(print_copy.filename).name, printed))
            params = {"unit_price": unit_price, "contract_pages": contract_pages, "manual_pages": manual_pages,
                      "include_appendix": include_appendix}
            try:
                run_id = store.save_volume(result, files, params)
                linked = own_and_link(request, store, "volume", run_id, case_volume, case_stage, case_version)
                return {**result, "id": run_id, **({"건에 붙임": linked} if case_volume else {})}
            except Exception as error:
                logger.exception("원고 분량 산정 이력 저장 실패: %s", error)
                detail = (str(error).splitlines() or [""])[0]
                return {**result, "id": None, "저장 오류": f"산정 이력을 저장하지 못했습니다({type(error).__name__}): {detail}"}

    if store.supports_history:

        @app.get("/api/volumes")
        def volumes(request: Request, module_code: str | None = None, limit: int = Query(50, ge=1, le=100),
                    offset: int = Query(0, ge=0)) -> list[dict]:
            """산정 이력 목록(최신순): 산정 시각·원고·분량·단가·집필료. 산정표 전체는 /api/volumes/{id}."""
            return store.list_volumes(module_code=module_code, limit=limit, offset=offset, visible=scope_of(request, store))

        @app.get("/api/volumes/{run_id}")
        def volume_detail(request: Request, run_id: str) -> dict:
            from ncs_service.auth import access

            if not access.allowed(store.dsn, scope_of(request, store), "volume", run_id):
                raise HTTPException(404, "산정 이력을 찾을 수 없습니다")
            found = store.get_volume(run_id)
            if found is None:
                raise HTTPException(404, "산정 이력을 찾을 수 없습니다")
            return found

        @app.delete("/api/volumes/{run_id}", status_code=204)
        def volume_delete(request: Request, run_id: str) -> Response:
            from ncs_service.auth import access

            if not access.allowed(store.dsn, scope_of(request, store), "volume", run_id):
                raise HTTPException(404, "산정 이력을 찾을 수 없습니다")
            if not store.delete_volume(run_id):
                raise HTTPException(404, "산정 이력을 찾을 수 없습니다")
            return Response(status_code=204)
