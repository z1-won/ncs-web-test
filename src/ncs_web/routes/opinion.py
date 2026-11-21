"""검토의견서·심의의견서 반영 여부 검토(REQ-02-003) — 의견서(여러 개)와 최종 원고(+ 출력본·반영 전 원고)를 받아 의견별 판정 후보표를 돌려준다.

판정은 ncs_opinion이 맡는다. 검수 결과처럼 저장하지 않는다: 올린 파일은 임시 폴더에서 읽고 바로 지운다.
"""

import re
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, UploadFile

from ..common import Services, error_response
from ..schemas import ErrorResponse


def _save(folder: Path, upload: UploadFile, fallback: str) -> Path:
    """올린 이름(결과에 그대로 보인다)으로 임시 폴더에 쓴다. 경로 구분자 등은 '_'로, 같은 이름이 있으면 번호를 붙인다."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", Path(upload.filename or fallback).name).strip(" .") or fallback
    path, n = folder / name, 1
    while path.exists():
        n += 1
        path = folder / f"{n}_{name}"
    path.write_bytes(upload.file.read())
    return path


def register(app: FastAPI, services: Services) -> None:
    @app.post("/api/opinion", responses={400: {"model": ErrorResponse}})
    def opinion(
        manuscript: Annotated[UploadFile, File()],
        opinions: Annotated[list[UploadFile], File()],
        rounds: Annotated[list[str] | None, Form()] = None,
        print_pdf: Annotated[UploadFile | None, File()] = None,
        previous: Annotated[UploadFile | None, File()] = None,
    ) -> Any:
        """판정 후보표 JSON(ncs_opinion.review). opinions: 검토의견서·심의의견서(PDF·hwp·hwpx), rounds: 의견서 순서대로 '1차'·'2차'·'심의'(선택),
        print_pdf: 최종 원고 출력본(근거 쪽 표시), previous: 반영 전 원고. 판정은 LLM이 한다 — 서버에 LLM 설정·반출 승인이 있으면
        자동으로 부르고, 없으면 모든 의견이 '확인 필요'와 이유(결과의 'LLM' 값)다."""
        from ncs_opinion import review

        with tempfile.TemporaryDirectory(prefix="ncs_opinion_") as folder:
            try:
                root = Path(folder)
                final = _save(root, manuscript, "원고.hwp")
                sheets = [_save(root, upload, f"의견서{i + 1}.pdf") for i, upload in enumerate(opinions) if upload.filename]
                pdf = _save(root, print_pdf, "출력본.pdf") if print_pdf is not None and print_pdf.filename else None
                old = _save(root, previous, "반영전원고.hwp") if previous is not None and previous.filename else None
                return review(sheets, final, rounds=[r.strip() for r in rounds or []] or None, print_pdf=pdf, previous=old)
            except ValueError as error:
                return error_response(400, str(error))
