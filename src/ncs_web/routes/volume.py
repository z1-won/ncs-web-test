"""원고 분량 산정(REQ-02-013) — 최종 원고(+ 기존 원고, 출력본 PDF)를 받아 구성별 행·쪽 산정표와 집필료를 돌려준다. 계산은 ncs_volume이 맡는다.

검수 결과처럼 저장하지 않는다: 올린 파일은 임시 폴더에서 읽고 바로 지운다.
"""

import re
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, UploadFile

from ..common import Services, error_response
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
    @app.post("/api/volume", responses={400: {"model": ErrorResponse}})
    def volume(
        manuscript: Annotated[UploadFile, File()],
        previous: Annotated[UploadFile | None, File()] = None,
        manual_pages: Annotated[float | None, Form(gt=0)] = None,
        include_appendix: Annotated[bool, Form()] = True,
        print_copy: Annotated[UploadFile | None, File()] = None,
        unit_price: Annotated[int | None, Form(gt=0)] = None,
        contract_pages: Annotated[int | None, Form(gt=0)] = None,
    ) -> Any:
        """산정표 JSON(ncs_volume.measure). previous: 비교할 기존 원고, manual_pages: 수작업 산정 쪽수(오차율),
        include_appendix: 부록을 산정에 넣을지(기본: 계약서 제13조 4항대로 넣는다),
        print_copy: 원고를 한글에서 PDF로 저장한 출력본(쪽을 PDF에서 잰다), unit_price: 원고료 단가(원/쪽, 없으면 예산지침 상한),
        contract_pages: 계약서에 적은 원고 분량(매, 초과분은 인정하지 않음)."""
        from ncs_volume import DEFAULT_CONFIG, measure

        config = replace(DEFAULT_CONFIG, include_appendix=include_appendix)
        with tempfile.TemporaryDirectory(prefix="ncs_volume_") as folder:
            try:
                final = _save(Path(folder), manuscript, "원고.hwp")
                old = _save(Path(folder), previous, "기존원고.hwp") if previous is not None and previous.filename else None
                printed = _save(Path(folder), print_copy, "출력본.pdf") if print_copy is not None and print_copy.filename else None
                return measure(final, previous=old, manual_pages=manual_pages, config=config, print_pdf=printed,
                               fee_unit=unit_price, contract_pages=contract_pages)
            except ValueError as error:
                return error_response(400, str(error))
