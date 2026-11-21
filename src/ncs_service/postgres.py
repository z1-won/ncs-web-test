"""PostgreSQL 이력 저장소 — 검수 이력(review_*)과 원고 분량 산정 이력(volume_runs). 검수 엔진과 웹 프레임워크에 의존하지 않는다."""

from __future__ import annotations

import copy
import hashlib
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ncs_core.module_code import CODE_IN_NAME

from .migrations import MIGRATIONS
from .models import ExecutedReview
from .registry import get_engine

def migrate(dsn: str) -> list[str]:
    """아직 적용되지 않은 MIGRATIONS를 순서대로 실행하고 schema_version에 기록한다. 적용한 이름 목록을 돌려준다."""
    applied = []
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {row[0] for row in connection.execute("SELECT name FROM schema_version").fetchall()}
        for name, sql in MIGRATIONS:
            if name in done:
                continue
            connection.execute(sql)
            connection.execute("INSERT INTO schema_version (name) VALUES (%s)", (name,))
            applied.append(name)
    return applied


def reporting_for(check: str):
    """해당 엔진의 reporting 모듈(REPORT_NAME, ITEM_FILES, summary, save_results)."""
    return import_module(get_engine(check).package + ".reporting")


def summary_for(review: ExecutedReview) -> dict:
    return reporting_for(review.check).summary(review.result)


def input_metadata(diagnostics: dict, uploads: list[tuple[str, Path]], *, keep_manuscript: bool = True) -> list[dict]:
    """진단의 역할별 임시 경로를 업로드 파일명·해시와 연결한다. keep_manuscript면 원고 hwpx 내용(content)도 싣는다(보관용)."""
    by_path = {str(path): (filename, path) for filename, path in uploads}
    result = []
    for role, path_string in diagnostics.get("inputs", {}).items():
        if not path_string or path_string not in by_path:
            continue
        filename, path = by_path[path_string]
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        item = {"role": role, "filename": filename, "sha256": digest.hexdigest(), "byte_size": path.stat().st_size}
        if keep_manuscript and role == "manuscript" and filename.lower().endswith(".hwpx"):
            item["content"] = path.read_bytes()
        result.append(item)
    return result


def save_review(dsn: str, review: ExecutedReview, inputs: list[dict], group_id: str | None = None,
                *, source: str = "web") -> tuple[str, dict]:
    """한 건을 저장하고 (run_id, 요약)을 돌려준다. group_id는 전체 실행 묶음(uuid 문자열) — 단독 실행이면 None.

    source는 실행 출처('web' 화면·API, 'cli' 검수 명령). 허용값은 DB 제약(마이그레이션 005)이 검사한다.
    """
    summary = summary_for(review)
    run_id = str(uuid4())
    if group_id is not None:
        UUID(group_id)  # 형식이 틀리면 ValueError
    diagnostics = copy.deepcopy(review.result.diagnostics)
    # 요청이 끝나면 사라지는 임시 경로 대신 지속되는 입력 이름을 기록한다.
    names = {item["role"]: item["filename"] for item in inputs}
    diagnostics["inputs"] = {role: names.get(role) for role in diagnostics.get("inputs", {})}
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO review_runs (id, check_name, module_code, verdict, engine_version, group_id, source) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (run_id, review.check, review.result.module_code, summary["검수결과"], version("ncs-f02-review"), group_id,
             source),
        )
        connection.execute(
            "INSERT INTO review_results (run_id, summary, sheet, diagnostics, findings, checklist) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (run_id, Jsonb(summary), Jsonb(review.result.sheet), Jsonb(diagnostics),
             Jsonb(review.result.findings), Jsonb(review.result.checklist)),
        )
        for item in inputs:
            connection.execute(
                "INSERT INTO review_inputs (run_id, role, filename, sha256, byte_size) "
                "VALUES (%s, %s, %s, %s, %s)",
                (run_id, item["role"], item["filename"], item.get("sha256"), item.get("byte_size")),
            )
            # 원고 hwpx는 내용도 보관한다(메모 달기용). 같은 파일(sha256)은 한 번만.
            if item["role"] == "manuscript" and item.get("content") is not None and item["filename"].lower().endswith(".hwpx"):
                connection.execute(
                    "INSERT INTO review_files (sha256, filename, content, byte_size) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (sha256) DO NOTHING",
                    (item["sha256"], item["filename"], item["content"], item["byte_size"]),
                )
    return run_id, summary


