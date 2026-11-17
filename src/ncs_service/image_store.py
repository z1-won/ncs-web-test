"""이미지 저작권 DB(REQ-02-010) 조회와 기관 확정 — 확정 화면(/api/images)과 추천용 조회(/api/images/recommendable)가 쓴다.

적재는 image_db, 형식 검사는 image_records. 여기서는 읽기와 사람이 하는 변경(수정·확정·확정 취소)만 다룬다.

두 갈래의 조회:
  관리용    list_images / get_image / image_file — 모든 그림. 확정하려면 그림을 봐야 하므로 파일도 내준다
  추천용    list_recommendable / recommendable_file — 뷰 v_image_recommendable(기관 확정 + 재사용 범위가 정해진 것) 중
            산출물 분류가 '비공개'가 아닌 것만(REQ-04-002·006). 추천(REQ-02-011)과 생성형 AI가 부르는 쪽은 이것만 쓴다.
            항목마다 원본 출처와 라이선스 유형·이용조건이 함께 나간다(REQ-04-006).
사람이 하는 변경:
  update_rights   자동 태깅 상태에서만. 확정된 것은 확정을 푼 뒤 고친다(확정값이 조용히 바뀌지 않게)
  confirm         분류·귀속이 있어야 한다(DB 제약 image_rights_confirmed_check와 같은 조건을 먼저 사람 말로 알려 준다)
  unconfirm       자동 태깅 상태로 되돌린다
모든 변경은 버전을 올리고 image_history에 누가·무엇을 남긴다. 요청이 version을 주면 그 버전일 때만 바꾼다
(두 사람이 같은 그림을 열어 놓고 차례로 저장해 앞사람의 수정을 덮는 일을 막는다).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import image_terms
from .image_records import RecordError, rights_changes

RIGHTS_COLUMNS = (
    "status", "confirmed_by", "confirmed_at", "version", "updated_at", "category", "ownership", "reuse_scope",
    "release_class", "license_scheme", "kogl_type", "kogl_ai", "cc_license", "license_note", "attribution",
    "non_commercial", "no_derivatives", "share_alike", "author", "source_org", "source_url", "retrieved_on",
    "credit_line", "ai_used", "ai_usage", "ai_mode", "ai_tool", "ai_date", "ai_original_source",
    "ai_pledge_submitted", "ai_tos_scope")
ASSET_COLUMNS = ("id", "sha256", "source_id", "created_at", "filename", "title", "format", "width_px", "height_px", "byte_size",
                 "kind", "keywords", "upscaled_format", "upscaled_width_px", "upscaled_height_px", "upscale_engine")
MEDIA_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "jpeg-progressive": "image/jpeg", "jpg": "image/jpeg",
               "bmp": "image/bmp", "gif": "image/gif"}
REQUIRED_TO_CONFIRM = {"category": "분류 체계", "ownership": "권리 귀속"}


class ImageNotFound(LookupError):
    """그 id의 그림(또는 파일)이 없다."""


class ImageConflict(RuntimeError):
    """지금 상태에서는 할 수 없는 변경 — 확정된 것을 수정, 다른 사람이 먼저 바꿈 등."""


def _uuid(image_id: str) -> str:
    try:
        return str(UUID(str(image_id)))
    except ValueError:
        raise ImageNotFound("그림을 찾을 수 없습니다") from None


def _plain(value):
    """JSON으로 내보낼 수 있는 값으로."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _row(row: dict) -> dict:
    return {key: _plain(value) for key, value in row.items()}


def terms() -> dict:
    """허용값 코드 → 이름. 화면의 선택 목록과 표시 글이 여기서 나온다."""
    return {
        "status": image_terms.STATUS, "category": image_terms.CATEGORY, "ownership": image_terms.OWNERSHIP,
        "reuse_scope": image_terms.REUSE_SCOPE, "release_class": image_terms.RELEASE_CLASS,
        "license_scheme": image_terms.LICENSE_SCHEME, "kind": image_terms.KIND, "ai_mode": image_terms.AI_MODE,
        "evidence_kind": image_terms.EVIDENCE_KIND, "history_action": image_terms.HISTORY_ACTION,
        "ai_usage": {str(no): {"name": name, "mode": mode} for no, (name, mode) in image_terms.AI_USAGE.items()},
        "kogl_type": {str(no): dict(zip(("attribution", "non_commercial", "no_derivatives"), conditions))
                      for no, conditions in image_terms.KOGL_CONDITIONS.items()},
        "cc_license": {code: dict(zip(("attribution", "non_commercial", "no_derivatives", "share_alike"), conditions))
                       for code, conditions in image_terms.CC_LICENSE.items()},
    }


