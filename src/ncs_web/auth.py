"""로그인 — /api/login·/api/logout·/api/me와, 로그인하지 않은 요청을 막는 미들웨어.

로그인은 계정을 둘 데이터베이스가 있을 때만 켜진다(create_app의 require_login). 켜지면 /api/ 아래 모든 경로가 로그인을 요구하고,
열어 두는 것은 OPEN_PATHS뿐이다(로그인 자체, 내 정보 확인, 화면이 처음에 읽는 /api/health). 화면 파일(/, /assets/…)은 막지 않는다 —
화면은 /api/me가 401이면 로그인 화면을 보인다.

쿠키: HttpOnly(스크립트가 읽지 못함), SameSite=Strict(다른 사이트에서 보낸 요청에는 실리지 않음 — CSRF 방어), https로 접속했으면 Secure.
로그인 실패는 아이디마다 세어 FAIL_LIMIT번을 넘으면 LOCK_SECONDS 동안 그 아이디의 시도를 받지 않는다(서버 메모리에만 둔다).
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .common import error_response, logger

COOKIE = "ncs_session"
OPEN_PATHS = {"/api/login", "/api/login/demo", "/api/logout", "/api/me", "/api/health"}
DEMO_PREFIX = "demo-"            # 시연 계정 아이디의 머리(scripts/demo/seed_demo.py가 만든다)
FAIL_LIMIT, LOCK_SECONDS = 5, 60


class Login(BaseModel):
    login: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class Throttle:
    """아이디별 로그인 실패 횟수. 한 프로세스의 메모리에만 있다(서버를 다시 켜면 지워진다)."""

    def __init__(self, limit: int = FAIL_LIMIT, seconds: int = LOCK_SECONDS, clock=time.monotonic):
        self.limit, self.seconds, self.clock = limit, seconds, clock
        self.fails: dict[str, tuple[int, float]] = {}

    def locked(self, login: str) -> bool:
        count, since = self.fails.get(login, (0, 0.0))
        if count >= self.limit and self.clock() - since < self.seconds:
            return True
        if count >= self.limit:
            self.fails.pop(login, None)
        return False

    def failed(self, login: str) -> None:
        count, _ = self.fails.get(login, (0, 0.0))
        self.fails[login] = (count + 1, self.clock())
        if len(self.fails) > 10000:          # 아이디를 바꿔 가며 두드려도 메모리가 끝없이 늘지 않게
            self.fails.clear()

    def passed(self, login: str) -> None:
        self.fails.pop(login, None)


def install(app: FastAPI, store, *, require_login: bool) -> None:
    """로그인 경로를 붙이고, require_login이면 /api/ 요청을 막는 미들웨어를 건다. 통과한 요청에는 request.state.account가 있다."""
    from ncs_service import accounts

    throttle = Throttle()
    app.state.require_login = require_login

    def current(request: Request) -> dict | None:
        return accounts.session_account(store.dsn, request.cookies.get(COOKIE, ""))

    if require_login:
        @app.middleware("http")
        async def guard(request: Request, call_next):
            path = request.url.path
            if path.startswith("/api/") and path not in OPEN_PATHS and request.method != "OPTIONS":
                account = await run_in_threadpool(current, request)
                if account is None:
                    return error_response(401, "로그인이 필요합니다")
                request.state.account = account
            return await call_next(request)

    @app.get("/api/me", response_model=None)
    def me(request: Request) -> Response | dict:
        """지금 로그인한 계정. 로그인을 쓰지 않는 서버(DB 없음)면 {"auth": false} — 화면이 로그인 없이 연다."""
        if not require_login:
            return {"auth": False, "account": None}
        account = current(request)
        if account is None:
            return error_response(401, "로그인이 필요합니다")
        return {"auth": True, "account": account}

    @app.get("/api/login/demo")
    def demo_accounts() -> dict:
        """시연 계정 안내 — 로그인 화면이 역할별 아이디와 비밀번호를 보여 줄 때 읽는다(로그인 전에 열린다).

        환경 변수 NCS_DEMO_PASSWORD(시연 계정을 만들 때 준 비밀번호)가 있을 때만 demo-로 시작하는 켜진 계정과 그 값을 돌려준다.
        없으면 빈 목록이다 — 운영 서버에는 이 값을 두지 않는다. 비밀번호는 저장소에 적지 않고 .env에만 둔다.
        """
        password = os.getenv("NCS_DEMO_PASSWORD", "")
        if not require_login or not password:
            return {"password": None, "accounts": []}
        rows = [row for row in accounts.list_accounts(store.dsn) if row["login"].startswith(DEMO_PREFIX) and row.get("active", True)]
        return {"password": password,
                "accounts": [{key: row.get(key) for key in ("login", "name", "role", "role_name", "org")} for row in rows]}

    @app.post("/api/login", response_model=None)
    def login(body: Login, request: Request, response: Response) -> Response | dict:
        if not require_login:
            return error_response(400, "이 서버는 로그인을 쓰지 않습니다(데이터베이스가 없습니다)")
        name = body.login.strip().lower()
        if throttle.locked(name):
            return error_response(429, f"로그인에 여러 번 실패했습니다. {LOCK_SECONDS}초 뒤에 다시 해 주세요")
        found = accounts.log_in(store.dsn, name, body.password)
        if found is None:
            throttle.failed(name)
            logger.warning("로그인 실패: %s", name)
            return error_response(401, "아이디 또는 비밀번호가 맞지 않습니다")
        throttle.passed(name)
        token, account = found
        response.set_cookie(COOKIE, token, max_age=accounts.SESSION_HOURS * 3600, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", path="/")
        return {"auth": True, "account": account}

    @app.post("/api/logout")
    def logout(request: Request, response: Response) -> dict:
        if require_login:
            accounts.log_out(store.dsn, request.cookies.get(COOKIE, ""))
        response.delete_cookie(COOKIE, path="/")
        return {"auth": require_login, "account": None}
