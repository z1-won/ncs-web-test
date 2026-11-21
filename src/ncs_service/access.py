"""기록을 누가 볼 수 있는가(REQ-04-002) — 검수 이력, 분량 산정 이력, 개수 기록에 '돌린 계정'과 '어느 권의 어느 단계 것인지'를 붙이고 거른다.

- 에디터와 직능연은 전부 본다(scope가 None).
- 집필진은 자기가 담당인 권(모듈 코드)의 기록과 자기가 돌린 기록만 본다. 검토진과 위원은 자기가 돌린 기록만 본다.
- 볼 수 없는 기록은 '없음'으로 답한다(있는지 알려 주지 않는다). 지우는 것도 볼 수 있는 기록만 된다.
- 건 밖에서 돌린 실행(단독 실행)은 어느 권에도 붙지 않는다. 돌린 사람과 에디터, 직능연만 본다.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import flow

TABLES = {"review": "review_runs", "volume": "volume_runs", "record": "work_records"}
LINKABLE = {"volume": "volume", "opinion": "record", "rights": "record"}     # 단계의 도구(flow.Stage.tools) → 기록 종류


@dataclass(frozen=True)
class Scope:
    codes: tuple[str, ...]      # 담당하는 권의 모듈 코드
    account_id: str | None

    def clause(self, prefix: str = "") -> tuple[str, tuple]:
        """목록을 거르는 SQL 조건과 값."""
        return f"({prefix}module_code = ANY(%s) OR {prefix}account_id = %s)", (list(self.codes), self.account_id)

    def sees(self, module_code: str, owner_id: str | None) -> bool:
        return module_code in self.codes or (owner_id is not None and str(owner_id) == str(self.account_id))


def _connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn)


def scope(dsn: str, account: dict | None) -> Scope | None:
    """이 계정이 볼 수 있는 범위. None이면 전부(에디터, 직능연, 로그인을 쓰지 않는 서버)."""
    if account is None or account.get("role") in flow.MANAGER_ROLES:
        return None
    codes: tuple[str, ...] = ()
    if account.get("role") == "author" and account.get("id"):
        with _connect(dsn) as connection:
            codes = tuple(row[0] for row in connection.execute("SELECT DISTINCT module_code FROM case_volumes WHERE author_id = %s", (account["id"],)))
    return Scope(codes, account.get("id"))


def set_owner(dsn: str, kind: str, record_id: str, account_id: str | None) -> None:
    """기록에 돌린 계정을 적는다."""
    if account_id:
        with _connect(dsn) as connection:
            connection.execute(f"UPDATE {TABLES[kind]} SET account_id = %s WHERE id = %s", (account_id, record_id))


def allowed(dsn: str, limit: Scope | None, kind: str, record_id: str) -> bool:
    """이 범위에서 그 기록을 볼 수 있는가. kind = review / volume / record / group(전체 실행 묶음). 없는 기록은 True(없음은 호출한 쪽이 답한다)."""
    if limit is None:
        return True
    try:
        with _connect(dsn) as connection:
            if kind == "group":
                rows = connection.execute("SELECT module_code, account_id FROM review_runs WHERE group_id = %s", (record_id,)).fetchall()
            else:
                rows = connection.execute(f"SELECT module_code, account_id FROM {TABLES[kind]} WHERE id = %s", (record_id,)).fetchall()
    except Exception:      # id 형식이 틀린 것 등 — '없음'은 원래 경로가 답한다
        return True
    return all(limit.sees(code, owner) for code, owner in rows)


def link(dsn: str, tool: str, record_id: str, volume_id: str, stage: str, account: dict | None) -> bool:
    """기록을 세분류 건의 권과 단계에 붙인다(분량 산정 → volume_runs, 의견 반영 검토와 권리 증빙 점검 → work_records).
    그 단계의 도구가 아니거나, 집필진이 담당이 아닌 권이면 붙이지 않고 False."""
    definition = flow.BY_KEY.get(stage)
    if definition is None or tool not in definition.tools:
        return False
    with _connect(dsn) as connection:
        volume = connection.execute("SELECT author_id FROM case_volumes WHERE id = %s", (volume_id,)).fetchone()
        if volume is None:
            return False
        if account is not None and account.get("role") not in flow.MANAGER_ROLES and str(volume[0] or "") != str(account.get("id") or "-"):
            return False
        connection.execute(f"UPDATE {TABLES[LINKABLE[tool]]} SET case_volume_id = %s, case_stage = %s WHERE id = %s", (volume_id, stage, record_id))
    return True
