"""PostgreSQL 검수 이력 저장소. 검수 엔진과 웹 프레임워크에 의존하지 않는다."""

from __future__ import annotations

import copy
import hashlib
from importlib.metadata import version
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ncs_core.reporting import report_summary
from .models import ExecutedReview

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_runs (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    check_name text NOT NULL CHECK (check_name IN ('position', 'toc', 'overview', 'knowledge')),
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

REPORTS = {
    "position": ("ncs_position.reporting", "위치"),
    "toc": ("ncs_toc.reporting", "차례"),
    "overview": ("ncs_overview.reporting", "개요"),
    "knowledge": ("ncs_knowledge.reporting", "필요지식"),
}


def migrate(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(SCHEMA)


def summary_for(review: ExecutedReview) -> dict:
    from importlib import import_module

    module_name, name = REPORTS[review.check]
    reporting = import_module(module_name)
    return report_summary(review.result, name=name, item_files=reporting.ITEM_FILES,
                          other_tail=f"{name}_기타")


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