def get_manuscript(dsn: str, run_id: str) -> tuple[str, bytes] | None:
    """실행에 보관된 원고 hwpx → (파일 이름, 바이트). 없으면 None."""
    try:
        UUID(run_id)
    except ValueError:
        return None
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT i.filename, f.content FROM review_inputs i JOIN review_files f ON f.sha256 = i.sha256 "
            "WHERE i.run_id = %s AND i.role = 'manuscript'",
            (run_id,),
        ).fetchone()
    return (row["filename"], bytes(row["content"])) if row else None


def _sweep_files(connection) -> int:
    """어느 실행에서도 참조하지 않는 보관 파일을 지운다(실행 삭제 뒤에 부른다)."""
    return connection.execute(
        "DELETE FROM review_files f WHERE NOT EXISTS (SELECT 1 FROM review_inputs i WHERE i.sha256 = f.sha256)"
    ).rowcount


def list_reviews(dsn: str, *, module_code: str | None = None, check: str | None = None,
                 verdict: str | None = None, standalone: bool = False, limit: int = 50, offset: int = 0, visible=None) -> list[dict]:
    """실행 목록(최신순). standalone=True면 전체 실행 묶음에 속하지 않은 단독 실행만. visible = access.Scope(볼 수 있는 범위) 또는 None(전부)."""
    clauses = []
    values: list = []
    if visible is not None:
        sql, extra = visible.clause()
        clauses.append(sql)
        values.extend(extra)
    for column, value in (("module_code", module_code), ("check_name", check), ("verdict", verdict)):
        if value:
            clauses.append(f"{column} = %s")
            values.append(value)
    if standalone:
        clauses.append("group_id IS NULL")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT id, created_at, check_name, module_code, verdict, engine_version, source, group_id "
            "FROM review_runs" + where + " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            (*values, limit, offset),
        ).fetchall()
    return [{**row, "id": str(row["id"]), "created_at": row["created_at"].isoformat(),
             "group_id": str(row["group_id"]) if row["group_id"] else None} for row in rows]


# 묶음 판정: 구성요소 하나라도 부적합이면 부적합, 아니면 판단불가가 있으면 판단불가, 모두 적합이면 적합.
VERDICT_ORDER = ("부적합", "판단불가", "적합", "미검사")


def group_verdict(verdicts: list[str]) -> str:
    for candidate in VERDICT_ORDER:
        if candidate in verdicts:
            return candidate
    return verdicts[0] if verdicts else "미검사"


def list_groups(dsn: str, *, module_code: str | None = None, limit: int = 50, offset: int = 0, visible=None) -> list[dict]:
    """전체 실행 묶음 목록(최신순). 한 묶음 = 한 행: 시작 시각, 모듈, 들어 있는 검수 이름·판정, 묶음 판정."""
    where = " AND module_code = %s" if module_code else ""
    values: list = [module_code] if module_code else []
    if visible is not None:
        sql, extra = visible.clause()
        where += " AND " + sql
        values.extend(extra)
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT group_id, min(created_at) AS created_at, module_code, "
            "array_agg(check_name ORDER BY created_at, id) AS checks, array_agg(verdict ORDER BY created_at, id) AS verdicts "
            "FROM review_runs WHERE group_id IS NOT NULL" + where +
            " GROUP BY group_id, module_code ORDER BY min(created_at) DESC LIMIT %s OFFSET %s",
            (*values, limit, offset),
        ).fetchall()
    return [{"group_id": str(row["group_id"]), "created_at": row["created_at"].isoformat(), "module_code": row["module_code"],
             "checks": list(row["checks"]), "verdicts": list(row["verdicts"]), "verdict": group_verdict(list(row["verdicts"]))}
            for row in rows]