# ───────────────────────── 조회 ─────────────────────────

LIST_SELECT = """
SELECT a.id, a.sha256, a.source_id, a.title, a.filename, a.kind, a.format, a.width_px, a.height_px, a.keywords, a.created_at,
       (a.content IS NOT NULL) AS has_file, (a.upscaled_content IS NOT NULL) AS has_upscaled,
       r.status, r.version, r.category, r.ownership, r.reuse_scope, r.release_class, r.license_scheme, r.kogl_type,
       r.kogl_ai, r.cc_license, r.ai_used, r.confirmed_by, r.confirmed_at,
       (SELECT count(*) FROM image_placements p WHERE p.image_id = a.id) AS placement_count,
       (SELECT count(DISTINCT p.module_code) FROM image_placements p WHERE p.image_id = a.id) AS module_count,
       (SELECT count(*) FROM image_evidence e WHERE e.image_id = a.id) AS evidence_count,
       first.module_code, first.label, first.caption
FROM image_assets a
LEFT JOIN image_rights r ON r.image_id = a.id
LEFT JOIN LATERAL (SELECT p.module_code, p.label, p.caption FROM image_placements p WHERE p.image_id = a.id
                   ORDER BY p.created_at, p.module_code, p.para_index, p.label LIMIT 1) first ON true
"""


def _filters(*, module_code=None, unit_code=None, keyword=None, q=None, kind=None, alias="a") -> tuple[list[str], list]:
    """관리용·추천용이 함께 쓰는 조건 — 그림 자체와 수록 위치·수행준거에 대한 것."""
    where, params = [], []
    if module_code:
        where.append(f"EXISTS (SELECT 1 FROM image_placements p WHERE p.image_id = {alias}.id AND p.module_code = %s)")
        params.append(module_code)
    if unit_code:
        where.append(f"EXISTS (SELECT 1 FROM image_ncs_links l WHERE l.image_id = {alias}.id AND l.unit_code = %s)")
        params.append(unit_code)
    if keyword:
        where.append(f"{alias}.keywords @> %s")
        params.append([keyword])
    if kind:
        where.append(f"{alias}.kind = %s")
        params.append(kind)
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append(
            f"({alias}.title ILIKE %s OR {alias}.filename ILIKE %s OR {alias}.source_id ILIKE %s OR EXISTS (SELECT 1 FROM unnest({alias}.keywords) k "
            f"WHERE k ILIKE %s) OR EXISTS (SELECT 1 FROM image_placements p WHERE p.image_id = {alias}.id "
            "AND (p.caption ILIKE %s OR p.context_text ILIKE %s)))")
        params += [like] * 6
    return where, params


