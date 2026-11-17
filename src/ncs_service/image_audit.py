"""이미지 저작권 DB 점검(REQ-02-010 검증 기준) — 지금 DB에 든 것으로 두 가지를 센다.

    python -m ncs_service.image_audit [--json]        # DATABASE_URL 필요. 노출이 1건이라도 있으면 종료 코드 1

  필수 항목   '권리 정보 필수 항목 충족(구조·형식 정확성 99.5%)'. 그림마다 그 그림에 해당하는 항목만 따져
              채워진 항목 ÷ 따진 항목으로 낸다. 전체와 기관 확정분을 따로 낸다(자동 태깅 상태는 덜 채워진 것이 정상이다)
  추천 노출   '재사용 범위 미확인 이미지의 추천 노출 0건'. 추천이 실제로 쓰는 세 길 — 뷰(v_image_recommendable),
              추천용 목록(image_store.list_recommendable), 추천 후보(image_recommend.candidates) — 에서 나온 그림을
              원래 표(image_rights)와 다시 맞춰, 확정이 아니거나 재사용 범위가 미확인이거나 비공개인 것을 센다
적재할 때의 충족률(거부되지 않은 레코드 ÷ 전체)은 적재 보고서(image_db.LoadReport)가 따로 낸다. 여기는 들어간 뒤의 상태다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg
from psycopg.rows import dict_row

from . import image_recommend, image_store

# (이름, 해당하는 그림, 채워졌다고 보는 조건) — r: image_rights, a: image_assets. 권리 정보가 없는 그림은 r.*가 NULL이다
REQUIRED: tuple[tuple[str, str, str], ...] = (
    ("그림 파일", "true", "a.content IS NOT NULL AND a.format IS NOT NULL AND a.width_px IS NOT NULL AND a.height_px IS NOT NULL"),
    ("권리 정보", "true", "r.image_id IS NOT NULL"),
    ("분류 체계", "r.image_id IS NOT NULL", "r.category IS NOT NULL"),
    ("권리 귀속", "r.image_id IS NOT NULL", "r.ownership IS NOT NULL"),
    ("재사용 범위", "r.image_id IS NOT NULL", "r.reuse_scope <> 'unknown'"),
    ("라이선스 유형(공공누리·공유마당 자료)", "r.category = 'public_license'", "r.license_scheme IS NOT NULL"),
    ("이용조건(라이선스 유형이 있는 자료)", "r.kogl_type IS NOT NULL OR r.cc_license IS NOT NULL",
     "r.attribution IS NOT NULL AND r.non_commercial IS NOT NULL AND r.no_derivatives IS NOT NULL"),
    ("원 출처 기관·URL·검색일(공공누리)", "r.license_scheme = 'kogl'",
     "r.source_org IS NOT NULL AND r.source_url IS NOT NULL AND r.retrieved_on IS NOT NULL"),
    ("출처 문구(공공누리)", "r.license_scheme = 'kogl'", "r.credit_line IS NOT NULL"),
    ("AI 활용 방식·도구·일자(AI 활용 그림)", "r.ai_used", "r.ai_mode IS NOT NULL AND r.ai_tool IS NOT NULL AND r.ai_date IS NOT NULL"),
    ("양도 동의서(직접제작·제작의뢰)", "r.category IN ('author_made', 'commissioned')",
     "EXISTS (SELECT 1 FROM image_evidence e WHERE e.image_id = a.id AND e.kind = 'transfer_consent')"),
    ("이용허락 동의서(포괄적 이용허락)", "r.category = 'blanket_license'",
     "EXISTS (SELECT 1 FROM image_evidence e WHERE e.image_id = a.id AND e.kind = 'license_consent')"),
    ("AI 서약서(AI 활용 그림)", "r.ai_used",
     "(r.ai_pledge_submitted IS TRUE OR EXISTS (SELECT 1 FROM image_evidence e WHERE e.image_id = a.id AND e.kind = 'ai_pledge'))"),
)
BASE = "FROM image_assets a LEFT JOIN image_rights r ON r.image_id = a.id"
# 추천에 나오면 안 되는 그림: 확정이 아님, 재사용 범위 미확인, 비공개
NOT_CLEARED = "(r.image_id IS NULL OR r.status <> 'confirmed' OR r.reuse_scope = 'unknown' OR r.release_class IS NOT DISTINCT FROM 'private')"


def _rate(filled: int, asked: int) -> float | None:
    return round(filled / asked, 4) if asked else None


def _required(connection, scope: str) -> dict:
    """scope에 드는 그림의 필수 항목 — {'그림', '따진 항목', '채워진 항목', '충족률', '항목별': [{'항목', '해당', '충족', '충족률'}]}."""
    selects = ", ".join(f"count(*) FILTER (WHERE ({applies})) AS a{i}, count(*) FILTER (WHERE ({applies}) AND ({filled})) AS f{i}"
                        for i, (_, applies, filled) in enumerate(REQUIRED))
    row = connection.execute(f"SELECT count(*) AS n, {selects} {BASE} WHERE {scope}").fetchone()
    items = [{"항목": name, "해당": row[f"a{i}"], "충족": row[f"f{i}"], "충족률": _rate(row[f"f{i}"], row[f"a{i}"])}
             for i, (name, _, _) in enumerate(REQUIRED)]
    asked, filled = sum(item["해당"] for item in items), sum(item["충족"] for item in items)
    return {"그림": row["n"], "따진 항목": asked, "채워진 항목": filled, "충족률": _rate(filled, asked), "항목별": items}


def _exposed(connection, ids: list[str]) -> list[dict]:
    """추천 쪽에서 나온 그림 가운데 나오면 안 되는 것 — [{'id', 'status', 'reuse_scope', 'release_class'}]."""
    if not ids:
        return []
    rows = connection.execute(
        f"SELECT a.id::text AS id, r.status, r.reuse_scope, r.release_class {BASE} WHERE a.id = ANY(%s::uuid[]) AND {NOT_CLEARED}",
        (ids,)).fetchall()
    return [dict(row) for row in rows]


def audit(dsn: str) -> dict:
    """→ {'건수', '필수 항목': {'전체', '기관 확정'}, '추천 노출': {'경로별': […], '노출': n}, '판정'}."""
    listed, offset = [], 0
    while True:                                         # 추천용 목록을 끝까지
        page = image_store.list_recommendable(dsn, limit=100, offset=offset)
        listed += [item["id"] for item in page["items"]]
        offset += 100
        if offset >= page["total"]:
            break
    candidates = [item["id"] for item in image_recommend.candidates(dsn)]
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        counts = connection.execute(
            f"SELECT count(*) AS 그림, count(r.image_id) AS \"권리 정보 있음\", "
            f"count(*) FILTER (WHERE r.status = 'confirmed') AS \"기관 확정\", "
            f"count(*) FILTER (WHERE r.status = 'auto') AS \"자동 태깅\", "
            f"count(*) FILTER (WHERE r.status = 'confirmed' AND r.reuse_scope = 'unknown') AS \"확정이지만 재사용 범위 미확인\", "
            f"count(*) FILTER (WHERE r.release_class = 'private') AS 비공개, "
            f"count(*) FILTER (WHERE NOT {NOT_CLEARED}) AS \"추천 대상\" {BASE}").fetchone()
        counts = {**counts,
                  "수록 위치": connection.execute("SELECT count(*) AS n FROM image_placements").fetchone()["n"],
                  "증빙": connection.execute("SELECT count(*) AS n FROM image_evidence").fetchone()["n"],
                  "수행준거 연결": connection.execute("SELECT count(*) AS n FROM image_ncs_links").fetchone()["n"]}
        view = [row["id"] for row in connection.execute("SELECT id::text AS id FROM v_image_recommendable").fetchall()]
        # 뷰는 비공개를 거르지 않는다(조회하는 쪽이 거른다) — 뷰에 대해서는 확정·재사용 범위만 본다
        view_exposed = [item for item in _exposed(connection, view)
                        if item["status"] != "confirmed" or item["reuse_scope"] == "unknown"]
        paths = [{"경로": "뷰 v_image_recommendable", "나온 그림": len(view), "노출": view_exposed},
                 {"경로": "추천용 목록(/api/images/recommendable)", "나온 그림": len(listed), "노출": _exposed(connection, listed)},
                 {"경로": "추천 후보(/api/recommend/images)", "나온 그림": len(candidates), "노출": _exposed(connection, candidates)}]
        required = {"전체": _required(connection, "true"), "기관 확정": _required(connection, "r.status = 'confirmed'")}
    exposed = sum(len(path["노출"]) for path in paths)
    return {"건수": dict(counts), "필수 항목": required, "추천 노출": {"경로별": paths, "노출": exposed},
            "판정": {"추천 노출 0건": exposed == 0,
                     "필수 항목 99.5%(기관 확정)": None if required["기관 확정"]["충족률"] is None else required["기관 확정"]["충족률"] >= 0.995}}


def text_report(result: dict) -> str:
    def percent(value: float | None) -> str:
        return "—" if value is None else f"{value * 100:.1f}%"

    lines = ["[건수] " + " · ".join(f"{name} {count}" for name, count in result["건수"].items())]
    for scope, found in result["필수 항목"].items():
        lines.append(f"[필수 항목 — {scope}] 그림 {found['그림']}개, 따진 항목 {found['따진 항목']}개 중 {found['채워진 항목']}개 충족 = {percent(found['충족률'])}")
        lines += [f"    {item['항목']}: {item['충족']}/{item['해당']} ({percent(item['충족률'])})" for item in found["항목별"] if item["해당"]]
    lines.append(f"[추천 노출] 나오면 안 되는 그림 {result['추천 노출']['노출']}건")
    lines += [f"    {path['경로']}: 나온 그림 {path['나온 그림']}개, 노출 {len(path['노출'])}건" for path in result["추천 노출"]["경로별"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="이미지 저작권 DB 점검 — 필수 항목 충족률과 추천 노출(REQ-02-010 검증 기준)")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL이 필요합니다(.env)", file=sys.stderr)
        return 2
    result = audit(dsn)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else text_report(result))
    return 0 if result["판정"]["추천 노출 0건"] else 1


if __name__ == "__main__":
    sys.exit(main())