def get_group(dsn: str, group_id: str) -> dict | None:
    """묶음 한 건: 실행 순서대로 각 검수의 전체 결과(get_review와 같은 모양) 목록."""
    try:
        UUID(group_id)
    except ValueError:
        return None
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT id FROM review_runs WHERE group_id = %s ORDER BY created_at, id", (group_id,)
        ).fetchall()
    if not rows:
        return None
    runs = [found for found in (get_review(dsn, str(row["id"])) for row in rows) if found]
    return {"group_id": group_id, "created_at": runs[0]["created_at"], "module_code": runs[0]["module_code"],
            "verdict": group_verdict([run["verdict"] for run in runs]), "runs": runs}


def delete_group(dsn: str, group_id: str) -> bool:
    try:
        UUID(group_id)
    except ValueError:
        return False
    with psycopg.connect(dsn) as connection:
        deleted = connection.execute("DELETE FROM review_runs WHERE group_id = %s", (group_id,)).rowcount
        if deleted:
            _sweep_files(connection)
    return deleted > 0


def get_review(dsn: str, run_id: str) -> dict | None:
    try:
        UUID(run_id)
    except ValueError:
        return None
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT r.id, r.created_at, r.check_name, r.module_code, r.verdict, r.engine_version, r.source, "
            "d.summary, d.sheet, d.diagnostics, d.findings, d.checklist "
            "FROM review_runs r JOIN review_results d ON d.run_id = r.id WHERE r.id = %s",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        inputs = connection.execute(
            "SELECT role, filename, sha256, byte_size FROM review_inputs WHERE run_id = %s ORDER BY role",
            (run_id,),
        ).fetchall()
    return {"id": str(row["id"]), "created_at": row["created_at"].isoformat(),
            "check": row["check_name"], "module_code": row["module_code"], "verdict": row["verdict"],
            "engine_version": row["engine_version"], "source": row["source"], "inputs": inputs,
            "요약": row["summary"], "검수확인서": row["sheet"], "진단": row["diagnostics"],
            "지적사항": row["findings"], "전체": row["checklist"]}


def delete_review(dsn: str, run_id: str) -> bool:
    """이력 한 건을 지운다. review_results·review_inputs는 ON DELETE CASCADE로 함께 지워진다.

    지웠으면 True, 없는 id(또는 UUID 형식이 아닌 값)면 False.
    """
    try:
        UUID(run_id)
    except ValueError:
        return False
    with psycopg.connect(dsn) as connection:
        deleted = connection.execute("DELETE FROM review_runs WHERE id = %s", (run_id,)).rowcount
        if deleted:
            _sweep_files(connection)
    return deleted > 0


def import_review(dsn: str, *, run_id: str, created_at, check: str, module_code: str,
                  summary: dict, sheet: list, diagnostics: dict, findings: list, checklist: list) -> bool:
    with psycopg.connect(dsn) as connection:
        if connection.execute("SELECT 1 FROM review_runs WHERE id = %s", (run_id,)).fetchone():
            return False
        connection.execute(
            "INSERT INTO review_runs (id, created_at, check_name, module_code, verdict, source) "
            "VALUES (%s, %s, %s, %s, %s, 'import')",
            (run_id, created_at, check, module_code, summary["검수결과"]),
        )
        connection.execute(
            "INSERT INTO review_results (run_id, summary, sheet, diagnostics, findings, checklist) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (run_id, Jsonb(summary), Jsonb(sheet), Jsonb(diagnostics), Jsonb(findings), Jsonb(checklist)),
        )
        for role, filename in diagnostics.get("inputs", {}).items():
            if filename:
                connection.execute(
                    "INSERT INTO review_inputs (run_id, role, filename) VALUES (%s, %s, %s)",
                    (run_id, role, filename),
                )
    return True


