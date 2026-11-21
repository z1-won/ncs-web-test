"""세분류 건(REQ-02-007) — 건(세분류 + 사업 연도) → 권(학습모듈 한 권, 담당 집필자) → 판본 → 사건을 PostgreSQL에 둔다.

- 주문의 단위는 세분류 한 건이다. 권은 그 세분류의 학습모듈이고, 모듈 코드의 앞 8자리(LM 다음)가 세분류와 같아야 한다.
- 모든 변화는 사건(case_events)으로만 남긴다: 누가(계정), 언제, 어느 단계에 무엇을, 어떤 메모와 근거로. 지우거나 고치지 않는다.
  단계의 상태는 저장하지 않고 사건을 접어서 얻는다(flow.states). 전이와 권한은 flow가 판단한다.
- 볼 수 있는 범위: 에디터와 직능연은 전부, 집필진은 자기가 담당인 권과 그 권의 사건만(건 단위 단계는 상태만). 검토진과 위원의 화면은 아직 없다.
- 원고 진행 현황(모듈 코드별 7단계)의 완료 표시와의 관계: 권을 건에 넣을 때 이미 있던 완료 표시를 사건으로 옮겨 오고(adopt),
  그 뒤 진행 현황에서 표시하거나 되돌리면 같은 트랜잭션에서 사건도 남긴다(mirror_stage_mark). 사건 쪽이 빠지는 일이 없다.
"""

from __future__ import annotations

import json
from uuid import uuid4

from . import flow

LEGACY_NOTE = "원고 진행 현황에서 표시"
EVENT_LIMIT = 300