def list_images(dsn: str, *, status: str | None = None, category: str | None = None, license_scheme: str | None = None,
                kogl_type: int | None = None, reuse_scope: str | None = None, module_code: str | None = None,
                unit_code: str | None = None, keyword: str | None = None, q: str | None = None,
                kind: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    """관리용 목록 — {'total', 'items'}. status='none'은 권리 정보가 아직 없는 그림."""
    where, params = _filters(module_code=module_code, unit_code=unit_code, keyword=keyword, q=q, kind=kind)
    if status == "none":
        where.append("r.image_id IS NULL")
    elif status:
        where.append("r.status = %s")
        params.append(status)
    for column, value in (("category", category), ("license_scheme", license_scheme), ("kogl_type", kogl_type),
                          ("reuse_scope", reuse_scope)):
        if value is not None:
            where.append(f"r.{column} = %s")
            params.append(value)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        total = connection.execute(
            f"SELECT count(*) AS n FROM image_assets a LEFT JOIN image_rights r ON r.image_id = a.id{clause}",
            params).fetchone()["n"]
        rows = connection.execute(
            f"{LIST_SELECT}{clause} ORDER BY a.created_at DESC, a.id LIMIT %s OFFSET %s", (*params, limit, offset)).fetchall()
    return {"total": total, "items": [_row(row) for row in rows]}


def get_image(dsn: str, image_id: str) -> dict:
    """그림 1건의 모든 것(파일 내용 제외) — 그림, 수록 위치, 권리 정보, 증빙, 수행준거, 변경 이력."""
    image_id = _uuid(image_id)
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        asset = connection.execute(
            f"SELECT {', '.join(ASSET_COLUMNS)}, (content IS NOT NULL) AS has_file, "
            "(upscaled_content IS NOT NULL) AS has_upscaled FROM image_assets WHERE id = %s", (image_id,)).fetchone()
        if asset is None:
            raise ImageNotFound("그림을 찾을 수 없습니다")
        rights = connection.execute(
            f"SELECT {', '.join(RIGHTS_COLUMNS)} FROM image_rights WHERE image_id = %s", (image_id,)).fetchone()

        def many(sql: str) -> list[dict]:
            return [_row(row) for row in connection.execute(sql, (image_id,)).fetchall()]

        return {
            **_row(asset),
            "rights": _row(rights) if rights else None,
            "placements": many(
                "SELECT id, module_code, module_name, page, label, caption, source_line, source_template, context_text, "
                "lesson_no, para_index, width_mm::float8 AS width_mm, height_mm::float8 AS height_mm "
                "FROM image_placements WHERE image_id = %s ORDER BY module_code, para_index, label"),
            "links": many("SELECT id, placement_id, unit_code, element_code, criterion_no FROM image_ncs_links "
                          "WHERE image_id = %s ORDER BY unit_code, element_code, criterion_no"),
            "evidence": many("SELECT id, kind, file_ref, file_sha256, submitted_on, note, created_at FROM image_evidence "
                             "WHERE image_id = %s ORDER BY created_at, id"),
            "history": many("SELECT changed_at, changed_by, action, version, changes FROM image_history "
                            "WHERE image_id = %s ORDER BY changed_at DESC, id DESC"),
        }


def _file(connection, image_id: str, upscaled: bool, extra_where: str = "") -> tuple[bytes, str]:
    column, format_column = ("upscaled_content", "upscaled_format") if upscaled else ("content", "format")
    row = connection.execute(
        f"SELECT a.{column}, a.{format_column} FROM image_assets a WHERE a.id = %s{extra_where}", (image_id,)).fetchone()
    if row is None or row[0] is None:
        raise ImageNotFound("그림 파일이 없습니다")
    return bytes(row[0]), MEDIA_TYPES.get((row[1] or "").lower(), "application/octet-stream")


def image_file(dsn: str, image_id: str, *, upscaled: bool = False) -> tuple[bytes, str]:
    """관리용: (그림 파일, media type)."""
    with psycopg.connect(dsn) as connection:
        return _file(connection, _uuid(image_id), upscaled)


RECOMMENDABLE = "v.release_class IS DISTINCT FROM 'private'"


def list_recommendable(dsn: str, *, module_code: str | None = None, unit_code: str | None = None,
                       keyword: str | None = None, q: str | None = None, kind: str | None = None,
                       limit: int = 50, offset: int = 0) -> dict:
    """추천용 목록 — 권리가 확인됐고 비공개가 아닌 그림만. 정부 귀속 + 전체 재사용 자산을 앞에 둔다(REQ-02-011)."""
    where, params = _filters(module_code=module_code, unit_code=unit_code, keyword=keyword, q=q, kind=kind, alias="v")
    clause = " AND ".join([RECOMMENDABLE, *where])
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        total = connection.execute(f"SELECT count(*) AS n FROM v_image_recommendable v WHERE {clause}", params).fetchone()["n"]
        rows = connection.execute(
            "SELECT v.*, (SELECT count(*) FROM image_placements p WHERE p.image_id = v.id) AS placement_count "
            f"FROM v_image_recommendable v WHERE {clause} "
            "ORDER BY (v.ownership = 'government' AND v.reuse_scope = 'all') DESC, v.confirmed_at DESC, v.id "
            "LIMIT %s OFFSET %s", (*params, limit, offset)).fetchall()
    items = []
    for row in rows:
        item = _row(row)
        # 이용허락 한정 자산은 '범위 확인 필요'로 표시한다(REQ-02-011)
        item["scope_check_needed"] = row["ownership"] == "licensed" or row["reuse_scope"] == "module_only"
        items.append(item)
    return {"total": total, "items": items}


def recommendable_file(dsn: str, image_id: str, *, upscaled: bool = False) -> tuple[bytes, str]:
    """추천용: 추천 목록에 나오는 그림의 파일만 내준다. 미확정·범위 미확인·비공개는 없는 것으로 답한다."""
    with psycopg.connect(dsn) as connection:
        return _file(connection, _uuid(image_id), upscaled,
                     f" AND EXISTS (SELECT 1 FROM v_image_recommendable v WHERE v.id = a.id AND {RECOMMENDABLE})")


# ───────────────────────── 사람이 하는 변경 ─────────────────────────

def _who(name: str | None) -> str:
    if not name or not name.strip():
        raise ValueError("by(변경한 사람)가 필요합니다 — 변경 이력에 남습니다")
    return name.strip()


def _locked_rights(connection, image_id: str, columns: tuple[str, ...] = ()):
    """그 그림의 권리 행을 잠가 읽는다 → dict 또는 None(권리 정보 없음). 그림이 없으면 ImageNotFound."""
    if connection.execute("SELECT 1 FROM image_assets WHERE id = %s FOR UPDATE", (image_id,)).fetchone() is None:
        raise ImageNotFound("그림을 찾을 수 없습니다")
    names = ("status", "version", *columns)
    row = connection.execute(
        f"SELECT {', '.join(names)} FROM image_rights WHERE image_id = %s FOR UPDATE", (image_id,)).fetchone()
    return dict(zip(names, row)) if row else None


def _check_version(current: dict | None, version: int | None):
    if version is not None and current is not None and current["version"] != version:
        raise ImageConflict(f"다른 사람이 먼저 바꿨습니다(지금 버전 {current['version']}, 보낸 버전 {version}). 다시 열어 확인하세요")


def _history(connection, image_id: str, by: str, action: str, version: int, changes: dict):
    connection.execute(
        "INSERT INTO image_history (image_id, changed_by, action, version, changes) VALUES (%s, %s, %s, %s, %s)",
        (image_id, by, action, version, Jsonb(changes)))


def update_rights(dsn: str, image_id: str, rights, *, by: str, version: int | None = None) -> dict:
    """권리 정보를 고친다(자동 태깅 상태에서만). rights의 모양은 레코드의 rights와 같고 null은 그 칸을 비운다.

    형식이 틀리면 RecordError, 확정된 것이거나 버전이 다르면 ImageConflict, DB 제약에 걸리면 ValueError(사유 포함).
    """
    by, image_id = _who(by), _uuid(image_id)
    changes = rights_changes(rights)
    columns = tuple(changes)
    try:
        with psycopg.connect(dsn) as connection:
            current = _locked_rights(connection, image_id, columns)
            _check_version(current, version)
            if current is None:
                values = {"image_id": image_id, **changes}
                connection.execute(
                    f"INSERT INTO image_rights ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))})",
                    tuple(values.values()))
                _history(connection, image_id, by, "updated", 1,
                         {column: [None, _plain(value)] for column, value in changes.items() if value is not None})
            else:
                if current["status"] == "confirmed":
                    raise ImageConflict("기관 확정된 권리 정보입니다. 확정을 푼 뒤 수정하세요")
                diff = {column: [_plain(current[column]), _plain(changes[column])]
                        for column in columns if current[column] != changes[column]}
                if diff:
                    sets = ", ".join(f"{column} = %s" for column in diff)
                    connection.execute(
                        f"UPDATE image_rights SET {sets}, version = version + 1, updated_at = now() WHERE image_id = %s",
                        (*(changes[column] for column in diff), image_id))
                    _history(connection, image_id, by, "updated", current["version"] + 1, diff)
    except psycopg.errors.CheckViolation as error:
        raise ValueError(_constraint_message(error)) from None
    return get_image(dsn, image_id)


CONSTRAINT_MESSAGES = {
    "image_rights_kogl_ownership_check": "귀속이 공공누리 조건이면 공공누리 유형이 필요합니다",
    "image_rights_license_columns_check": "라이선스 체계와 유형이 맞지 않습니다",
    "image_rights_kogl_conditions_check": "이용조건이 공공누리 유형과 맞지 않습니다",
    "image_rights_cc_conditions_check": "이용조건이 CC 유형과 맞지 않습니다",
    "image_rights_kogl_ai_check": "AI유형은 제1~4유형과만 함께 표시됩니다",
    "image_rights_ai_fields_check": "AI를 쓰지 않은 그림에 AI 필드를 채울 수 없습니다",
    "image_rights_ai_usage_mode_check": "AI 활용 유형과 방식이 맞지 않습니다",
    "image_rights_confirmed_check": "확정에는 분류 체계·권리 귀속·확정자가 필요합니다",
}


def _constraint_message(error: psycopg.Error) -> str:
    name = getattr(error.diag, "constraint_name", None)
    return CONSTRAINT_MESSAGES.get(name, f"저장할 수 없는 값입니다({name or error.diag.message_primary})")


def confirm(dsn: str, image_id: str, *, by: str, version: int | None = None) -> dict:
    """기관 확정. 분류·귀속이 없으면 ValueError(무엇이 빠졌는지), 이미 확정이면 ImageConflict."""
    by, image_id = _who(by), _uuid(image_id)
    with psycopg.connect(dsn) as connection:
        current = _locked_rights(connection, image_id, ("category", "ownership", "reuse_scope"))
        _check_version(current, version)
        if current is not None and current["status"] == "confirmed":
            raise ImageConflict("이미 기관 확정된 그림입니다")
        missing = [name for column, name in REQUIRED_TO_CONFIRM.items() if current is None or current[column] is None]
        if missing:
            raise ValueError("확정하려면 " + "·".join(missing) + "을(를) 먼저 입력하세요")
        connection.execute(
            "UPDATE image_rights SET status = 'confirmed', confirmed_by = %s, confirmed_at = now(), "
            "version = version + 1, updated_at = now() WHERE image_id = %s", (by, image_id))
        _history(connection, image_id, by, "confirmed", current["version"] + 1, {"status": ["auto", "confirmed"]})
    found = get_image(dsn, image_id)
    # 확정은 됐지만 추천에는 나오지 않는 경우를 화면이 알려 줄 수 있게
    found["notice"] = ("재사용 범위가 '미확인'이라 추천 목록에는 나오지 않습니다"
                       if found["rights"]["reuse_scope"] == "unknown" else None)
    return found


def unconfirm(dsn: str, image_id: str, *, by: str, version: int | None = None) -> dict:
    """확정 취소 — 자동 태깅 상태로 되돌린다(값은 그대로). 확정 상태가 아니면 ImageConflict."""
    by, image_id = _who(by), _uuid(image_id)
    with psycopg.connect(dsn) as connection:
        current = _locked_rights(connection, image_id, ("confirmed_by",))
        _check_version(current, version)
        if current is None or current["status"] != "confirmed":
            raise ImageConflict("기관 확정 상태가 아닙니다")
        connection.execute(
            "UPDATE image_rights SET status = 'auto', confirmed_by = NULL, confirmed_at = NULL, "
            "version = version + 1, updated_at = now() WHERE image_id = %s", (image_id,))
        _history(connection, image_id, by, "unconfirmed", current["version"] + 1,
                 {"status": ["confirmed", "auto"], "confirmed_by": [current["confirmed_by"], None]})
    return get_image(dsn, image_id)


def add_evidence(dsn: str, sha256: str, kind: str, *, by: str, file_ref: str | None = None,
                 submitted_on: date | None = None, note: str | None = None) -> bool:
    """그 그림(sha256)에 증빙 1건을 잇는다(REQ-02-014 '확인된 증빙은 이미지 저작권 DB에 연결'). 새로 넣었으면 True.

    같은 그림에 같은 종류·같은 파일의 증빙이 이미 있으면 다시 넣지 않는다(점검을 여러 번 돌려도 한 건).
    그 그림이 DB에 없으면 ImageNotFound, 종류가 허용값이 아니면 ValueError.
    """
    by = _who(by)
    if kind not in image_terms.EVIDENCE_KIND:
        raise ValueError(f"증빙 종류 '{kind}'는 허용값이 아닙니다")
    with psycopg.connect(dsn) as connection:
        found = connection.execute("SELECT id FROM image_assets WHERE sha256 = %s FOR UPDATE", (sha256,)).fetchone()
        if found is None:
            raise ImageNotFound("그림을 찾을 수 없습니다")
        image_id = found[0]
        if connection.execute(
                "SELECT 1 FROM image_evidence WHERE image_id = %s AND kind = %s AND file_ref IS NOT DISTINCT FROM %s",
                (image_id, kind, file_ref)).fetchone():
            return False
        connection.execute(
            "INSERT INTO image_evidence (id, image_id, kind, file_ref, submitted_on, note) VALUES (%s, %s, %s, %s, %s, %s)",
            (str(uuid4()), image_id, kind, file_ref, submitted_on, note))
        _history(connection, str(image_id), by, "evidence_added", None,
                 {"evidence": [None, image_terms.EVIDENCE_KIND[kind] + (f" ({file_ref})" if file_ref else "")]})
    return True


__all__ = ["ImageConflict", "ImageNotFound", "RecordError", "add_evidence", "confirm", "get_image", "image_file", "list_images",
           "list_recommendable", "recommendable_file", "terms", "unconfirm", "update_rights"]