# ── 원고 분량 산정 이력(volume_runs) ── 산정표(ncs_volume.measure의 결과 dict)를 그대로 보관한다. 원고 파일은 보관하지 않는다.
def file_metadata(files: list[tuple[str, str, Path]]) -> list[dict]:
    """[(역할, 올린 파일 이름, 임시 경로)] → [{role, filename, sha256, byte_size}]. 요청이 끝나면 사라지는 경로 대신 남길 값."""
    result = []
    for role, filename, path in files:
        digest = hashlib.sha256()
        with Path(path).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        result.append({"role": role, "filename": filename, "sha256": digest.hexdigest(), "byte_size": Path(path).stat().st_size})
    return result


def save_volume(dsn: str, result: dict, inputs: list[dict], params: dict, *, source: str = "web") -> str:
    """산정 한 건을 저장하고 id를 돌려준다. inputs는 file_metadata()의 값(역할 manuscript가 있어야 한다),
    params는 산정에 넣은 값(단가·계약 분량·수작업 쪽수·부록 포함 여부). 모듈 코드는 원고 파일 이름에서 읽고 없으면 빈 값."""
    manuscript = next(item for item in inputs if item["role"] == "manuscript")
    codes = list(dict.fromkeys(CODE_IN_NAME.findall(manuscript["filename"])))
    fee = result["집필료"]
    run_id = str(uuid4())
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO volume_runs (id, module_code, manuscript, sha256, byte_size, pages, unit_price, fee, estimated, "
            "params, inputs, result, engine_version, source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (run_id, codes[0] if len(codes) == 1 else "", manuscript["filename"], manuscript["sha256"], manuscript["byte_size"],
             fee["산정 분량"], fee["단가"], fee["집필료"], bool(fee["추정"]), Jsonb(params), Jsonb(inputs), Jsonb(result),
             version("ncs-f02-review"), source),
        )
    return run_id


def list_volumes(dsn: str, *, module_code: str | None = None, limit: int = 50, offset: int = 0, visible=None) -> list[dict]:
    """산정 이력 목록(최신순). 산정표 전체는 싣지 않는다 — 한 건은 get_volume."""
    where = " WHERE module_code = %s" if module_code else ""
    values: list = [module_code] if module_code else []
    if visible is not None:
        sql, extra = visible.clause()
        where += (" AND " if where else " WHERE ") + sql
        values.extend(extra)
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT id, created_at, module_code, manuscript, sha256, pages, unit_price, fee, estimated, "
            "(params->>'unit_price') IS NOT NULL AS unit_given, source "
            "FROM volume_runs" + where + " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            (*values, limit, offset),
        ).fetchall()
    return [{**row, "id": str(row["id"]), "created_at": row["created_at"].isoformat()} for row in rows]


def get_volume(dsn: str, run_id: str) -> dict | None:
    """산정 한 건: 저장한 산정표에 id·created_at·입력 파일·넣은 값을 붙여 돌려준다(화면이 방금 산정한 결과와 같은 모양으로 그린다)."""
    try:
        UUID(run_id)
    except ValueError:
        return None
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT id, created_at, params, inputs, result, source FROM volume_runs WHERE id = %s", (run_id,)
        ).fetchone()
    if row is None:
        return None
    return {**row["result"], "id": str(row["id"]), "created_at": row["created_at"].isoformat(),
            "입력": {"파일": row["inputs"], "값": row["params"]}, "source": row["source"]}


def delete_volume(dsn: str, run_id: str) -> bool:
    try:
        UUID(run_id)
    except ValueError:
        return False
    with psycopg.connect(dsn) as connection:
        return connection.execute("DELETE FROM volume_runs WHERE id = %s", (run_id,)).rowcount > 0