def _connect(dsn: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(dsn, row_factory=dict_row)


def actor_name(account: dict) -> str:
    return f"{account['name']}({account['login']})" if account.get("login") else account["name"]


def can_manage(account: dict) -> bool:
    return account.get("role") in flow.MANAGER_ROLES


def _event(connection, case_id: str, *, action: str, actor: str, actor_id: str | None = None, volume_id: str | None = None, stage: str = "",
           note: str = "", proxy: bool = False, evidence: dict | None = None, at=None) -> str:
    event_id = str(uuid4())
    connection.execute(
        "INSERT INTO case_events (id, case_id, volume_id, stage, action, actor_id, actor, proxy, note, evidence, at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, COALESCE(%s, now()))",
        (event_id, case_id, volume_id, stage, action, actor_id, actor, proxy, note, json.dumps(evidence or {}, ensure_ascii=False), at))
    return event_id


def _volume_code(subclass: str, module_code: str) -> str:
    from ncs_core import validate_module_code

    code = validate_module_code(module_code)
    if code[2:10] != subclass:
        raise ValueError(f"{code}은 세분류 {subclass}의 학습모듈이 아닙니다")
    return code


def _add_volume(connection, case_id: str, subclass: str, module_code: str, title: str, account: dict) -> str:
    code = _volume_code(subclass, module_code)
    if connection.execute("SELECT 1 FROM case_volumes WHERE case_id = %s AND module_code = %s", (case_id, code)).fetchone():
        raise ValueError(f"{code}은 이미 이 건에 들어 있습니다")
    volume_id = str(uuid4())
    connection.execute("INSERT INTO case_volumes (id, case_id, module_code, title) VALUES (%s, %s, %s, %s)", (volume_id, case_id, code, title.strip()))
    _event(connection, case_id, action=flow.VOLUME_ADDED, actor=actor_name(account), actor_id=account.get("id"), volume_id=volume_id, note=code)
    # 이미 있던 완료 표시(원고 진행 현황)를 사건으로 옮겨 온다 — 표시한 사람과 시각은 그때의 것
    marks = connection.execute("SELECT stage, done_by, done_at, note FROM manuscript_stages WHERE module_code = %s ORDER BY stage", (code,)).fetchall()
    for mark in marks:
        for stage in flow.legacy_stages(mark["stage"]):
            _event(connection, case_id, action=flow.COMPLETE, actor=mark["done_by"], stage=stage.key, at=mark["done_at"],
                   volume_id=None if stage.unit == flow.CASE else volume_id,
                   note=" ".join(filter(None, [LEGACY_NOTE + ".", mark["note"]])), evidence={"from": "manuscript_stages", "module_code": code})
    return volume_id


def create_case(dsn: str, *, subclass: str, year: int, improvement: str, account: dict, name: str = "", volumes: list[dict] = ()) -> str:
    """건을 만들고 권을 넣는다. volumes = [{'module_code', 'title'}]. 같은 세분류·연도의 건이 있으면 ValueError."""
    subclass = (subclass or "").strip()
    if not (subclass.isdigit() and len(subclass) == 8):
        raise ValueError("세분류 코드는 숫자 8자리입니다")
    if improvement not in flow.IMPROVEMENTS:
        raise ValueError("개선 유형은 " + ", ".join(flow.IMPROVEMENTS) + " 중 하나입니다")
    if not volumes:
        raise ValueError("권을 하나 이상 넣어 주세요")
    case_id = str(uuid4())
    with _connect(dsn) as connection:
        if connection.execute("SELECT 1 FROM cases WHERE subclass = %s AND year = %s", (subclass, year)).fetchone():
            raise ValueError(f"{year}년 세분류 {subclass} 건이 이미 있습니다")
        connection.execute("INSERT INTO cases (id, subclass, year, name, improvement, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
                           (case_id, subclass, year, name.strip(), improvement, actor_name(account)))
        _event(connection, case_id, action=flow.CREATED, actor=actor_name(account), actor_id=account.get("id"), note=improvement)
        for volume in volumes:
            _add_volume(connection, case_id, subclass, volume["module_code"], volume.get("title", ""), account)
    return case_id


def add_volume(dsn: str, case_id: str, *, module_code: str, title: str = "", account: dict) -> str | None:
    with _connect(dsn) as connection:
        case = connection.execute("SELECT subclass FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone()
        return _add_volume(connection, case_id, case["subclass"], module_code, title, account) if case else None


def assign_author(dsn: str, case_id: str, volume_id: str, author_id: str | None, *, account: dict) -> bool:
    """권의 담당 집필자를 정하거나(author_id) 비운다(None). 집필진 역할의 쓰는 계정만 붙일 수 있다. 권이 없으면 False."""
    with _connect(dsn) as connection:
        volume = connection.execute("SELECT author_id FROM case_volumes WHERE id = %s AND case_id = %s FOR UPDATE", (volume_id, case_id)).fetchone()
        if volume is None:
            return False
        label = "담당 없음"
        if author_id:
            author = connection.execute("SELECT name, login, role, active FROM accounts WHERE id = %s", (author_id,)).fetchone()
            if author is None or author["role"] != "author" or not author["active"]:
                raise ValueError("집필진 역할의 사용 중인 계정만 담당으로 정할 수 있습니다")
            label = f"{author['name']}({author['login']})"
        if str(volume["author_id"] or "") == str(author_id or ""):
            return True
        connection.execute("UPDATE case_volumes SET author_id = %s WHERE id = %s", (author_id, volume_id))
        _event(connection, case_id, action=flow.AUTHOR_SET, actor=actor_name(account), actor_id=account.get("id"), volume_id=volume_id, note=label)
    return True


def _stage_events(connection, case_id: str) -> list[dict]:
    rows = connection.execute("SELECT volume_id, stage, action, at, actor, note FROM case_events WHERE case_id = %s AND stage <> '' ORDER BY seq",
                              (case_id,)).fetchall()
    return [{**row, "volume_id": str(row["volume_id"]) if row["volume_id"] else None} for row in rows]


def act(dsn: str, case_id: str, *, stage: str, action: str, account: dict, volume_id: str | None = None, note: str = "",
        evidence: dict | None = None) -> str:
    """단계에 행동 하나(제출, 보완 요청, 판정 도착, 완료, 되돌림)를 적는다. 전이와 권한은 flow가 판단하고, 안 되면 FlowError(권한이면 Denied).
    돌려주는 값은 바뀐 뒤의 상태."""
    definition = flow.BY_KEY.get(stage)
    if definition is None:
        raise flow.FlowError("없는 단계입니다")
    if (definition.unit == flow.VOLUME) != bool(volume_id):
        raise flow.FlowError(f"‘{definition.name}’은 {definition.unit} 단위 단계입니다")
    ok, proxy = flow.allowed(definition, action, account.get("role", ""))
    if not ok:
        raise flow.Denied(f"‘{definition.name}’의 ‘{flow.ACTIONS.get(action, action)}’은 이 계정의 역할로 할 수 없습니다")
    with _connect(dsn) as connection:
        if connection.execute("SELECT 1 FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone() is None:
            raise LookupError("건이 없습니다")
        if volume_id:
            volume = connection.execute("SELECT author_id FROM case_volumes WHERE id = %s AND case_id = %s", (volume_id, case_id)).fetchone()
            if volume is None:
                raise LookupError("권이 없습니다")
            if account.get("role") == "author" and str(volume["author_id"] or "") != str(account.get("id") or "-"):
                raise flow.Denied("담당하는 권에만 적을 수 있습니다")
        now = flow.states(_stage_events(connection, case_id)).get((volume_id, stage), flow.blank())
        target = flow.next_state(definition, now["state"], action, note=note, before=now["before"])
        _event(connection, case_id, action=action, actor=actor_name(account), actor_id=account.get("id"), volume_id=volume_id, stage=stage,
               note=note.strip(), proxy=proxy, evidence=evidence)
    return target


def mirror_stage_mark(connection, module_code: str, legacy_stage: int, *, done: bool, by: str, note: str = "") -> int:
    """원고 진행 현황의 완료 표시·되돌림을 그 권이 든 건(가장 최근 연도)의 사건으로도 남긴다. set_stage의 트랜잭션 안에서 부른다.
    connection은 기본(튜플) 행의 연결이다. 건에 없는 원고면 아무것도 하지 않는다. 이미 그 상태면 남기지 않는다. 남긴 사건 수를 돌려준다."""
    volume = connection.execute(
        "SELECT v.id, v.case_id FROM case_volumes v JOIN cases c ON c.id = v.case_id WHERE v.module_code = %s ORDER BY c.year DESC LIMIT 1",
        (module_code,)).fetchone()
    if volume is None:
        return 0
    volume_id, case_id = str(volume[0]), str(volume[1])
    rows = connection.execute("SELECT volume_id, stage, action, at, actor, note FROM case_events WHERE case_id = %s AND stage <> '' ORDER BY seq",
                              (case_id,)).fetchall()
    events = [{"volume_id": str(row[0]) if row[0] else None, "stage": row[1], "action": row[2], "at": row[3], "actor": row[4], "note": row[5]}
              for row in rows]
    current = flow.states(events)
    written = 0
    for stage in flow.legacy_stages(legacy_stage):
        key = (None if stage.unit == flow.CASE else volume_id, stage.key)
        is_done = current.get(key, flow.blank())["state"] == flow.DONE
        if is_done == done:
            continue
        _event(connection, case_id, action=flow.COMPLETE if done else flow.REOPEN, actor=by, stage=stage.key, volume_id=key[0],
               note=" ".join(filter(None, [LEGACY_NOTE + ".", note])), evidence={"from": "manuscript_stages", "module_code": module_code})
        written += 1
    return written


def _visible(account: dict) -> tuple[str, tuple]:
    """권을 거르는 SQL 조건과 값. 에디터·직능연은 전부, 집필진은 담당 권만, 그 밖의 역할은 아직 아무것도 보지 않는다."""
    if can_manage(account):
        return "true", ()
    if account.get("role") == "author" and account.get("id"):
        return "v.author_id = %s", (account["id"],)
    return "false", ()


def _progress(volume_states: list[dict]) -> dict:
    total = len(volume_states) * len(flow.VOLUME_STAGES)
    done = sum(1 for states in volume_states for state in states.values() if state["state"] == flow.DONE)
    return {"done": done, "total": total}


def _volume_states(current: dict, volume_id: str) -> dict:
    return {stage.key: current.get((volume_id, stage.key), flow.blank()) for stage in flow.VOLUME_STAGES}


def list_cases(dsn: str, account: dict) -> list[dict]:
    """볼 수 있는 건 목록(최근 연도, 세분류 순): 권 수, 담당이 정해진 권 수, 권 단계 진도(완료 수/전체)."""
    where, values = _visible(account)
    with _connect(dsn) as connection:
        cases = connection.execute(
            "SELECT c.id, c.subclass, c.year, c.name, c.improvement, c.created_at, count(v.id) AS volumes, count(v.author_id) AS assigned, "
            "array_agg(v.id) AS volume_ids FROM cases c JOIN case_volumes v ON v.case_id = c.id "
            f"WHERE {where} GROUP BY c.id ORDER BY c.year DESC, c.subclass", values).fetchall()
        out = []
        for case in cases:
            current = flow.states(_stage_events(connection, str(case["id"])))
            ids = [str(v) for v in case.pop("volume_ids")]
            out.append({**case, "id": str(case["id"]), "progress": _progress([_volume_states(current, v) for v in ids])})
    return out


def get_case(dsn: str, case_id: str, account: dict) -> dict | None:
    """건 하나: 권(담당 집필자, 단계별 상태), 건 단위 단계의 상태, 사건 기록(최근순), 단계 정의표. 볼 수 있는 권이 없으면 None."""
    where, values = _visible(account)
    with _connect(dsn) as connection:
        case = connection.execute("SELECT id, subclass, year, name, improvement, created_by, created_at FROM cases WHERE id = %s", (case_id,)).fetchone()
        if case is None:
            return None
        volumes = connection.execute(
            "SELECT v.id, v.module_code, v.title, a.id AS author_id, a.name AS author_name, a.login AS author_login, a.org AS author_org "
            f"FROM case_volumes v LEFT JOIN accounts a ON a.id = v.author_id WHERE v.case_id = %s AND {where} ORDER BY v.module_code",
            (case_id, *values)).fetchall()
        if not volumes:
            return None
        current = flow.states(_stage_events(connection, case_id))
        seen = [str(v["id"]) for v in volumes]
        rows = connection.execute(
            "SELECT e.id, e.at, e.actor, e.proxy, e.volume_id, e.stage, e.action, e.note, v.module_code FROM case_events e "
            "LEFT JOIN case_volumes v ON v.id = e.volume_id WHERE e.case_id = %s AND (e.volume_id IS NULL OR e.volume_id = ANY(%s::uuid[])) "
            "ORDER BY e.seq DESC LIMIT %s", (case_id, seen, EVENT_LIMIT)).fetchall()
    manage = can_manage(account)
    volume_rows = []
    for volume in volumes:
        stage_states = _volume_states(current, str(volume["id"]))
        volume_rows.append({
            "id": str(volume["id"]), "module_code": volume["module_code"], "title": volume["title"],
            "author": {"id": str(volume["author_id"]), "name": volume["author_name"], "login": volume["author_login"], "org": volume["author_org"]}
            if volume["author_id"] else None,
            "stages": stage_states, "done": sum(s["state"] == flow.DONE for s in stage_states.values()), "total": len(stage_states)})
    events = [{"id": str(row["id"]), "at": row["at"], "actor": row["actor"], "proxy": row["proxy"],
               "volume_id": str(row["volume_id"]) if row["volume_id"] else None, "module_code": row["module_code"],
               "stage": row["stage"], "stage_name": flow.BY_KEY[row["stage"]].name if row["stage"] in flow.BY_KEY else "",
               "action": row["action"], "action_name": flow.ACTIONS.get(row["action"]) or flow.NOTES.get(row["action"], row["action"]),
               "note": row["note"]} for row in rows]
    return {**case, "id": str(case["id"]), "volumes": volume_rows,
            "case_stages": {stage.key: current.get((None, stage.key), flow.blank()) for stage in flow.CASE_STAGES},
            "progress": _progress([v["stages"] for v in volume_rows]),
            "stages": [stage.public() for stage in flow.STAGES], "basis": flow.BASIS,
            "events": events, "can_manage": manage}
