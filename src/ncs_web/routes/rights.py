"""권리 증빙 제출 현황 점검(REQ-02-014) — 원고와 제출 서류(작성된 한글 양식)를 올려 현황표와 누락 목록을 받는다.

  POST /api/rights/check    manuscript(원고 1개) + forms(서류 여러 개) + 날짜·제출 여부 → 점검 결과
                            print_copy(출력본 PDF, 선택)를 함께 주면 그림이 놓인 쪽을 읽어 결과물 현황의 쪽수와 대조한다
                            save=true면 결과를 이미지 저작권 DB에 잇는다(PostgreSQL일 때만, by·모듈 코드 필요)
  POST /api/rights/export   점검 결과(JSON) → 현황표 xlsx
데이터베이스 없이도 점검은 된다. 올린 파일은 점검하는 동안만 임시 폴더에 두고 지운다 — 서류 파일과 그 본문은 서버에 남지 않는다.
이미지 저작권 DB에 반영할 때 남는 것은 그림 파일·수록 위치·제작 방식·AI 표기와 증빙의 종류·서류 파일 이름·제출일뿐이다.
"""

import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from starlette.exceptions import HTTPException

from ..common import Services, actor, logger, own_and_link

MAX_BYTES = 200 << 20      # 원고 + 서류 합계 상한(업로드 보관함과 같은 200MB)
MAX_FORMS = 30
PORTRAIT = ("unknown", "none", "submitted")


def _day(text: str, name: str) -> date | None:
    if not text.strip():
        return None
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise HTTPException(400, f"{name}은(는) YYYY-MM-DD 날짜여야 합니다") from None


def register(app: FastAPI, services: Services) -> None:
    store = services.store

    @app.post("/api/rights/check")
    def rights_check(
        request: Request,
        manuscript: Annotated[UploadFile, File()],
        forms: Annotated[list[UploadFile] | None, File()] = None,
        print_copy: Annotated[UploadFile | None, File()] = None,
        first_review_on: Annotated[str, Form()] = "", submitted_on: Annotated[str, Form()] = "",
        transfer_author: Annotated[bool, Form()] = False, transfer_maker: Annotated[bool, Form()] = False,
        portrait: Annotated[str, Form()] = "unknown", pledge: Annotated[bool, Form()] = False,
        save: Annotated[bool, Form()] = False, by: Annotated[str, Form()] = "", module_code: Annotated[str, Form()] = "",
        case_volume: Annotated[str, Form()] = "",     # 세분류 건의 권에서 열어 돌린 것이면 그 권 id와 단계 — 개수 기록이 그 단계에 붙는다
        case_stage: Annotated[str, Form()] = "",
        case_version: Annotated[str, Form()] = "",    # 보관한 판본을 그대로 쓴 것이면 그 판본 id
    ) -> dict[str, Any]:
        from ncs_core.module_code import resolve_module_code
        from ncs_rights.check import Options
        from ncs_rights.service import run

        if portrait not in PORTRAIT:
            raise HTTPException(400, "portrait는 unknown / none / submitted 중 하나여야 합니다")
        options = Options(first_review_on=_day(first_review_on, "1차 검토일"), submitted_on=_day(submitted_on, "제출일"),
                          transfer_author=transfer_author, transfer_maker=transfer_maker, portrait=portrait, pledge=pledge)
        named = [item for item in forms or [] if item.filename]
        if len(named) > MAX_FORMS:
            raise HTTPException(400, f"서류는 한 번에 {MAX_FORMS}개까지 올릴 수 있습니다")
        if save:
            from ncs_service.workflow.flow import MANAGER_ROLES

            account = getattr(request.state, "account", None)
            if account is not None and account.get("role") not in MANAGER_ROLES:
                raise HTTPException(403, "이미지 저작권 DB에 반영하는 일은 에디터와 직능연 계정만 할 수 있습니다")
        if save and not store.supports_history:
            raise HTTPException(400, "이미지 저작권 DB에 반영하려면 데이터베이스(DATABASE_URL)가 필요합니다")
        by = actor(request, by)      # 로그인했으면 계정 이름 — 보낸 이름은 쓰지 않는다
        if save and not by:
            raise HTTPException(400, "by(변경한 사람)가 필요합니다 — 변경 이력에 남습니다")
        with tempfile.TemporaryDirectory(prefix="ncs_rights_") as folder:
            total = 0

            def keep(item: UploadFile, sub: str) -> Path:
                nonlocal total
                name = Path((item.filename or "").replace("\\", "/")).name     # 브라우저가 보낸 경로는 버리고 이름만 쓴다
                if not name or name in (".", ".."):
                    raise HTTPException(400, f"쓸 수 없는 파일 이름입니다: {item.filename}")
                target = Path(folder) / sub / name
                if target.exists():
                    raise HTTPException(400, f"같은 이름의 서류가 두 번 올라왔습니다: {name}")
                data = item.file.read(MAX_BYTES - total + 1)
                total += len(data)
                if total > MAX_BYTES:
                    raise HTTPException(400, f"올린 파일의 합계가 {MAX_BYTES >> 20}MB를 넘습니다")
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(data)
                return target

            manuscript_path = keep(manuscript, "manuscript")
            form_paths = [keep(item, "forms") for item in named]
            print_path = keep(print_copy, "print") if print_copy is not None and print_copy.filename else None
            try:
                report = run(manuscript_path, form_paths, options, print_copy=print_path)
            except ValueError as error:
                raise HTTPException(400, str(error)) from None
            report["저장"] = None
            if save:
                from ncs_service.images.rights_link import save_to_image_db

                try:
                    code = resolve_module_code(manuscript_path, module_code)
                except ValueError as error:
                    raise HTTPException(400, f"이미지 저작권 DB에 반영하려면 모듈 코드가 필요합니다: {error}") from None
                report["저장"] = {"모듈 코드": code, **save_to_image_db(
                    store.dsn, manuscript_path, code, report, by=by, submitted_on=options.submitted_on)}
            # 원고 진행 현황(REQ-02-007)에 쓸 개수만 남긴다(판정·그림 수·누락 수와 파일 이름). 현황표·지적사항은 남기지 않는다
            report["진행 현황 기록"] = None
            try:
                from ncs_service.workflow.progress import RIGHTS, summarize_rights

                files = [{"role": "manuscript", "filename": manuscript_path.name}] + [{"role": "form", "filename": p.name} for p in form_paths]
                report["진행 현황 기록"] = store.save_work_record(RIGHTS, manuscript_path.name, summarize_rights(report), files,
                                                              module_code=module_code)
                record = report["진행 현황 기록"]
                linked = own_and_link(request, store, "rights", record["id"] if record else None, case_volume, case_stage, case_version)
                if case_volume:
                    report["건에 붙임"] = linked
            except Exception as error:      # 기록은 부가 기능이라 점검 결과를 막지 않는다
                logger.exception("권리 증빙 점검 개수 기록 실패: %s", error)
        return report

    @app.post("/api/rights/export")
    def rights_export(report: dict[str, Any]) -> Response:
        from ncs_rights.report import build_xlsx

        try:
            content = build_xlsx(report)
        except (KeyError, TypeError) as error:
            raise HTTPException(400, f"점검 결과의 모양이 맞지 않습니다: {error}") from None
        name = Path(str(report.get("원고", {}).get("파일") or "원고")).stem
        filename = f"권리증빙_제출현황_{name}.xlsx"
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
            "Content-Disposition": f"attachment; filename=rights.xlsx; filename*=UTF-8''{quote(filename)}"})
