"""검토의견서·심의의견서 반영 여부 검토(REQ-02-003) — 의견서(여러 개)와 최종 원고(+ 출력본·반영 전 원고)를 받아 의견별 판정 후보표를 돌려준다.

판정은 ncs_opinion이 맡는다. 검수 결과처럼 저장하지 않는다: 올린 파일은 임시 폴더에서 읽고 바로 지운다.
저장소가 이력을 지원하면(PostgreSQL) 원고 진행 현황(REQ-02-007)에 쓸 **개수만** 남긴다 — 차수별 총 의견·반영 후보·미반영 후보·확인 필요 수와
올린 파일 이름. 의견 문장과 원고 문단은 남기지 않는다. 남기지 못해도 검토 결과는 그대로 돌려준다.
"""

import re
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Request, UploadFile

from ..common import Services, error_response, logger, own_and_link
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
        request: Request,
        manuscript: Annotated[UploadFile, File()],
        opinions: Annotated[list[UploadFile], File()],
        rounds: Annotated[list[str] | None, Form()] = None,
        print_pdf: Annotated[UploadFile | None, File()] = None,
        previous: Annotated[UploadFile | None, File()] = None,
        case_volume: Annotated[str, Form()] = "",     # 세분류 건의 권에서 열어 돌린 것이면 그 권 id와 단계 — 개수 기록이 그 단계에 붙는다
        case_stage: Annotated[str, Form()] = "",
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
                result = review(sheets, final, rounds=[r.strip() for r in rounds or []] or None, print_pdf=pdf, previous=old)
            except ValueError as error:
                return error_response(400, str(error))
            files = [{"role": "manuscript", "filename": final.name}] + [{"role": "opinion", "filename": s.name} for s in sheets]
        record = _record(services, final.name, result, files)
        linked = own_and_link(request, services.store, "opinion", record["id"] if record else None, case_volume, case_stage)
        return {**result, "진행 현황 기록": record, **({"건에 붙임": linked} if case_volume else {})}


def _record(services: Services, manuscript: str, result: dict, files: list[dict]) -> dict | None:
    """진행 현황용 개수 기록. 돌려주는 값: {'id', 'module_code'}(모듈 코드가 비면 어느 원고에도 붙지 않음) 또는 None(DB 없음·실패)."""
    from ncs_service.progress import OPINION, summarize_opinion

    try:
        return services.store.save_work_record(OPINION, manuscript, summarize_opinion(result), files)
    except Exception as error:      # 기록은 부가 기능이라 검토 결과를 막지 않는다
        logger.exception("의견 반영 검토 개수 기록 실패: %s", error)
        return None
