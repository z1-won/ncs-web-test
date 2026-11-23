"""세분류 건(REQ-02-007) — 건(세분류 + 사업 연도) → 권(학습모듈 한 권, 담당 집필자) → 판본 → 사건을 PostgreSQL에 둔다.

- 주문의 단위는 세분류 한 건이다. 권은 그 세분류의 학습모듈이고, 모듈 코드의 앞 8자리(LM 다음)가 세분류와 같아야 한다.
- 모든 변화는 사건(case_events)으로만 남긴다: 누가(계정), 언제, 어느 단계에 무엇을, 어떤 메모와 근거로. 지우거나 고치지 않는다.
  단계의 상태는 저장하지 않고 사건을 접어서 얻는다(flow.states). 전이와 권한은 flow가 판단한다.
- 볼 수 있는 범위: 에디터와 직능연은 전부, 집필진은 자기가 담당인 권과 그 권의 사건만(건 단위 단계는 상태만). 검토진과 위원의 화면은 아직 없다.
- 판본: 원고를 올리는 단계의 제출은 파일과 함께 한다(submit_version). 파일은 기한 없이 보관하고, 그 판본으로 돌린 원고 검수는
  review_runs.version_id로 이어진다. 검수하는 단계의 보완 요청과 완료는 그 검수 묶음을 근거로 가리키고, 검수 기록이 없으면 사유를 받는다.
- 근거 기록: 의견 반영 검토, 원고 분량, 권리 증빙 점검을 권의 단계에서 열어 돌리면 그 기록이 그 권과 단계에 붙는다(access.link).
- 원고 진행 현황(모듈 코드별 7단계)과의 관계: 권을 건에 넣을 때 이미 있던 완료 표시를 사건으로 옮겨 온다(adopt). 건에 든 원고의 단계는
  건 화면에서만 진행한다(진행 현황의 완료 표시는 막는다 — routes.progress). 단계가 두 군데에서 따로 움직이지 않게 하려는 것이다.
"""

from __future__ import annotations

import json
from uuid import uuid4

from . import flow

LEGACY_NOTE = "원고 진행 현황에서 표시"
EVENT_LIMIT = 300
MANUSCRIPT_TYPES = (".hwp", ".hwpx")
PLAN_STAGE = "plan"
MAX_VERSION_BYTES = 50 << 20
ROLE_NAMES = {"krivet": "직능연", "author": "집필진", "editor": "에디터", "reviewer": "검토진", "committee": "소위원회 위원"}     # accounts.ROLES와 같다


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


def _latest_version(connection, volume_id: str, stage: str | None = None) -> dict | None:
    """권의 가장 최근 판본(stage를 주면 그 단계에 제출한 것 중). 검수 묶음이 있으면 가장 최근 것의 id도."""
    where, values = ("AND stage = %s", (stage,)) if stage else ("", ())
    version = connection.execute(
        f"SELECT id, stage, number, sha256, filename FROM volume_versions WHERE volume_id = %s {where} ORDER BY submitted_at DESC, number DESC LIMIT 1",
        (volume_id, *values)).fetchone()
    if version is None:
        return None
    run = connection.execute("SELECT group_id, id FROM review_runs WHERE version_id = %s ORDER BY created_at DESC LIMIT 1", (version["id"],)).fetchone()
    return {**version, "id": str(version["id"]), "group": str(run["group_id"] or run["id"]) if run else None}


def _latest_case_file(connection, case_id: str, stage: str) -> dict | None:
    """건 단위 단계에 올린 가장 최근 문서. 그 문서로 돌린 점검이 있으면 가장 최근 실행의 id도."""
    row = connection.execute(
        "SELECT id, number, sha256, filename, content FROM case_files WHERE case_id = %s AND stage = %s ORDER BY number DESC LIMIT 1",
        (case_id, stage)).fetchone()
    if row is None:
        return None
    run = connection.execute("SELECT id FROM review_runs WHERE case_file_id = %s ORDER BY created_at DESC LIMIT 1", (row["id"],)).fetchone()
    return {**row, "id": str(row["id"]), "run": str(run["id"]) if run else None}