# --- 원고 진행 현황(REQ-02-007) -------------------------------------------------------

def save_work_record(dsn: str, kind: str, manuscript: str, counts: dict, files: list[dict], *, module_code: str = "",
                     source: str = "web") -> dict:
    """의견 반영 검토·권리 증빙 점검의 개수 기록 한 건을 남긴다. 모듈 코드는 준 값, 없으면 원고 파일 이름에서 읽고 그것도 없으면 빈 값
    (빈 값이면 어느 원고의 진행 현황에도 붙지 않는다). 돌려주는 값: {'id', 'module_code'}."""
    from .progress import KINDS

    if kind not in KINDS:
        raise ValueError(f"모르는 기록 종류: {kind}")
    given = CODE_IN_NAME.findall(module_code.strip())
    found = given if given == [module_code.strip()] else list(dict.fromkeys(CODE_IN_NAME.findall(manuscript)))
    code = found[0] if len(found) == 1 else ""
    record_id = str(uuid4())
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO work_records (id, kind, module_code, manuscript, counts, files, source) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (record_id, kind, code, manuscript, Jsonb(counts), Jsonb(files), source),
        )
    return {"id": record_id, "module_code": code}


def list_manuscripts(dsn: str, *, limit: int = 50, offset: int = 0, codes: list[str] | None = None) -> list[dict]:
    """기록이 있는 원고(모듈 코드) 목록 — 최근 기록순. 한 줄: 모듈 코드, 처음·최근 기록 시각, 기록 수, 기록 종류.
    codes를 주면 그 모듈 코드만(집필진은 담당 권만 본다)."""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT module_code, min(created_at) AS first_at, max(created_at) AS last_at, "
            "count(*) FILTER (WHERE counted) AS records, array_agg(DISTINCT kind) AS kinds FROM ("
            " SELECT module_code, created_at, CASE WHEN check_name = 'plan' THEN 'plan' ELSE 'review' END AS kind, true AS counted FROM review_runs"
            " UNION ALL SELECT module_code, created_at, 'group', false FROM review_runs WHERE group_id IS NOT NULL AND check_name <> 'plan'"
            " UNION ALL SELECT module_code, done_at, 'done:' || stage, false FROM manuscript_stages"
            " UNION ALL SELECT module_code, created_at, 'volume', true FROM volume_runs"
            " UNION ALL SELECT module_code, created_at, 'rights', true FROM work_records WHERE kind = 'rights'"
            " UNION ALL SELECT module_code, created_at, 'opinion', true FROM work_records WHERE kind = 'opinion'"
            " UNION ALL SELECT w.module_code, w.created_at, 'opinion:' || k.name, false FROM work_records w,"
            "  jsonb_object_keys(CASE WHEN jsonb_typeof(w.counts->'차수별') = 'object' THEN w.counts->'차수별' ELSE '{}'::jsonb END) AS k(name)"
            "  WHERE w.kind = 'opinion'"
            ") t WHERE module_code <> '' AND (%s::text[] IS NULL OR module_code = ANY(%s::text[])) "
            "GROUP BY module_code ORDER BY max(created_at) DESC, module_code LIMIT %s OFFSET %s",
            (codes, codes, limit, offset),
        ).fetchall()
    return [{"module_code": row["module_code"], "first_at": row["first_at"].isoformat(), "last_at": row["last_at"].isoformat(),
             "records": row["records"], "kinds": sorted(row["kinds"])} for row in rows]


