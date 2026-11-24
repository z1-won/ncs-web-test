"""검토의견서·심의의견서 반영 여부 검토(REQ-02-003) — 의견서(여러 개)와 최종 원고(+ 출력본·반영 전 원고)를 받아 의견별 판정 후보표를 돌려준다.

판정은 ncs_opinion이 맡는다. 검수 결과처럼 저장하지 않는다: 올린 파일은 임시 폴더에서 읽고 바로 지운다.
저장소가 이력을 지원하면(PostgreSQL) 원고 진행 현황(REQ-02-007)에 쓸 **개수만** 남긴다 — 차수별 총 의견·반영 후보·미반영 후보·확인 필요 수와
올린 파일 이름. 의견 문장과 원고 문단은 남기지 않는다. 남기지 못해도 검토 결과는 그대로 돌려준다.
다만 세분류 건의 권에서 열어 돌린 검토는 그 건의 기록으로 보관한다(REQ-02-003 사람 작업 4번): 의견서 파일, 의견별 결과, 담당자 확정
(ncs_service.workflow.opinion_archive). 보관한 검토는 GET /api/opinion/records/{id}로 다시 연다.
"""

import re
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Request, UploadFile

from ..common import Services, error_response, logger, manager_only, own_and_link
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


WHAT = "의견 반영 검토는"      # manager_only가 403에 적는 주어. 반영 여부의 판단은 확인하는 쪽(에디터, 직능연)의 일이다


def register(app: FastAPI, services: Services) -> None:
    register_decisions(app, services)

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
        case_version: Annotated[str, Form()] = "",    # 보관한 판본을 그대로 쓴 것이면 그 판본 id
    ) -> Any:
        """판정 후보표 JSON(ncs_opinion.review). opinions: 검토의견서·심의의견서(PDF·hwp·hwpx), rounds: 의견서 순서대로 '1차'·'2차'·'심의'(선택),
        print_pdf: 최종 원고 출력본(근거 쪽 표시), previous: 반영 전 원고. 판정은 LLM(Claude)이 한다 — 서버에 ANTHROPIC_API_KEY·반출 승인
        (LLM_ALLOW_UPLOAD=1)이 있으면 자동으로 부르고, 없으면 모든 의견이 '확인 필요'와 이유(결과의 'LLM' 값)다. 사용량은 'usage'."""
        from ncs_opinion import review

        manager_only(request, WHAT)
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
            # 건에서 연 검토면 보관할 의견서 내용을 임시 폴더가 지워지기 전에 읽어 둔다(차수는 결과가 읽은 값)
            read_rounds = {item.get("파일"): item.get("차수") or "" for item in result.get("의견서") or []}
            sheet_files = [(read_rounds.get(s.name, ""), s.name, s.read_bytes()) for s in sheets] if case_volume else []
        record = _record(services, final.name, result, files)
        linked = own_and_link(request, services.store, "opinion", record["id"] if record else None, case_volume, case_stage, case_version)
        kept = _keep(services, request, record, result, sheet_files) if linked else False
        return {**result, "진행 현황 기록": record, **({"건에 붙임": linked, "보관": kept} if case_volume else {})}