def _act(connection, case_id: str, definition: flow.Stage, action: str, account: dict, *, volume_id: str | None, note: str,
         evidence: dict | None = None, version_id: str | None = None, case_file_id: str | None = None) -> str:
    """잠근 건 안에서 전이를 검사하고 사건을 남긴다. 바뀐 뒤의 상태를 돌려준다."""
    ok, proxy = flow.allowed(definition, action, account.get("role", ""))
    if not ok:
        raise flow.Denied(f"‘{definition.name}’의 ‘{flow.ACTIONS.get(action, action)}’은 이 계정의 역할로 할 수 없습니다")
    if volume_id:
        volume = connection.execute("SELECT author_id FROM case_volumes WHERE id = %s AND case_id = %s", (volume_id, case_id)).fetchone()
        if volume is None:
            raise LookupError("권이 없습니다")
        if account.get("role") == "author" and str(volume["author_id"] or "") != str(account.get("id") or "-"):
            raise flow.Denied("담당하는 권에만 적을 수 있습니다")
    elif account.get("role") == "author" and connection.execute(
            "SELECT 1 FROM case_volumes WHERE case_id = %s AND author_id = %s", (case_id, account.get("id"))).fetchone() is None:
        raise flow.Denied("담당하는 권이 있는 건에만 적을 수 있습니다")
    now = flow.states(_stage_events(connection, case_id)).get((volume_id, definition.key), flow.blank())
    target = flow.next_state(definition, now["state"], action, note=note, before=now["before"])
    evidence = dict(evidence or {})
    if volume_id and (definition.review or definition.tools) and action in (flow.REQUEST, flow.COMPLETE):
        # 근거: 이 단계에 제출한 판본(없으면 그 권의 가장 최근 판본)의 검수 묶음과, 이 단계에 붙은 기록. 하나도 없으면 사유를 받는다 — 일관성 규칙 2
        found = False
        if definition.review:
            latest = _latest_version(connection, volume_id, definition.key if definition.manuscript else None)
            if latest and latest["group"]:
                evidence.update({"version": latest["id"], "review_group": latest["group"]})
                version_id = version_id or latest["id"]
                found = True
        if definition.tools:
            linked = _linked(connection, [volume_id]).get((volume_id, definition.key), [])
            if linked:
                evidence["records"] = [item["id"] for item in linked]
                found = True
        if not found and not note.strip():
            raise flow.FlowError(f"이 단계에 붙은 검수나 점검 기록이 없습니다. 먼저 실행하거나, 기록 없이 ‘{flow.ACTIONS[action]}’을 하는 사유를 적어 주세요")
    if not volume_id and definition.document and action in (flow.REQUEST, flow.COMPLETE):
        document = _latest_case_file(connection, case_id, definition.key)
        if document and document["run"]:
            evidence.update({"case_file": document["id"], "review_run": document["run"]})
            case_file_id = case_file_id or document["id"]
        elif not note.strip():
            raise flow.FlowError(f"올린 문서로 돌린 점검 기록이 없습니다. 점검을 먼저 실행하거나, 점검 없이 ‘{flow.ACTIONS[action]}’을 하는 사유를 적어 주세요")
    connection.execute(
        "INSERT INTO case_events (id, case_id, volume_id, stage, action, actor_id, actor, proxy, note, evidence, version_id, case_file_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
        (str(uuid4()), case_id, volume_id, definition.key, action, account.get("id"), actor_name(account), proxy, note.strip(),
         json.dumps(evidence, ensure_ascii=False), version_id, case_file_id))
    return target


def _stage(stage: str, volume_id: str | None) -> flow.Stage:
    definition = flow.BY_KEY.get(stage)
    if definition is None:
        raise flow.FlowError("없는 단계입니다")
    if (definition.unit == flow.VOLUME) != bool(volume_id):
        raise flow.FlowError(f"‘{definition.name}’은 {definition.unit} 단위 단계입니다")
    return definition