def progress_sources(dsn: str, module_code: str) -> dict | None:
    """한 원고(모듈 코드)의 기록을 진행 현황(ncs_service.progress.build)의 재료로 모은다. 기록이 하나도 없으면 None."""
    def iso(value):
        return value.isoformat() if value is not None else None

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        totals = connection.execute(
            "SELECT check_name = 'plan' AS is_plan, count(*) AS n, min(created_at) AS first_at, max(created_at) AS last_at "
            "FROM review_runs WHERE module_code = %s GROUP BY 1", (module_code,)).fetchall()
        staged = connection.execute(
            "SELECT work_stage, count(*) AS n, max(created_at) AS last_at, "
            "(array_agg(verdict ORDER BY created_at DESC, id DESC))[1] AS verdict FROM review_runs "
            "WHERE module_code = %s AND work_stage IS NOT NULL AND check_name <> 'plan' GROUP BY work_stage", (module_code,)).fetchall()
        done = connection.execute(
            "SELECT stage, done_by, done_at, note FROM manuscript_stages WHERE module_code = %s", (module_code,)).fetchall()
        history = connection.execute(
            "SELECT stage, action, changed_by, changed_at, note FROM manuscript_stage_history WHERE module_code = %s "
            "ORDER BY changed_at DESC, id DESC LIMIT 50", (module_code,)).fetchall()
        latest = connection.execute(
            "SELECT DISTINCT ON (r.check_name) r.id, r.check_name, r.created_at, r.verdict, d.sheet "
            "FROM review_runs r LEFT JOIN review_results d ON d.run_id = r.id WHERE r.module_code = %s "
            "ORDER BY r.check_name, r.created_at DESC, r.id DESC", (module_code,)).fetchall()
        group = connection.execute(
            "SELECT group_id, min(created_at) AS created_at, array_agg(check_name ORDER BY created_at, id) AS checks, "
            "array_agg(verdict ORDER BY created_at, id) AS verdicts FROM review_runs "
            "WHERE module_code = %s AND group_id IS NOT NULL AND check_name <> 'plan' "
            "GROUP BY group_id ORDER BY min(created_at) DESC LIMIT 1", (module_code,)).fetchone()
        volume = connection.execute(
            "SELECT id, created_at, manuscript, pages, unit_price, fee, estimated, count(*) OVER () AS total "
            "FROM volume_runs WHERE module_code = %s ORDER BY created_at DESC, id DESC LIMIT 1", (module_code,)).fetchone()
        records = connection.execute(
            "SELECT id, created_at, kind, manuscript, counts FROM work_records WHERE module_code = %s "
            "ORDER BY created_at DESC, id DESC LIMIT 100", (module_code,)).fetchall()
        images = connection.execute(
            "SELECT count(DISTINCT p.image_id) AS total, count(DISTINCT p.image_id) FILTER (WHERE r.status = 'confirmed') AS confirmed "
            "FROM image_placements p LEFT JOIN image_rights r ON r.image_id = p.image_id WHERE p.module_code = %s", (module_code,)).fetchone()
    if not (totals or volume or records or images["total"] or done or history):
        return None
    by_plan = {row["is_plan"]: row for row in totals}
    reviews, plans = by_plan.get(False), by_plan.get(True)
    plan_latest = next((row for row in latest if row["check_name"] == "plan"), None)
    return {
        "reviews": {"count": reviews["n"], "first": iso(reviews["first_at"]), "last": iso(reviews["last_at"])} if reviews else {},
        "plan": {"count": plans["n"], "last": iso(plans["last_at"]), "verdict": plan_latest["verdict"] if plan_latest else None} if plans else {},
        "latest_checks": [{"id": str(row["id"]), "check": row["check_name"], "created_at": iso(row["created_at"]),
                           "verdict": row["verdict"], "sheet": row["sheet"] or []} for row in latest],
        "last_group": {"group_id": str(group["group_id"]), "created_at": iso(group["created_at"]), "checks": list(group["checks"]),
                       "verdict": group_verdict(list(group["verdicts"]))} if group else None,
        "volume": {"id": str(volume["id"]), "created_at": iso(volume["created_at"]), "manuscript": volume["manuscript"],
                   "pages": volume["pages"], "unit_price": volume["unit_price"], "fee": volume["fee"],
                   "estimated": volume["estimated"]} if volume else None,
        "volume_count": volume["total"] if volume else 0,
        "records": [{"id": str(row["id"]), "created_at": iso(row["created_at"]), "kind": row["kind"],
                     "manuscript": row["manuscript"], "counts": row["counts"]} for row in records],
        "images": {"total": images["total"], "confirmed": images["confirmed"]},
        "staged_reviews": {row["work_stage"]: {"count": row["n"], "last": iso(row["last_at"]), "verdict": row["verdict"]} for row in staged},
        "done": {row["stage"]: {"by": row["done_by"], "at": iso(row["done_at"]), "note": row["note"]} for row in done},
        "history": [{"stage": row["stage"], "action": row["action"], "by": row["changed_by"], "at": iso(row["changed_at"]),
                     "note": row["note"]} for row in history],
    }


