"""계정과 로그인 세션 — 회원가입은 없고 관리자가 명령으로 계정을 미리 만든다(설계: 세분류 건 흐름과 역할 v0.2).

  python -m ncs_service.accounts add --login kim --name "김에디터" --role editor --org "에디팅기관"   # 비밀번호는 물어본다
  python -m ncs_service.accounts list
  python -m ncs_service.accounts password --login kim
  python -m ncs_service.accounts disable --login kim        # 다시 쓰려면 enable

DATABASE_URL(또는 --database-url)이 가리키는 PostgreSQL에 쓴다. 계정을 둘 곳이 필요하므로 로그인은 DB가 있는 서버에서만 된다.

- 비밀번호는 원문을 저장하지 않는다: scrypt(표준 라이브러리 hashlib)로 만든 값과 소금만 'scrypt$N$r$p$소금$값' 꼴로 둔다.
- 세션: 로그인하면 무작위 토큰을 쿠키로 주고, DB에는 토큰의 sha256만 둔다(DB가 새도 쿠키를 만들 수 없다). 기한은 SESSION_HOURS.
- 역할(ROLES)은 과업 안내의 참여 주체 다섯. 무엇을 볼 수 있는지는 역할과 담당 권으로 거른다(이 모듈은 계정까지만 맡는다).
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import os
import secrets
import sys
from datetime import timedelta

ROLES = {"krivet": "직능연", "author": "집필진", "editor": "에디터", "reviewer": "검토진", "committee": "소위원회 위원"}
SESSION_HOURS = 12
MIN_PASSWORD = 8
SCRYPT = (2 ** 14, 8, 1)      # N, r, p — 계정 수가 적은 내부 도구 기준(OWASP 권고 최소값)
ACCOUNT_COLUMNS = "id, login, name, role, org, active, created_at"


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"비밀번호는 {MIN_PASSWORD}자 이상이어야 합니다")
    n, r, p = SCRYPT
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return "$".join(["scrypt", str(n), str(r), str(p), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()])


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public(row: dict) -> dict:
    return {"id": str(row["id"]), "login": row["login"], "name": row["name"], "role": row["role"], "role_name": ROLES.get(row["role"], row["role"]),
            "org": row["org"], "active": row["active"]}


# --- DB --------------------------------------------------------------------------------

def _connect(dsn: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(dsn, row_factory=dict_row)


def create_account(dsn: str, *, login: str, name: str, role: str, org: str = "", password: str) -> dict:
    from uuid import uuid4

    login = login.strip().lower()
    if not login or not name.strip():
        raise ValueError("아이디와 이름이 필요합니다")
    if role not in ROLES:
        raise ValueError("역할은 " + " / ".join(ROLES) + " 중 하나여야 합니다")
    hashed = hash_password(password)
    with _connect(dsn) as connection:
        if connection.execute("SELECT 1 FROM accounts WHERE login = %s", (login,)).fetchone():
            raise ValueError(f"이미 있는 아이디입니다: {login}")
        row = connection.execute(
            f"INSERT INTO accounts (id, login, name, role, org, password_hash) VALUES (%s, %s, %s, %s, %s, %s) RETURNING {ACCOUNT_COLUMNS}",
            (str(uuid4()), login, name.strip(), role, org.strip(), hashed)).fetchone()
    return _public(row)


def list_accounts(dsn: str) -> list[dict]:
    with _connect(dsn) as connection:
        return [_public(row) for row in connection.execute(f"SELECT {ACCOUNT_COLUMNS} FROM accounts ORDER BY role, login").fetchall()]


def set_password(dsn: str, login: str, password: str) -> bool:
    """비밀번호를 바꾸고 그 계정의 세션을 모두 끊는다."""
    hashed = hash_password(password)
    with _connect(dsn) as connection:
        row = connection.execute("UPDATE accounts SET password_hash = %s WHERE login = %s RETURNING id", (hashed, login.strip().lower())).fetchone()
        if row:
            connection.execute("DELETE FROM account_sessions WHERE account_id = %s", (row["id"],))
    return row is not None


def set_active(dsn: str, login: str, active: bool) -> bool:
    with _connect(dsn) as connection:
        row = connection.execute("UPDATE accounts SET active = %s WHERE login = %s RETURNING id", (active, login.strip().lower())).fetchone()
        if row and not active:
            connection.execute("DELETE FROM account_sessions WHERE account_id = %s", (row["id"],))
    return row is not None


def log_in(dsn: str, login: str, password: str) -> tuple[str, dict] | None:
    """아이디·비밀번호가 맞고 쓰는 계정이면 (쿠키에 줄 토큰, 계정). 아니면 None — 어느 쪽이 틀렸는지는 알려 주지 않는다."""
    with _connect(dsn) as connection:
        row = connection.execute(f"SELECT {ACCOUNT_COLUMNS}, password_hash FROM accounts WHERE login = %s", (login.strip().lower(),)).fetchone()
        # 없는 아이디여도 같은 시간이 걸리게 한 번 계산한다(아이디가 있는지 응답 시간으로 알 수 없게)
        ok = verify_password(password, row["password_hash"] if row else hash_password("없는 계정용 자리 값"))
        if not (row and ok and row["active"]):
            return None
        token = secrets.token_urlsafe(32)
        connection.execute("DELETE FROM account_sessions WHERE expires_at < now()")
        connection.execute("INSERT INTO account_sessions (token_hash, account_id, expires_at) VALUES (%s, %s, now() + %s)",
                           (token_hash(token), row["id"], timedelta(hours=SESSION_HOURS)))
    return token, _public(row)


def session_account(dsn: str, token: str) -> dict | None:
    """쿠키의 토큰 → 계정(기한이 남았고 쓰는 계정일 때만)."""
    if not token:
        return None
    with _connect(dsn) as connection:
        row = connection.execute(
            f"SELECT {', '.join('a.' + c for c in ACCOUNT_COLUMNS.split(', '))} FROM account_sessions s JOIN accounts a ON a.id = s.account_id "
            "WHERE s.token_hash = %s AND s.expires_at > now() AND a.active", (token_hash(token),)).fetchone()
    return _public(row) if row else None


def log_out(dsn: str, token: str) -> None:
    if token:
        with _connect(dsn) as connection:
            connection.execute("DELETE FROM account_sessions WHERE token_hash = %s", (token_hash(token),))


# --- 관리자 명령 --------------------------------------------------------------------------

def _ask_password() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")       # 스크립트에서: echo 비밀번호 | python -m ncs_service.accounts add …
    first = getpass.getpass("비밀번호: ")
    if first != getpass.getpass("비밀번호 확인: "):
        raise ValueError("두 번 적은 비밀번호가 다릅니다")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncs_service.accounts", description="계정을 만들고 관리한다(회원가입 없음).")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL 주소(기본: DATABASE_URL)")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="계정 만들기(비밀번호는 물어본다)")
    add.add_argument("--login", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--role", required=True, choices=list(ROLES), help=", ".join(f"{k}={v}" for k, v in ROLES.items()))
    add.add_argument("--org", default="")
    commands.add_parser("list", help="계정 목록")
    for name, text in (("password", "비밀번호 바꾸기"), ("disable", "계정 막기"), ("enable", "막은 계정 다시 쓰기")):
        commands.add_parser(name, help=text).add_argument("--login", required=True)
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.exit(2, "DATABASE_URL이 필요합니다(계정은 데이터베이스에 둡니다)\n")
    from .postgres import migrate

    try:
        migrate(args.database_url)
        if args.command == "add":
            made = create_account(args.database_url, login=args.login, name=args.name, role=args.role, org=args.org, password=_ask_password())
            print(f"만듦: {made['login']} ({made['name']}, {made['role_name']})")
        elif args.command == "list":
            for row in list_accounts(args.database_url):
                print(f"{row['login']}\t{row['name']}\t{row['role_name']}\t{row['org']}\t{'사용' if row['active'] else '막음'}")
        elif args.command == "password":
            found = set_password(args.database_url, args.login, _ask_password())
            print("바꿈" if found else "없는 아이디입니다")
            return 0 if found else 1
        else:
            found = set_active(args.database_url, args.login, args.command == "enable")
            print(("다시 씀" if args.command == "enable" else "막음") if found else "없는 아이디입니다")
            return 0 if found else 1
    except ValueError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
