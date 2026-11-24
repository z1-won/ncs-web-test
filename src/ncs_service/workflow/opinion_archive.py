"""의견 반영 검토의 보관(REQ-02-003 사람 작업 4번 '최종 판단·보관') — 세분류 건의 권에서 돌린 검토만 남긴다.

따로 연 의견 반영 검토는 전처럼 개수만 남고 의견 글과 파일은 남지 않는다. 건에서 연 검토는 그 건의 기록이므로
(판본 파일을 건에 보관하는 것과 같다) 올린 의견서 파일, 의견별 결과(의견 글, 판정 후보, 근거 문단), 담당자 확정을 함께 둔다.
개수 기록(work_records)을 지우면 보관한 것도 같이 지워진다. 표는 migrations 021.
"""

from __future__ import annotations

import hashlib
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def keep(dsn: str, record_id: str, result: dict, files: list[tuple[str, str, bytes]], *, name: str = "") -> bool:
    """검토 한 건을 보관한다. files = [(차수, 파일 이름, 내용)] — 의견서만(원고는 건의 판본으로 이미 있다). 같은 기록을 다시 보관하면 바꾼다."""
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO opinion_archives (record_id, result, kept_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (record_id) DO UPDATE SET result = EXCLUDED.result, kept_name = EXCLUDED.kept_name, created_at = now()",
            (record_id, Jsonb(result), name))
        connection.execute("DELETE FROM opinion_archive_files WHERE record_id = %s", (record_id,))
        for round_name, filename, content in files:
            connection.execute(
                "INSERT INTO opinion_archive_files (id, record_id, round, filename, sha256, byte_size, content) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (str(uuid4()), record_id, round_name or "", filename, hashlib.sha256(content).hexdigest(), len(content), content))
    return True


def get(dsn: str, record_id: str) -> dict | None:
    """보관한 검토 — {'result', 'decisions', 'decided', 'kept_by', 'created_at', 'files': [{'id', 'round', 'filename', 'byte_size'}]}. 없으면 None."""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute("SELECT result, decisions, decided_name, decided_at, kept_name, created_at FROM opinion_archives WHERE record_id = %s",
                                 (record_id,)).fetchone()
        if row is None:
            return None
        files = connection.execute("SELECT id, round, filename, byte_size FROM opinion_archive_files WHERE record_id = %s ORDER BY round, filename",
                                   (record_id,)).fetchall()
    return {"result": row["result"], "decisions": row["decisions"] or {},
            "decided": {"by": row["decided_name"], "at": row["decided_at"].isoformat()} if row["decided_at"] else None,
            "kept_by": row["kept_name"], "created_at": row["created_at"].isoformat(),
            "files": [{"id": str(item["id"]), "round": item["round"], "filename": item["filename"], "byte_size": item["byte_size"]} for item in files]}


def file(dsn: str, record_id: str, file_id: str) -> tuple[str, bytes] | None:
    """보관한 의견서 파일 하나 — (파일 이름, 내용)."""
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT filename, content FROM opinion_archive_files WHERE record_id = %s AND id = %s", (record_id, file_id)).fetchone()
    return (row[0], bytes(row[1])) if row else None


def set_decisions(dsn: str, record_id: str, decisions: dict[str, str], *, name: str = "") -> bool:
    """보관한 검토에 의견별 담당자 확정(의견 번호 → 반영/미반영)을 적는다. 보관한 검토가 있었으면 True."""
    with psycopg.connect(dsn) as connection:
        cursor = connection.execute("UPDATE opinion_archives SET decisions = %s, decided_name = %s, decided_at = now() WHERE record_id = %s",
                                    (Jsonb(decisions), name, record_id))
        return cursor.rowcount > 0


def kept_ids(connection, record_ids: list[str]) -> set[str]:
    """그 기록들 가운데 보관한 검토가 있는 것."""
    if not record_ids:
        return set()
    rows = connection.execute("SELECT record_id FROM opinion_archives WHERE record_id = ANY(%s::uuid[])", (record_ids,)).fetchall()
    return {str(row["record_id"] if isinstance(row, dict) else row[0]) for row in rows}