def set_stage(dsn: str, module_code: str, stage: int, *, done: bool, by: str, note: str = "") -> bool:
    """단계 완료 표시(done=True) 또는 되돌림(False). 이력을 함께 남긴다. 상태가 실제로 바뀌었으면 True
    (이미 완료인 단계를 다시 완료로 표시하면 사람·시각·메모를 새로 쓰고 True, 완료가 아닌 단계를 되돌리면 False)."""
    with psycopg.connect(dsn) as connection:
        if done:
            connection.execute(
                "INSERT INTO manuscript_stages (module_code, stage, done_by, note) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (module_code, stage) DO UPDATE SET done_by = EXCLUDED.done_by, done_at = now(), note = EXCLUDED.note",
                (module_code, stage, by, note))
            changed = True
        else:
            changed = connection.execute("DELETE FROM manuscript_stages WHERE module_code = %s AND stage = %s",
                                         (module_code, stage)).rowcount > 0
        if changed:
            connection.execute(
                "INSERT INTO manuscript_stage_history (id, module_code, stage, action, changed_by, note) VALUES (%s, %s, %s, %s, %s, %s)",
                (str(uuid4()), module_code, stage, "done" if done else "undone", by, note))
    return changed


def tag_review_stage(dsn: str, run_id: str, stage: int) -> None:
    """원고 검수 실행에 고른 단계를 적는다(review_runs.work_stage)."""
    with psycopg.connect(dsn) as connection:
        connection.execute("UPDATE review_runs SET work_stage = %s WHERE id = %s", (stage, run_id))


# 기록 비우기 — 처음부터 다시 해 볼 때 쓴다(관리자 명령 postgres_cli clear). 계정과 이미지 저작권 DB는 건드리지 않는다.
HISTORY_TABLES = (   # (표, 화면에서 부르는 이름). 순서대로 지운다
    ("review_runs", "원고 검수·개발계획서 점검 이력(확인서, 입력 기록 포함)"),
    ("review_files", "검수할 때 보관한 원고 파일"),
    ("volume_runs", "원고 분량 산정 이력"),
    ("work_records", "의견 반영 검토·권리 증빙 점검의 개수 기록"),
    ("manuscript_stages", "진행 현황의 단계 완료 표시"),
    ("manuscript_stage_history", "단계 완료 표시 이력"),
)


def clear_history(dsn: str, *, apply: bool) -> list[tuple[str, str, int]]:
    """검수·분량·진행 현황 기록을 모두 지운다. apply=False면 지우지 않고 지금 몇 건인지만 센다. 반환: [(표, 이름, 건수)].
    review_results·review_inputs는 review_runs를 지우면 함께 지워진다(ON DELETE CASCADE)."""
    out = []
    with psycopg.connect(dsn) as connection:
        for table, label in HISTORY_TABLES:
            count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            out.append((table, label, count))
        if apply:
            for table, _ in HISTORY_TABLES:
                connection.execute(f"DELETE FROM {table}")
    return out
