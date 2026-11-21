"""세분류 건(REQ-02-007) — 건(세분류 + 사업 연도)을 만들고, 권마다 담당 집필자를 붙이고, 단계의 변화를 사건으로 남긴다.

저장과 권한은 ncs_service.cases, 단계 정의표와 전이는 ncs_service.flow가 맡는다. 여기는 요청을 받아 넘기고 오류를 화면 문구로 바꾼다.
건을 만들고 권·집필자를 바꾸는 일은 에디터와 직능연만 한다. 집필진은 자기가 담당인 권이 든 건만, 그 권만 본다.
누가 했는지는 로그인한 계정에서 읽는다. 저장소가 이력을 지원할 때(PostgreSQL)만 붙는다.
"""

from datetime import date
from uuid import UUID

from fastapi import FastAPI, Query, Request
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from ..common import Services

NO_LOGIN = {"id": None, "name": "로그인 없음", "login": "", "role": "editor"}     # 로그인을 끈 서버(테스트)에서만 쓰인다


class VolumeIn(BaseModel):
    module_code: str = Field(min_length=1, max_length=40)
    title: str = Field(default="", max_length=200)


class CaseIn(BaseModel):
    subclass: str = Field(min_length=8, max_length=8)
    year: int = Field(ge=2000, le=2100)
    improvement: str = Field(max_length=20)
    name: str = Field(default="", max_length=200)
    volumes: list[VolumeIn] = Field(min_length=1, max_length=60)


class AuthorIn(BaseModel):
    author_id: UUID | None = None


class EventIn(BaseModel):
    stage: str = Field(max_length=40)
    action: str = Field(max_length=20)
    volume_id: UUID | None = None
    note: str = Field(default="", max_length=500)


def subclass_listing(subclass: str) -> dict:
    """NCS 목록에서 세분류의 이름과 학습모듈(능력단위) 목록. 목록에 없으면 이름과 권이 빈 값."""
    from ncs_core.ncs_catalog import catalog

    listing = catalog()
    found = listing.subclass(subclass) if listing else None
    if found is None:
        return {"subclass": subclass, "name": "", "volumes": []}
    return {"subclass": subclass, "name": found.name, "volumes": [{"module_code": "LM" + unit.code, "title": unit.name} for unit in found.units]}


def register(app: FastAPI, services: Services) -> None:
    store = services.store
    if not store.supports_history:
        return
    from ncs_service import accounts, cases, flow

    dsn = store.dsn

    def who(request: Request) -> dict:
        return getattr(request.state, "account", None) or NO_LOGIN

    def manager(request: Request) -> dict:
        account = who(request)
        if not cases.can_manage(account):
            raise HTTPException(403, "세분류 건을 만들거나 바꾸는 일은 에디터와 직능연 계정만 할 수 있습니다")
        return account

    def found(case_id: UUID, account: dict) -> dict:
        case = cases.get_case(dsn, str(case_id), account)
        if case is None:
            raise HTTPException(404, "건을 찾지 못했습니다. 목록에서 다시 열어 주세요")     # 볼 수 없는 건도 같은 답 — 있는지 알려 주지 않는다
        return case

    @app.get("/api/cases")
    def case_list(request: Request) -> dict:
        """볼 수 있는 건 목록과, 이 계정이 건을 만들 수 있는지."""
        account = who(request)
        return {"cases": cases.list_cases(dsn, account), "can_manage": cases.can_manage(account)}

    @app.get("/api/cases/options")
    def case_options(request: Request) -> dict:
        """건을 만들고 집필자를 붙일 때 고르는 값: 개선 유형, 올해 연도, 집필진 계정(사용 중인 것)."""
        manager(request)
        authors = [{"id": a["id"], "name": a["name"], "login": a["login"], "org": a["org"]}
                   for a in accounts.list_accounts(dsn) if a["role"] == "author" and a["active"]]
        return {"improvements": list(flow.IMPROVEMENTS), "year": date.today().year, "authors": authors}

    @app.get("/api/cases/lookup")
    def case_lookup(request: Request, subclass: str = Query(min_length=8, max_length=8, pattern=r"^[0-9]{8}$")) -> dict:
        """세분류 코드 → NCS 목록의 세분류 이름과 학습모듈 목록(건을 만들 때 권을 미리 채운다)."""
        manager(request)
        return subclass_listing(subclass)

    @app.post("/api/cases")
    def case_create(body: CaseIn, request: Request) -> dict:
        account = manager(request)
        try:
            case_id = cases.create_case(dsn, subclass=body.subclass, year=body.year, improvement=body.improvement, account=account,
                                        name=body.name or subclass_listing(body.subclass)["name"],
                                        volumes=[volume.model_dump() for volume in body.volumes])
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        return found(case_id, account)

    @app.get("/api/cases/{case_id}")
    def case_get(case_id: UUID, request: Request) -> dict:
        """건 하나: 권(담당 집필자, 단계별 상태), 건 단위 단계, 사건 기록, 단계 정의표."""
        return found(case_id, who(request))

    @app.post("/api/cases/{case_id}/volumes")
    def case_add_volume(case_id: UUID, body: VolumeIn, request: Request) -> dict:
        account = manager(request)
        try:
            added = cases.add_volume(dsn, str(case_id), module_code=body.module_code, title=body.title, account=account)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        if added is None:
            raise HTTPException(404, "건을 찾지 못했습니다. 목록에서 다시 열어 주세요")
        return found(case_id, account)

    @app.post("/api/cases/{case_id}/volumes/{volume_id}/author")
    def case_assign_author(case_id: UUID, volume_id: UUID, body: AuthorIn, request: Request) -> dict:
        """권의 담당 집필자를 정하거나(author_id) 비운다(null)."""
        account = manager(request)
        try:
            ok = cases.assign_author(dsn, str(case_id), str(volume_id), str(body.author_id) if body.author_id else None, account=account)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        if not ok:
            raise HTTPException(404, "권을 찾지 못했습니다. 화면을 새로 고쳐 주세요")
        return found(case_id, account)

    @app.post("/api/cases/{case_id}/events")
    def case_act(case_id: UUID, body: EventIn, request: Request) -> dict:
        """단계에 행동 하나(submit 제출, request 보완 요청, verdict 판정 도착, done 완료, reopen 되돌림)를 적는다. 바뀐 뒤의 건을 돌려준다."""
        account = who(request)
        found(case_id, account)
        try:
            cases.act(dsn, str(case_id), stage=body.stage, action=body.action, account=account,
                      volume_id=str(body.volume_id) if body.volume_id else None, note=body.note)
        except flow.Denied as error:
            raise HTTPException(403, str(error)) from None
        except flow.FlowError as error:
            raise HTTPException(409, str(error)) from None
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        return found(case_id, account)
