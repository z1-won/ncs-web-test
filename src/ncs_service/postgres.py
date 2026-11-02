"""PostgreSQL 검수 이력 저장소. 검수 엔진과 웹 프레임워크에 의존하지 않는다."""

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


def save_review(dsn: str, review: ExecutedReview, inputs: list[dict], group_id: str | None = None) -> tuple[str, dict]:
    """한 건을 저장하고 (run_id, 요약)을 돌려준다. group_id는 전체 실행 묶음(uuid 문자열) — 단독 실행이면 None."""
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
            "INSERT INTO review_runs (id, check_name, module_code, verdict, engine_version, group_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (run_id, review.check, review.result.module_code, summary["검수결과"], version("ncs-f02-review"), group_id),
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
                 verdict: str | None = None, standalone: bool = False, limit: int = 50, offset: int = 0) -> list[dict]:
    """실행 목록(최신순). standalone=True면 전체 실행 묶음에 속하지 않은 단독 실행만."""
    clauses = []
    values: list = []
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


def list_groups(dsn: str, *, module_code: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    """전체 실행 묶음 목록(최신순). 한 묶음 = 한 행: 시작 시각, 모듈, 들어 있는 검수 이름·판정, 묶음 판정."""
    where = " AND module_code = %s" if module_code else ""
    values: list = [module_code] if module_code else []
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
