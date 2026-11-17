"""이미지 저작권 DB(REQ-02-010) 적재 — 이미지 레코드를 006_image_db의 표에 넣는다.

    python -m ncs_service.image_db 레코드.json --by 담당자이름        # DATABASE_URL 필요

레코드 형식과 검사는 image_records(docs/IMAGE_RECORD.md). 여기서는 검사를 통과한 레코드를 표에 넣는 규칙만 정한다.

적재 규칙 — 같은 레코드를 몇 번 넣어도 결과가 같다:
  그림 파일   sha256이 같으면 같은 그림이다. 처음이면 새로 넣고, 이미 있으면 비어 있는 열만 채운다(있는 값은 덮지 않는다).
             키워드는 합친다. 업스케일본은 아직 없을 때만 넣는다.
  수록 위치   (그림, 모듈, 그림 번호, 문단 순번)이 같으면 같은 자리다. 새 자리는 추가하고, 있는 자리는 레코드가 적은 값으로 고친다
             (추출기를 고쳐 다시 돌리면 캡션·출처 줄이 바로잡혀야 하므로).
  권리 정보   없으면 '자동 태깅'으로 넣는다. 자동 태깅 상태면 레코드가 적은 묶음만 고치고 버전을 올린다.
             **기관이 확정한 권리 정보는 건드리지 않는다** — 자동 태깅 결과가 사람이 확정한 값을 지우면 안 된다.
             그런 건은 보고서의 '확정 유지'에 남는다. 고치려면 확정 화면에서 확정을 풀고 한다.
  수행준거    같은 (그림, 능력단위, 요소, 수행준거) 연결은 한 번만.
  변경 이력   새 그림은 'created', 권리 정보가 바뀌면 'updated'와 바뀐 열 {열: [이전, 이후]}.
레코드 1건이 실패해도(형식 오류, DB 제약 위반) 나머지는 적재한다. 실패한 건은 사유와 함께 보고서의 '거부'에 남는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .image_records import NormalRecord, RecordError, normalize, read_records
from .postgres import migrate

ASSET_FILL = ("source_id", "filename", "title", "format", "width_px", "height_px", "byte_size", "content", "kind")
UPSCALED = ("upscaled_content", "upscaled_format", "upscaled_width_px", "upscaled_height_px", "upscale_engine")
PLACEMENT_VALUES = ("module_name", "page", "caption", "source_line", "source_template", "context_text", "lesson_no",
                    "width_mm", "height_mm")


@dataclass
class LoadReport:
    """적재 결과. 필수 항목 충족률(정의서 REQ-02-010 검증 기준 99.5%)은 accepted / total."""
    total: int = 0
    created: int = 0                 # 새로 넣은 그림
    merged: int = 0                  # 이미 있던 그림에 합친 건
    placements_added: int = 0
    links_added: int = 0
    rights_updated: int = 0          # 자동 태깅 상태의 권리 정보를 고친 건
    kept_confirmed: list[str] = field(default_factory=list)   # 기관 확정이라 권리 정보를 건드리지 않은 그림(sha256)
    rejected: list[dict] = field(default_factory=list)        # [{'index', 'sha256', 'reasons'}]

    @property
    def accepted(self) -> int:
        return self.created + self.merged

    @property
    def acceptance_rate(self) -> float | None:
        return self.accepted / self.total if self.total else None

    def as_dict(self) -> dict:
        return {
            "전체": self.total, "적재": self.accepted, "새 그림": self.created, "기존 그림에 합침": self.merged,
            "추가된 수록 위치": self.placements_added, "추가된 수행준거 연결": self.links_added,
            "고친 권리 정보": self.rights_updated, "확정 유지": self.kept_confirmed, "거부": self.rejected,
            "필수 항목 충족률": None if self.acceptance_rate is None else round(self.acceptance_rate, 4),
        }


def _insert(connection, table: str, values: dict):
    connection.execute(
        f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))})", tuple(values.values()))


def _plain(value):
    """변경 이력(jsonb)에 넣을 수 있는 값으로."""
    return value.isoformat() if isinstance(value, date) else value


def _save_asset(connection, asset: dict) -> tuple[str, bool]:
    """(그림 id, 새로 넣었는가)."""
    found = connection.execute(
        "SELECT id, keywords, upscaled_content IS NOT NULL FROM image_assets WHERE sha256 = %s FOR UPDATE",
        (asset["sha256"],)).fetchone()
    if found is None:
        image_id = str(uuid4())
        _insert(connection, "image_assets", {"id": image_id, **asset})
        return image_id, True
    image_id, keywords, has_upscaled = str(found[0]), found[1], found[2]
    sets = [f"{column} = COALESCE({column}, %s)" for column in ASSET_FILL]
    values = [asset[column] for column in ASSET_FILL]
    sets.append("keywords = %s")
    values.append(list(dict.fromkeys([*keywords, *asset["keywords"]])))
    if not has_upscaled and asset["upscaled_content"] is not None:
        sets += [f"{column} = %s" for column in UPSCALED]
        values += [asset[column] for column in UPSCALED]
    connection.execute(f"UPDATE image_assets SET {', '.join(sets)} WHERE id = %s", (*values, image_id))
    return image_id, False


def _save_placement(connection, image_id: str, placement: dict) -> tuple[str, bool]:
    """(수록 위치 id, 새로 넣었는가). 있는 자리는 레코드가 적은 값(None이 아닌 것)으로 고친다."""
    values = {"id": str(uuid4()), "image_id": image_id, **placement}
    updates = ", ".join(f"{column} = COALESCE(EXCLUDED.{column}, image_placements.{column})" for column in PLACEMENT_VALUES)
    row = connection.execute(
        f"INSERT INTO image_placements ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))}) "
        f"ON CONFLICT (image_id, module_code, label, para_index) DO UPDATE SET {updates} "
        "RETURNING id, (xmax = 0)", tuple(values.values())).fetchone()
    return str(row[0]), row[1]


def _save_rights(connection, image_id: str, sha256: str, rights: dict | None, changed_by: str, report: LoadReport):
    if rights is None:
        return
    columns = list(rights)
    select = ", ".join(["status", "version", *columns])
    found = connection.execute(
        f"SELECT {select} FROM image_rights WHERE image_id = %s FOR UPDATE", (image_id,)).fetchone()
    if found is None:
        _insert(connection, "image_rights", {"image_id": image_id, **rights})
        return
    status, version, *current = found
    if status == "confirmed":
        report.kept_confirmed.append(sha256)
        return
    changes = {column: [_plain(old), _plain(rights[column])]
               for column, old in zip(columns, current) if old != rights[column]}
    if not changes:
        return
    sets = ", ".join(f"{column} = %s" for column in changes)
    connection.execute(
        f"UPDATE image_rights SET {sets}, version = version + 1, updated_at = now() WHERE image_id = %s",
        (*(rights[column] for column in changes), image_id))
    _insert(connection, "image_history", {"image_id": image_id, "changed_by": changed_by, "action": "updated",
                                          "version": version + 1, "changes": Jsonb(changes)})
    report.rights_updated += 1


def _save(connection, record: NormalRecord, changed_by: str, report: LoadReport) -> bool:
    """레코드 1건을 넣는다. 새 그림이면 True."""
    image_id, created = _save_asset(connection, record.asset)
    placement_ids = []
    for placement in record.placements:
        placement_id, added = _save_placement(connection, image_id, placement)
        placement_ids.append(placement_id)
        report.placements_added += added
    _save_rights(connection, image_id, record.asset["sha256"], record.rights, changed_by, report)
    for link in record.links:
        placement_id = None if link["placement"] is None else placement_ids[link["placement"]]
        done = connection.execute(
            "INSERT INTO image_ncs_links (id, image_id, placement_id, unit_code, element_code, criterion_no) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (image_id, unit_code, element_code, criterion_no) DO NOTHING",
            (str(uuid4()), image_id, placement_id, link["unit_code"], link["element_code"], link["criterion_no"]))
        report.links_added += done.rowcount
    if created:
        _insert(connection, "image_history", {
            "image_id": image_id, "changed_by": changed_by, "action": "created", "version": 1,
            "changes": Jsonb({"placements": len(record.placements), "links": len(record.links),
                              "rights": record.rights is not None})})
    return created


def _db_reason(error: psycopg.Error) -> str:
    constraint = getattr(error.diag, "constraint_name", None)
    message = (error.diag.message_primary or str(error)).strip()
    return f"DB 제약 위반({constraint}): {message}" if constraint else f"DB 오류: {message}"


def load_records(dsn: str, records: list, *, changed_by: str, base_dir: str | Path | None = None) -> LoadReport:
    """레코드 목록을 적재한다. 건마다 따로 처리해 한 건의 실패가 다른 건을 막지 않는다."""
    if not changed_by or not changed_by.strip():
        raise ValueError("changed_by(적재한 사람)가 필요합니다 — 변경 이력에 남습니다")
    report = LoadReport(total=len(records))
    with psycopg.connect(dsn) as connection:
        for index, raw in enumerate(records):
            sha256 = raw.get("sha256") if isinstance(raw, dict) else None
            try:
                record = normalize(raw, base_dir=base_dir)
            except RecordError as error:
                report.rejected.append({"index": index, "sha256": sha256, "reasons": error.reasons})
                continue
            before = (report.placements_added, report.links_added, report.rights_updated, len(report.kept_confirmed))
            try:
                with connection.transaction():           # 건마다 savepoint — 실패하면 이 건만 되돌린다
                    created = _save(connection, record, changed_by.strip(), report)
            except psycopg.Error as error:
                report.placements_added, report.links_added, report.rights_updated, kept = before
                del report.kept_confirmed[kept:]
                report.rejected.append({"index": index, "sha256": record.asset["sha256"], "reasons": [_db_reason(error)]})
                continue
            report.created += created
            report.merged += not created
    return report


def load_file(dsn: str, path: str | Path, *, changed_by: str) -> LoadReport:
    """레코드 JSON 파일을 적재한다. 레코드의 file 경로는 JSON 파일이 있는 폴더 기준."""
    records, base_dir = read_records(path)
    return load_records(dsn, records, changed_by=changed_by, base_dir=base_dir)


def check_records(records: list, *, base_dir: str | Path | None = None) -> dict:
    """DB에 넣지 않고 형식만 검사한다 → {'전체', '통과', '거부': [{'index', 'sha256', 'reasons'}]}."""
    rejected = []
    for index, raw in enumerate(records):
        try:
            normalize(raw, base_dir=base_dir)
        except RecordError as error:
            rejected.append({"index": index, "sha256": raw.get("sha256") if isinstance(raw, dict) else None,
                             "reasons": error.reasons})
    return {"전체": len(records), "통과": len(records) - len(rejected), "거부": rejected}


def flatten_file_names(records: list) -> list:
    """레코드의 file 경로를 파일 이름만 남긴다 — 화면에서 올린 파일은 폴더 없이 한곳에 놓이므로('images/a.png' → 'a.png')."""
    def flat(source):
        if isinstance(source, dict) and isinstance(source.get("file"), str):
            return {**source, "file": Path(source["file"].replace("\\", "/")).name}
        return source

    out = []
    for record in records:
        record = flat(record)
        if isinstance(record, dict) and "upscaled" in record:
            record = {**record, "upscaled": flat(record["upscaled"])}
        out.append(record)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="이미지 레코드 JSON을 이미지 저작권 DB에 적재")
    parser.add_argument("file", type=Path, help="레코드 JSON 파일(docs/IMAGE_RECORD.md) 또는 공공누리 수집 JSON(0.1-PoC)")
    parser.add_argument("--by", help="적재한 사람(변경 이력에 남는 이름). 적재할 때 필수")
    parser.add_argument("--check", action="store_true", help="DB에 넣지 않고 형식만 검사")
    args = parser.parse_args(argv)
    from . import kogl_import      # 공공누리 수집 JSON(0.1-PoC, REQ-02-012)도 같은 명령으로 넣는다

    data = json.loads(args.file.read_text(encoding="utf-8-sig"))
    kogl = kogl_import.is_dataset(data)
    if args.check:
        if kogl:
            result = kogl_import.run(None, data, base_dir=args.file.parent, check_only=True)
        else:
            records, base_dir = read_records(args.file)
            result = check_records(records, base_dir=base_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["거부"] else 0
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL이 필요합니다(.env). 형식만 보려면 --check", file=sys.stderr)
        return 2
    if not args.by:
        print("--by(적재한 사람)가 필요합니다", file=sys.stderr)
        return 2
    migrate(dsn)
    result = (kogl_import.run(dsn, data, base_dir=args.file.parent, by=args.by) if kogl
              else load_file(dsn, args.file, changed_by=args.by).as_dict())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["거부"] else 0


if __name__ == "__main__":
    sys.exit(main())