def register_decisions(app: FastAPI, services: Services) -> None:
    from urllib.parse import quote

    from fastapi import Response

    from ..schemas import OpinionDecisionRequest

    @app.post("/api/opinion/export", responses={400: {"model": ErrorResponse}})
    def opinion_export(body: OpinionDecisionRequest, request: Request) -> Response:
        """결과표 xlsx — 의견별 판정 후보와 담당자 확정(반영/미반영), 근거 문단, 수정 제안, 집필자 확인, 검수 기준. 보관·전달용."""
        manager_only(request, WHAT)
        from ncs_opinion.report import build_xlsx

        try:
            content = build_xlsx(body.manuscript or "원고", body.rows, body.decisions, llm=body.llm)
        except (ValueError, KeyError) as error:
            return error_response(400, f"결과표를 만들지 못했습니다: {error}")
        filename = f"의견반영검토_{Path(body.manuscript or '원고').stem}.xlsx"
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
            "Content-Disposition": f"attachment; filename=opinion_review.xlsx; filename*=UTF-8''{quote(filename)}"})

    @app.get("/api/opinion/records/{record_id}", responses={404: {"model": ErrorResponse}})
    def opinion_record(record_id: str, request: Request) -> Any:
        """보관한 의견 반영 검토(세분류 건에서 돌린 것) — 의견별 결과, 담당자 확정, 의견서 파일 목록. 에디터와 직능연 계정만."""
        manager_only(request, WHAT)
        found = _archive(services, lambda archive, dsn: archive.get(dsn, record_id))
        if found is None:
            return error_response(404, "보관한 의견 반영 검토를 찾을 수 없습니다")
        return {**found, "result": {**found["result"], "진행 현황 기록": {"id": record_id}}}

    @app.get("/api/opinion/records/{record_id}/files/{file_id}", responses={404: {"model": ErrorResponse}})
    def opinion_record_file(record_id: str, file_id: str, request: Request) -> Any:
        """보관한 의견서 파일 하나를 내려받는다."""
        manager_only(request, WHAT)
        found = _archive(services, lambda archive, dsn: archive.file(dsn, record_id, file_id))
        if found is None:
            return error_response(404, "보관한 의견서를 찾을 수 없습니다")
        name, content = found
        return Response(content, media_type="application/octet-stream", headers={
            "Content-Disposition": f"attachment; filename=opinion_sheet; filename*=UTF-8''{quote(name)}"})

    @app.post("/api/opinion/decisions", responses={400: {"model": ErrorResponse}})
    def opinion_decisions(body: OpinionDecisionRequest, request: Request) -> Any:
        """담당자 확정을 그 검토의 진행 현황 기록에 적는다(DB 모드). 적는 것은 의견 번호별 확정값과 개수·오차율뿐이다(의견 글은 넣지 않는다).
        돌려주는 값: {'저장': 적었는가, '확정': 요약, '안내'}. 이력 DB가 없거나 기록이 없으면 저장하지 않고 그렇게 알린다 — 결과표를 내려받아 보관."""
        from datetime import datetime, timezone

        from ncs_opinion.report import decision_summary
        from ncs_service.workflow.progress import OPINION

        manager_only(request, WHAT)
        try:
            summary = decision_summary(body.rows, body.decisions)
        except (ValueError, KeyError, TypeError) as error:
            return error_response(400, f"확정값을 읽지 못했습니다: {error}")
        saved = False
        if body.record_id and services.store.supports_history:
            note = {**{key: summary[key] for key in ("의견별", "확정", "반영", "미반영", "후보와 다름", "보류였던 것")},
                    "오차율": summary["오차율"]["오차율"], "결과": summary["오차율"]["결과"], "확정 시각": datetime.now(timezone.utc).isoformat()}
            try:
                saved = services.store.set_work_record_note(body.record_id, OPINION, "확정", note)
                if saved:      # 보관한 검토(건에서 돌린 것)면 의견별 확정도 그 보관에 적는다 — 다시 열면 확정이 그대로 보인다
                    from ..common import actor

                    picked = {str(key): value for key, value in body.decisions.items() if value}
                    _archive(services, lambda archive, dsn: archive.set_decisions(dsn, body.record_id, picked, name=actor(request, "")))
            except Exception as error:
                logger.exception("의견 반영 검토 확정 저장 실패: %s", error)
        guide = ("담당자 확정을 진행 현황 기록에 저장했습니다." if saved
                 else "확정을 저장하지 못했습니다(이력 DB가 없거나 이 검토의 기록이 없음). 결과표를 내려받아 보관해 주세요.")
        return {"저장": saved, "확정": summary, "안내": guide}


def _archive(services: Services, action):
    """보관 모듈을 부른다. 이력을 두지 않는 서버이거나 id가 잘못됐으면 None."""
    if not services.store.supports_history:
        return None
    import psycopg

    from ncs_service.workflow import opinion_archive

    try:
        return action(opinion_archive, services.store.dsn)
    except psycopg.errors.DataError:      # uuid 꼴이 아닌 id
        return None


def _keep(services: Services, request: Request, record: dict | None, result: dict, sheet_files: list) -> bool:
    """건에 붙은 검토를 보관한다. 실패해도 검토 결과는 그대로 돌려준다."""
    from ..common import actor

    if not record:
        return False
    try:
        return bool(_archive(services, lambda archive, dsn: archive.keep(dsn, record["id"], result, sheet_files, name=actor(request, ""))))
    except Exception as error:
        logger.exception("의견 반영 검토 보관 실패: %s", error)
        return False


def _record(services: Services, manuscript: str, result: dict, files: list[dict]) -> dict | None:
    """진행 현황용 개수 기록. 돌려주는 값: {'id', 'module_code'}(모듈 코드가 비면 어느 원고에도 붙지 않음) 또는 None(DB 없음·실패)."""
    from ncs_service.workflow.progress import OPINION, summarize_opinion

    try:
        return services.store.save_work_record(OPINION, manuscript, summarize_opinion(result), files)
    except Exception as error:      # 기록은 부가 기능이라 검토 결과를 막지 않는다
        logger.exception("의견 반영 검토 개수 기록 실패: %s", error)
        return None