def act(dsn: str, case_id: str, *, stage: str, action: str, account: dict, volume_id: str | None = None, note: str = "",
        evidence: dict | None = None) -> str:
    """단계에 행동 하나(제출, 보완 요청, 판정 도착, 완료, 되돌림)를 적는다. 전이와 권한은 flow가 판단하고, 안 되면 FlowError(권한이면 Denied).
    원고를 올리는 단계의 제출은 submit_version으로 한다. 돌려주는 값은 바뀐 뒤의 상태."""
    definition = _stage(stage, volume_id)
    if action == flow.SUBMIT and (definition.manuscript or definition.document):
        raise flow.FlowError(f"‘{definition.name}’은 파일을 올려서 제출합니다")
    with _connect(dsn) as connection:
        if connection.execute("SELECT 1 FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone() is None:
            raise LookupError("건이 없습니다")
        return _act(connection, case_id, definition, action, account, volume_id=volume_id, note=note, evidence=evidence)


def submit_version(dsn: str, case_id: str, volume_id: str, *, stage: str, filename: str, content: bytes, account: dict, note: str = "") -> str:
    """원고 판본을 올려 제출한다 — 파일을 보관하고(volume_versions) 제출 사건에 그 판본을 붙인다. 판본 id를 돌려준다.
    같은 단계에 바로 앞서 낸 것과 같은 파일이면 받지 않는다(고친 파일을 올려야 다시 제출이 된다)."""
    definition = _stage(stage, volume_id)
    if not definition.manuscript:
        raise flow.FlowError(f"‘{definition.name}’은 원고 파일을 올리는 단계가 아닙니다")
    name, sha256 = _checked_file(filename, content)
    version_id = str(uuid4())
    with _connect(dsn) as connection:
        if connection.execute("SELECT 1 FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone() is None:
            raise LookupError("건이 없습니다")
        last = _latest_version(connection, volume_id, stage)
        if last and last["sha256"] == sha256:
            raise ValueError("바로 앞서 제출한 파일과 같은 파일입니다. 고친 파일을 올려 주세요")
        # 전이를 먼저 검사한다(권한·순서가 틀리면 파일을 남기지 않는다). 판본을 넣은 뒤 사건에 붙인다
        ok, _ = flow.allowed(definition, flow.SUBMIT, account.get("role", ""))
        if not ok:
            raise flow.Denied(f"‘{definition.name}’의 제출은 이 계정의 역할로 할 수 없습니다")
        connection.execute(
            "INSERT INTO volume_versions (id, volume_id, stage, number, sha256, filename, byte_size, content, submitted_by, submitted_name) "
            "SELECT %s, v.id, %s, %s, %s, %s, %s, %s, %s, %s FROM case_volumes v WHERE v.id = %s AND v.case_id = %s",
            (version_id, stage, (last["number"] + 1) if last else 1, sha256, name, len(content), content, account.get("id"), actor_name(account),
             volume_id, case_id))
        _act(connection, case_id, definition, flow.SUBMIT, account, volume_id=volume_id, note=note, version_id=version_id)
    return version_id


def _checked_file(filename: str, content: bytes) -> tuple[str, str]:
    """올린 파일의 이름과 sha256. 형식·크기가 맞지 않으면 ValueError."""
    import hashlib
    from pathlib import PurePath

    name = PurePath(filename or "").name
    if not name or PurePath(name).suffix.lower() not in MANUSCRIPT_TYPES:
        raise ValueError("hwp, hwpx 파일로 올려 주세요")
    if not content:
        raise ValueError("빈 파일입니다. 파일을 다시 골라 주세요")
    if len(content) > MAX_VERSION_BYTES:
        raise ValueError(f"파일이 {MAX_VERSION_BYTES >> 20}MB를 넘습니다")
    return name, hashlib.sha256(content).hexdigest()


def submit_case_file(dsn: str, case_id: str, *, stage: str, filename: str, content: bytes, account: dict, note: str = "") -> str:
    """건 단위 단계의 문서(개발계획서)를 올려 제출한다 — 파일을 보관하고(case_files) 제출 사건에 붙인다. 문서 id를 돌려준다."""
    definition = _stage(stage, None)
    if not definition.document:
        raise flow.FlowError(f"‘{definition.name}’은 문서 파일을 올리는 단계가 아닙니다")
    name, sha256 = _checked_file(filename, content)
    file_id = str(uuid4())
    with _connect(dsn) as connection:
        if connection.execute("SELECT 1 FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone() is None:
            raise LookupError("건이 없습니다")
        last = _latest_case_file(connection, case_id, stage)
        if last and last["sha256"] == sha256:
            raise ValueError("바로 앞서 제출한 파일과 같은 파일입니다. 고친 파일을 올려 주세요")
        ok, _ = flow.allowed(definition, flow.SUBMIT, account.get("role", ""))
        if not ok:
            raise flow.Denied(f"‘{definition.name}’의 제출은 이 계정의 역할로 할 수 없습니다")
        connection.execute(
            "INSERT INTO case_files (id, case_id, stage, number, sha256, filename, byte_size, content, submitted_by, submitted_name) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (file_id, case_id, stage, (last["number"] + 1) if last else 1, sha256, name, len(content), content, account.get("id"), actor_name(account)))
        _act(connection, case_id, definition, flow.SUBMIT, account, volume_id=None, note=note, case_file_id=file_id)
    return file_id


def get_case_file(dsn: str, case_id: str, file_id: str, account: dict) -> dict | None:
    """건 단위 단계의 문서 파일: {'id', 'filename', 'content'}. 에디터, 직능연과 그 건에 담당 권이 있는 집필진만."""
    if account.get("role") in flow.JUDGES:      # 검토진과 위원은 판정할 원고만 본다
        return None
    where, values = _visible(account)
    with _connect(dsn) as connection:
        if connection.execute(f"SELECT 1 FROM case_volumes v WHERE v.case_id = %s AND {where} LIMIT 1", (case_id, *values)).fetchone() is None:
            return None
        row = connection.execute("SELECT id, filename, content FROM case_files WHERE id = %s AND case_id = %s", (file_id, case_id)).fetchone()
    return {**row, "id": str(row["id"]), "content": bytes(row["content"])} if row else None


def plan_file(dsn: str, case_id: str) -> tuple[str, bytes] | None:
    """그 건의 가장 최근 개발계획서(파일 이름, 내용). 권의 원고 검수에서 위치 검수를 함께 돌리는 데 쓴다."""
    with _connect(dsn) as connection:
        found = _latest_case_file(connection, case_id, PLAN_STAGE)
    return (found["filename"], bytes(found["content"])) if found else None


def tag_review_case_file(dsn: str, run_id: str, file_id: str) -> None:
    """개발계획서 점검 실행이 어느 문서의 것인지 적는다(review_runs.case_file_id)."""
    with _connect(dsn) as connection:
        connection.execute("UPDATE review_runs SET case_file_id = %s WHERE id = %s", (file_id, run_id))


def get_version(dsn: str, case_id: str, version_id: str, account: dict) -> dict | None:
    """판본 파일: {'id', 'volume_id', 'module_code', 'filename', 'content'}. 볼 수 없는 권의 것이면 None."""
    where, values = _visible(account)
    if account.get("role") in flow.JUDGES:      # 판정 역할은 판정할 판본만 — 건을 읽어 보이는 판본인지 가린다
        case = get_case(dsn, case_id, account)
        if case is None or version_id not in {version["id"] for volume in case["volumes"] for version in volume["versions"]}:
            return None
        where, values = "true", ()
    with _connect(dsn) as connection:
        row = connection.execute(
            "SELECT x.id, x.filename, x.content, v.id AS volume_id, v.module_code FROM volume_versions x JOIN case_volumes v ON v.id = x.volume_id "
            f"WHERE x.id = %s AND v.case_id = %s AND {where}", (version_id, case_id, *values)).fetchone()
    return {**row, "id": str(row["id"]), "volume_id": str(row["volume_id"]), "content": bytes(row["content"])} if row else None


def tag_review_version(dsn: str, run_id: str, version_id: str) -> None:
    """원고 검수 실행이 어느 판본의 것인지 적는다(review_runs.version_id)."""
    with _connect(dsn) as connection:
        connection.execute("UPDATE review_runs SET version_id = %s WHERE id = %s", (version_id, run_id))


def volume_of(dsn: str, module_code: str) -> dict | None:
    """이 모듈 코드가 든 건과 권(가장 최근 연도의 건). 없으면 None — 원고 진행 현황이 '건에서 진행하는 원고'인지 가리는 데 쓴다."""
    with _connect(dsn) as connection:
        row = connection.execute(
            "SELECT v.id AS volume_id, c.id AS case_id, c.name, c.subclass, c.year FROM case_volumes v JOIN cases c ON c.id = v.case_id "
            "WHERE v.module_code = %s ORDER BY c.year DESC LIMIT 1", (module_code,)).fetchone()
    return {"case_id": str(row["case_id"]), "volume_id": str(row["volume_id"]), "name": row["name"] or row["subclass"], "year": row["year"]} if row else None


def _linked(connection, volume_ids: list[str]) -> dict[tuple[str, str], list[dict]]:
    """권과 단계에 붙은 기록(의견 반영 검토, 권리 증빙 점검, 분량 산정) — {(권 id, 단계 key): [{'tool', 'id', 'at', 'text'}]} 최근 것부터."""
    out: dict[tuple[str, str], list[dict]] = {}
    records = connection.execute(
        "SELECT id, kind, created_at, counts, case_volume_id, case_stage FROM work_records WHERE case_volume_id = ANY(%s::uuid[])", (volume_ids,)).fetchall()
    for row in records:
        counts = row["counts"] or {}
        if row["kind"] == "opinion":
            total = counts.get("전체") or {}
            text = f"의견 {total.get('총 의견', 0)}개 중 반영 후보 {total.get('반영 후보', 0)}, 미반영 후보 {total.get('미반영 후보', 0)}, 확인 필요 {total.get('확인 필요', 0)}"
        else:
            text = f"판정 {counts.get('판정') or '-'}, 원고 그림 {counts.get('원고 그림') or 0}개, 누락 {counts.get('누락') or 0}개"
        out.setdefault((str(row["case_volume_id"]), row["case_stage"]), []).append(
            {"tool": row["kind"], "id": str(row["id"]), "at": row["created_at"], "text": text})
    runs = connection.execute(
        "SELECT id, created_at, pages, case_volume_id, case_stage FROM volume_runs WHERE case_volume_id = ANY(%s::uuid[])", (volume_ids,)).fetchall()
    for row in runs:
        out.setdefault((str(row["case_volume_id"]), row["case_stage"]), []).append(
            {"tool": "volume", "id": str(row["id"]), "at": row["created_at"], "text": f"분량 {row['pages']}매"})
    for rows in out.values():
        rows.sort(key=lambda item: item["at"], reverse=True)
    return out


def _visible(account: dict) -> tuple[str, tuple]:
    """권을 거르는 SQL 조건과 값. 에디터·직능연은 전부, 집필진은 담당 권만, 그 밖의 역할은 아직 아무것도 보지 않는다."""
    if can_manage(account):
        return "true", ()
    if account.get("role") == "author" and account.get("id"):
        return "v.author_id = %s", (account["id"],)
    if account.get("role") in flow.JUDGES:      # 검토진, 위원: SQL로는 전부 읽고 get_case가 판정할 것만 남긴다(_judge_view)
        return "true", ()
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
    if account.get("role") in flow.JUDGES:      # 판정할 것이 있는 건만
        out = [case for case in out if get_case(dsn, case["id"], account) is not None]
    return out


def _versions(connection, volume_ids: list[str]) -> dict[str, list[dict]]:
    """권 id → 판본 목록(최근 것부터). 판본마다 가장 최근 검수 묶음의 판정을 붙인다."""
    from ..postgres import group_verdict

    rows = connection.execute(
        "SELECT id, volume_id, stage, number, filename, byte_size, submitted_name, submitted_at FROM volume_versions "
        "WHERE volume_id = ANY(%s::uuid[]) ORDER BY submitted_at DESC, number DESC", (volume_ids,)).fetchall()
    runs = connection.execute(
        "SELECT version_id, COALESCE(group_id, id) AS grp, check_name, verdict, created_at FROM review_runs "
        "WHERE version_id = ANY(%s::uuid[]) ORDER BY created_at", ([row["id"] for row in rows],)).fetchall() if rows else []
    by_version: dict[str, dict[str, list[dict]]] = {}
    for run in runs:
        by_version.setdefault(str(run["version_id"]), {}).setdefault(str(run["grp"]), []).append(run)
    out: dict[str, list[dict]] = {}
    for row in rows:
        groups = by_version.get(str(row["id"]), {})
        review = None
        if groups:
            group_id, checks = max(groups.items(), key=lambda item: item[1][-1]["created_at"])
            verdicts = [check["verdict"] for check in checks]
            review = {"group": group_id, "at": checks[-1]["created_at"], "verdict": group_verdict(verdicts), "checks": len(checks),
                      "counts": {verdict: verdicts.count(verdict) for verdict in dict.fromkeys(verdicts)}}
        out.setdefault(str(row["volume_id"]), []).append({
            "id": str(row["id"]), "stage": row["stage"], "stage_name": flow.BY_KEY[row["stage"]].name if row["stage"] in flow.BY_KEY else row["stage"],
            "number": row["number"], "filename": row["filename"], "byte_size": row["byte_size"], "by": row["submitted_name"],
            "at": row["submitted_at"], "review": review})
    return out


def _case_files(connection, case_id: str) -> dict[str, list[dict]]:
    """건 단위 단계에 올린 문서 — {단계 key: [문서(최근 것부터)]}. 문서마다 가장 최근 점검 실행의 판정을 붙인다."""
    rows = connection.execute(
        "SELECT f.id, f.stage, f.number, f.filename, f.byte_size, f.submitted_name, f.submitted_at, r.id AS run_id, r.verdict, r.created_at AS run_at "
        "FROM case_files f LEFT JOIN LATERAL (SELECT id, verdict, created_at FROM review_runs WHERE case_file_id = f.id ORDER BY created_at DESC LIMIT 1) r ON true "
        "WHERE f.case_id = %s ORDER BY f.number DESC", (case_id,)).fetchall()
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["stage"], []).append({
            "id": str(row["id"]), "number": row["number"], "filename": row["filename"], "byte_size": row["byte_size"], "by": row["submitted_name"],
            "at": row["submitted_at"], "review": {"run": str(row["run_id"]), "verdict": row["verdict"], "at": row["run_at"]} if row["run_id"] else None})
    return out


def _judge_view(role: str, volumes: list[dict], events: list[dict]) -> tuple[list[dict], list[dict]]:
    """검토진·위원에게 보일 것만 남긴다: 자기 판정 단계가 제출됨·판정 도착인 권, 판정할 원고(그 앞 단계의 가장 최근 판본), 그 판정 단계의 기록.
    붙은 기록과 다른 단계의 판본은 싣지 않는다 — 위원은 심의본만 본다."""
    stages = flow.JUDGES[role]
    kept = []
    for volume in volumes:
        standing = volume["current"]
        if standing is None or standing["key"] not in stages or standing["state"] not in (flow.SUBMITTED, flow.VERDICT):
            continue
        source = stages[standing["key"]]
        kept.append({**volume, "versions": [v for v in volume["versions"] if v["stage"] == source][:1], "records": {}, "reopen": []})
    ids = {volume["id"] for volume in kept}
    return kept, [e for e in events if e["stage"] in stages and (e["volume_id"] is None or e["volume_id"] in ids)]


def _standing(stage: flow.Stage | None, state: dict, role: str) -> dict | None:
    """지금 서 있는 단계와 이 계정이 거기서 할 수 있는 일."""
    if stage is None:
        return None
    return {"key": stage.key, "name": stage.name, "unit": stage.unit, "kind": stage.kind, "state": state["state"], "at": state["at"], "by": state["by"],
            "note": state["note"], "turn": [ROLE_NAMES.get(r, r) for r in flow.turn(stage, state["state"])],
            "turn_roles": list(flow.turn(stage, state["state"])),
            "manuscript": stage.manuscript, "review": stage.review, "tools": list(stage.tools), "document": stage.document, "actions": flow.available(stage, state["state"], role)}


def get_case(dsn: str, case_id: str, account: dict) -> dict | None:
    """건 하나: 권(담당 집필자, 단계별 상태, 지금 서 있는 단계와 할 수 있는 일, 판본), 건 단위 단계, 사건 기록(최근순), 단계 정의표.
    볼 수 있는 권이 없으면 None."""
    where, values = _visible(account)
    role = account.get("role", "")
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
        versions = _versions(connection, seen)
        linked = _linked(connection, seen)
        documents = _case_files(connection, case_id)
        rows = connection.execute(
            "SELECT e.id, e.at, e.actor, e.proxy, e.volume_id, e.stage, e.action, e.note, e.version_id, v.module_code FROM case_events e "
            "LEFT JOIN case_volumes v ON v.id = e.volume_id WHERE e.case_id = %s AND (e.volume_id IS NULL OR e.volume_id = ANY(%s::uuid[])) "
            "ORDER BY e.seq DESC LIMIT %s", (case_id, seen, EVENT_LIMIT)).fetchall()
    case_states = {stage.key: current.get((None, stage.key), flow.blank()) for stage in flow.CASE_STAGES}
    volume_rows = []
    for volume in volumes:
        stage_states = _volume_states(current, str(volume["id"]))
        every = {**case_states, **stage_states}
        standing = flow.current(every)
        mine = versions.get(str(volume["id"]), [])
        for key, state in stage_states.items():     # 완료한 뒤에 그 단계의 판본·검수·붙은 기록이 새로 생겼는가 — 일관성 규칙 4
            if state["state"] == flow.DONE and state["at"]:
                later = [v["at"] for v in mine if v["stage"] == key] + [v["review"]["at"] for v in mine if v["stage"] == key and v["review"]]
                later += [item["at"] for item in linked.get((str(volume["id"]), key), [])]
                stage_states[key] = {**state, "changed": any(at > state["at"] for at in later)}
        volume_rows.append({
            "id": str(volume["id"]), "module_code": volume["module_code"], "title": volume["title"],
            "author": {"id": str(volume["author_id"]), "name": volume["author_name"], "login": volume["author_login"], "org": volume["author_org"]}
            if volume["author_id"] else None,
            "stages": stage_states, "done": sum(s["state"] == flow.DONE for s in stage_states.values()), "total": len(stage_states),
            "current": _standing(standing, every[standing.key], role) if standing else None,
            "reopen": [key for key, state in stage_states.items() if flow.reopenable(flow.BY_KEY[key], state["state"], role)],
            "versions": versions.get(str(volume["id"]), []),
            "records": {stage.key: linked.get((str(volume["id"]), stage.key), []) for stage in flow.VOLUME_STAGES if stage.tools}})
    events = [{"id": str(row["id"]), "at": row["at"], "actor": row["actor"], "proxy": row["proxy"],
               "volume_id": str(row["volume_id"]) if row["volume_id"] else None, "module_code": row["module_code"],
               "stage": row["stage"], "stage_name": flow.BY_KEY[row["stage"]].name if row["stage"] in flow.BY_KEY else "",
               "action": row["action"], "action_name": flow.ACTIONS.get(row["action"]) or flow.NOTES.get(row["action"], row["action"]),
               "note": row["note"], "version_id": str(row["version_id"]) if row["version_id"] else None} for row in rows]
    case_standing = flow.current(case_states)
    if role in flow.JUDGES:
        volume_rows, events = _judge_view(role, volume_rows, events)
        documents = {}
        if not volume_rows:
            return None
    return {**case, "id": str(case["id"]), "volumes": volume_rows, "case_files": documents,
            "case_stages": case_states,
            "case_actions": {stage.key: _standing(stage, case_states[stage.key], role) for stage in flow.CASE_STAGES},
            "case_reopen": [stage.key for stage in flow.CASE_STAGES if flow.reopenable(stage, case_states[stage.key]["state"], role)],
            "case_current": case_standing.key if case_standing else None,
            "progress": _progress([v["stages"] for v in volume_rows]),
            "stages": [stage.public() for stage in flow.STAGES], "basis": flow.BASIS,
            "events": events, "can_manage": can_manage(account), "role": role}


TODO_TEXT = {flow.SUBMIT: "제출해 주세요", flow.REQUEST: "제출된 것을 확인해 주세요", flow.JUDGE: "판정 결과를 적어 주세요", flow.COMPLETE: "확인하고 완료로 표시해 주세요"}


def todo(dsn: str, account: dict) -> list[dict]:
    """내 할 일: 볼 수 있는 권마다 지금 서 있는 단계가 이 계정의 차례인 것. 건 단위 단계는 건마다 한 번만.
    에디터에게는 화면이 없는 기관(직능연, 검토진, 위원)의 차례도 '대신 기록'으로 함께 보인다. 집필진의 차례는 집필진에게만 보인다."""
    role = account.get("role", "")
    out = []
    for listed in list_cases(dsn, account):
        case = get_case(dsn, listed["id"], account)
        if case is None:
            continue
        done_case_stage = set()
        for volume in case["volumes"]:
            standing = volume["current"]
            if standing is None:
                continue
            # 사유가 있어야 하는 완료와, 이미 제출한 것을 다시 내는 일은 '할 일'이 아니다
            plain = [a for a in standing["actions"]
                     if not a["needs_note"] and not (a["action"] == flow.SUBMIT and standing["state"] == flow.SUBMITTED)]
            mine = [a for a in plain if not a["proxy"]]
            proxied = [a for a in plain if a["proxy"]] if "author" not in standing["turn_roles"] else []
            actions = mine or proxied
            if not actions:
                continue
            is_case = standing["unit"] == flow.CASE
            if is_case:
                if standing["key"] in done_case_stage:
                    continue
                done_case_stage.add(standing["key"])
            first = actions[0]["action"]
            text = "원고를 올려 제출해 주세요" if first == flow.SUBMIT and standing["manuscript"] else TODO_TEXT[first]
            if standing["state"] == flow.REQUESTED:
                text = "보완 요청을 받았습니다. 고친 원고를 다시 제출해 주세요" if standing["manuscript"] else "보완 요청을 받았습니다. 다시 제출해 주세요"
            out.append({"case_id": case["id"], "case_name": case["name"] or case["subclass"], "year": case["year"],
                        "volume_id": None if is_case else volume["id"], "module_code": None if is_case else volume["module_code"],
                        "title": "건 전체" if is_case else (volume["title"] or volume["module_code"]),
                        "stage": standing["key"], "stage_name": standing["name"], "state": standing["state"], "since": standing["at"],
                        "note": standing["note"] if standing["state"] == flow.REQUESTED else "", "proxy": not mine, "todo": text,
                        "turn": standing["turn"]})
    out.sort(key=lambda item: (item["proxy"], str(item["since"] or "")))
    return out
