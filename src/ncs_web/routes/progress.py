"""원고 진행 현황(REQ-02-007 '원고별 편집·내용·저작권 검수 진행도 확인') — 원고(모듈 코드)마다 남아 있는 기록을 단계와 진행도로 보여 준다.

기록(원고 검수·개발계획서 점검 이력, 분량 산정 이력, 의견 반영 검토와 권리 증빙 점검의 개수 기록, 이미지 저작권 DB)은 모아서 보여 주기만 하고,
단계의 완료는 담당자가 직접 표시한다(POST …/stages/{단계} — 누가·언제·메모가 남고 되돌릴 수 있다). 누가 했는지는 로그인한 계정에서 읽는다. 단계와 진행도를 만드는 일은 ncs_service.progress가 한다. 저장소가 이력을 지원할 때(PostgreSQL)만 붙는다.
"""

from fastapi import FastAPI, Query, Request
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from ..common import Services, actor, scope_of


class StageMark(BaseModel):
    """단계 완료 표시·되돌림. 이력에 남는 이름은 로그인한 계정에서 읽는다. by는 로그인을 끈 서버(테스트)에서만 쓴다."""
    done: bool
    by: str = Field(default="", max_length=50)
    note: str = Field(default="", max_length=300)


def module_name(module_code: str) -> str:
    """NCS 목록에서 학습모듈(능력단위) 이름. 목록에 없으면 빈 값."""
    from ncs_core.ncs_catalog import catalog

    listing = catalog()
    unit = listing.unit(module_code.removeprefix("LM")) if listing else None
    return unit.name if unit else ""


def register(app: FastAPI, services: Services) -> None:
    store = services.store
    if not store.supports_history:
        return

    from ncs_service import cases

    def allowed(request: Request, code: str) -> None:
        limit_to = scope_of(request, store)
        if limit_to is not None and code not in limit_to.codes:
            raise HTTPException(404, "원고를 찾지 못했습니다. 담당하는 권의 원고만 볼 수 있습니다")

    @app.get("/api/manuscripts")
    def manuscripts(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> list[dict]:
        """기록이 있는 원고 목록(최근 기록순): 모듈 코드, 학습모듈명, 처음·최근 기록 시각, 기록 수, 기록이 있는 단계 수(7단계 중)."""
        limit_to = scope_of(request, store)
        codes = None if limit_to is None else list(limit_to.codes)      # 집필진은 담당 권만. 그 밖의 역할(검토진, 위원)은 빈 목록
        return [{**row, "name": module_name(row["module_code"])} for row in store.list_manuscripts(limit=limit, offset=offset, codes=codes)]

    @app.get("/api/manuscripts/{module_code}")
    def manuscript_progress(module_code: str, request: Request) -> dict:
        """한 원고의 진행 현황: 단계 7개(담당자의 완료 표시와 근거 기록)와 편집·내용·저작권 검수 진행도, 분량."""
        from ncs_core import validate_module_code

        try:
            code = validate_module_code(module_code)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        allowed(request, code)
        # 기록이 없어도 빈 현황. '건'이 있으면 세분류 건에 든 원고다 — 단계는 건 화면에서 진행하고, 여기서는 기록과 진행도만 본다
        return {**store.get_progress(code, name=module_name(code)), "건": cases.volume_of(store.dsn, code)}

    @app.post("/api/manuscripts/{module_code}/stages/{stage}")
    def mark_stage(module_code: str, stage: int, mark: StageMark, request: Request) -> dict:
        """단계를 완료로 표시하거나(done=true) 되돌린다(false). 바뀐 뒤의 진행 현황을 돌려준다."""
        from ncs_core import validate_module_code
        from ncs_service.progress import STAGE_NUMBERS

        try:
            code = validate_module_code(module_code)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        if stage not in STAGE_NUMBERS:
            raise HTTPException(400, f"단계는 {STAGE_NUMBERS[0]}~{STAGE_NUMBERS[-1]} 중 하나여야 합니다")
        allowed(request, code)
        if cases.volume_of(store.dsn, code):
            raise HTTPException(409, "이 원고는 세분류 건에 들어 있습니다. 단계는 세분류 건 화면에서 진행해 주세요")
        by = actor(request, mark.by)     # 로그인했으면 보낸 이름은 쓰지 않는다
        if not by:
            raise HTTPException(400, "표시한 사람을 알 수 없습니다. 로그인해 주세요")
        store.set_stage(code, stage, done=mark.done, by=by, note=mark.note.strip())
        return {**store.get_progress(code, name=module_name(code)), "건": None}
