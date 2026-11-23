"""경로 모듈(routes/)이 함께 쓰는 것 — 저장소 묶음(Services), 오류 응답, 업로드 역할 풀기, 허용 출처."""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse

from .uploads import UploadStore

# 화면은 같은 출처에서 API를 부른다(빌드본은 이 서버가 함께 내고, Vite dev 서버는 /api를 8765로 프록시한다).
# 그래서 교차 출처 허용은 Vite dev 서버를 프록시 없이 직접 붙일 때만 필요하며, 아래 목록으로 한정한다.
# 예전처럼 "*"로 열어 두면 브라우저에서 방문한 임의의 웹사이트가 이 로컬 API로 보관 원고를 읽거나 이력을 지울 수 있다.
logger = logging.getLogger("ncs_web")
DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def allowed_origins() -> list[str]:
    """NCS_WEB_ORIGINS(쉼표 구분)로 출처를 추가할 수 있다. 빈 값이면 기본 목록만 허용한다."""
    extra = [item.strip() for item in os.getenv("NCS_WEB_ORIGINS", "").split(",") if item.strip()]
    return list(dict.fromkeys([*DEFAULT_ORIGINS, *extra]))


@dataclass
class Services:
    """create_app이 한 번 만들어 경로 모듈마다 넘기는 것. store = 검수 결과 저장소(파일 또는 PostgreSQL), uploads = 업로드 토큰 보관소."""

    store: Any
    uploads: UploadStore


def parse_roles(text: str, count: int) -> list[str] | None:
    """업로드 칸이 정한 역할 목록(JSON 배열, files와 같은 순서·개수). 비어 있으면 None(넣은 순서가 역할)."""
    if not text:
        return None
    try:
        roles = json.loads(text)
    except ValueError:
        roles = None
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        raise ValueError('roles는 ["manuscript", "plan", "print"]처럼 역할 이름의 JSON 배열이어야 합니다')
    if len(roles) != count:
        raise ValueError(f"roles({len(roles)}개)와 files({count}개)의 개수가 다릅니다")
    return roles


def error_response(status: int, message: str, **extra: Any) -> JSONResponse:
    # charset을 명시해 브라우저가 JSON을 직접 표시할 때 한국어 메시지가 깨지지 않게 한다.
    return JSONResponse({"error": message, **extra}, status_code=status,
                        media_type="application/json; charset=utf-8")


def actor(request, given: str = "") -> str:
    """변경 이력에 남길 '누가'. 로그인했으면 계정의 이름(아이디) — 화면이 보낸 이름은 쓰지 않는다. 로그인을 끈 서버(테스트)에서만 given을 쓴다."""
    account = getattr(request.state, "account", None)
    return f"{account['name']}({account['login']})" if account else (given or "").strip()


def viewer(request) -> dict | None:
    """로그인한 계정. 로그인을 쓰지 않는 서버면 None."""
    return getattr(request.state, "account", None)


def scope_of(request, store):
    """이 요청이 볼 수 있는 기록의 범위(ncs_service.auth.access.Scope). None이면 전부 — 에디터, 직능연, 로그인을 쓰지 않는 서버."""
    from ncs_service.auth import access

    return access.scope(store.dsn, viewer(request))


def own_and_link(request, store, tool: str, record_id: str | None, case_volume: str = "", case_stage: str = "", case_version: str = "") -> bool:
    """방금 남긴 기록에 돌린 계정을 적고, 세분류 건의 권·단계에서 열어 돌린 것이면 거기에 붙인다. 붙였으면 True.
    tool = review / volume / opinion / rights. 기록이 없으면(저장 실패, DB 없음) 아무것도 하지 않는다."""
    from ncs_service.auth import access

    if not record_id or not store.supports_history:
        return False
    account = viewer(request)
    kind = access.LINKABLE.get(tool, "review")
    try:
        access.set_owner(store.dsn, kind, record_id, account.get("id") if account else None)
        if case_volume and case_stage and tool in access.LINKABLE:
            return access.link(store.dsn, tool, record_id, case_volume, case_stage, account, case_version)
    except Exception as error:      # 부가 정보라 결과를 막지 않는다
        logger.exception("기록의 계정·단계 표시 실패: %s", error)
    return False
