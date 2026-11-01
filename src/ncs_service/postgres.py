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

from .models import ExecutedReview
from .registry import get_engine

# 001: 최초 스키마. check_name의 허용값은 Python(registry.ENGINES)이 검증하므로 DB 제약으로 두지 않는다 — 엔진을
# 추가할 때 DB를 바꿀 필요가 없게 하기 위해서다.
SCHEMA = """
CREATE TABLE IF NOT EXISTS review_runs (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    check_name text NOT NULL,
    module_code text NOT NULL,
    verdict text NOT NULL,
    engine_version text,
    source text NOT NULL DEFAULT 'web' CHECK (source IN ('web', 'import'))
);
CREATE INDEX IF NOT EXISTS review_runs_created_idx ON review_runs (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS review_runs_module_idx ON review_runs (module_code, created_at DESC);
CREATE INDEX IF NOT EXISTS review_runs_check_idx ON review_runs (check_name, created_at DESC);
CREATE INDEX IF NOT EXISTS review_runs_verdict_idx ON review_runs (verdict, created_at DESC);
CREATE TABLE IF NOT EXISTS review_results (
    run_id uuid PRIMARY KEY REFERENCES review_runs(id) ON DELETE CASCADE,
    summary jsonb NOT NULL,
    sheet jsonb NOT NULL,
    diagnostics jsonb NOT NULL,
    findings jsonb NOT NULL,
    checklist jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS review_inputs (
    run_id uuid NOT NULL REFERENCES review_runs(id) ON DELETE CASCADE,
    role text NOT NULL,
    filename text NOT NULL,
    sha256 text,
    byte_size bigint,
    PRIMARY KEY (run_id, role)
);
"""

# 번호 순서로 한 번씩만 적용되는 스키마 변경. 적용된 항목은 수정하지 않고 새 번호를 뒤에 붙인다.
# 002: 초기 설치본에 있던 check_name CHECK 제약 제거(이름은 PostgreSQL 자동 명명 규칙 <표>_<열>_check).
MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("001_initial", SCHEMA),
    ("002_drop_check_name_constraint",
     "ALTER TABLE review_runs DROP CONSTRAINT IF EXISTS review_runs_check_name_check"),
)


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


def input_metadata(diagnostics: dict, uploads: list[tuple[str, Path]]) -> list[dict]:
    """진단의 역할별 임시 경로를 업로드 파일명·해시와 연결한다."""
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
        result.append({"role": role, "filename": filename,
                       "sha256": digest.hexdigest(),
                       "byte_size": path.stat().st_size})
    return result


def save_review(dsn: str, review: ExecutedReview, inputs: list[dict]) -> tuple[str, dict]:
    summary = summary_for(review)
    run_id = str(uuid4())
    diagnostics = copy.deepcopy(review.result.diagnostics)
    # 요청이 끝나면 사라지는 임시 경로 대신 지속되는 입력 이름을 기록한다.
    names = {item["role"]: item["filename"] for item in inputs}
    diagnostics["inputs"] = {role: names.get(role) for role in diagnostics.get("inputs", {})}
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO review_runs (id, check_name, module_code, verdict, engine_version) "
            "VALUES (%s, %s, %s, %s, %s)",
            (run_id, review.check, review.result.module_code, summary["검수결과"], version("ncs-f02-review")),
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
    return run_id, summary


def list_reviews(dsn: str, *, module_code: str | None = None, check: str | None = None,
                 verdict: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    clauses = []
    values: list = []
    for column, value in (("module_code", module_code), ("check_name", check), ("verdict", verdict)):
        if value:
            clauses.append(f"{column} = %s")
            values.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT id, created_at, check_name, module_code, verdict, engine_version, source "
            "FROM review_runs" + where + " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            (*values, limit, offset),
        ).fetchall()
    return [{**row, "id": str(row["id"]), "created_at": row["created_at"].isoformat()} for row in rows]


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
