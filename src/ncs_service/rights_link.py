"""권리 증빙 점검(ncs_rights) 결과를 이미지 저작권 DB에 잇는다 — REQ-02-014 '확인된 증빙은 이미지 저작권 DB(REQ-02-010)에 연결'.

점검 결과의 그림을 원고(hwpx)의 그림 파일과 자리로 짝지어(캡션 문단 바로 위, 앞 캡션보다 아래에 놓인 그림 파일):
  1. 그림 파일·수록 위치·(목록의 제작 방식에서 온) 분류·AI 표기를 이미지 레코드로 적재한다(image_db.load_records —
     이미 있는 그림은 합치고, 기관이 확정한 권리 정보는 건드리지 않는다)
  2. 현황표에서 '제출'로 확인된 증빙을 그 그림에 잇는다(image_store.add_evidence — 같은 증빙은 한 번만)
그림 파일을 찾지 못한 그림(캡션 위에 그림 개체가 없거나 hwp 원고)은 건너뛰고 그 수를 알려 준다.
그림 번호로 짝짓지 않는 것은 실제 원고에 같은 번호가 두 번 쓰이거나 뒤 번호가 빈 캡션('그림 1-')이 여럿 있어서다 —
번호로 찾으면 서로 다른 그림의 수록 위치와 권리 정보가 한 그림 파일에 붙는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.pictures import MAX_CAPTION_GAP, picture_records, pictures_by_caption

from . import image_db, image_store

EVIDENCE_KINDS = {"양도 동의서(집필자)": "transfer_consent", "양도 동의서(제작자)": "transfer_consent",
                  "이용허락 동의서": "license_consent", "초상권 동의서": "portrait_consent", "AI 서약서": "ai_pledge"}
CATEGORIES = ("author_made", "commissioned", "public_license", "blanket_license", "prior_module")


MAX_GAP = MAX_CAPTION_GAP        # 그림과 캡션 사이에 올 수 있는 문단 수 — 짝짓기는 ncs_core.pictures.pictures_by_caption으로 옮겼다


def _pictures_by_caption(document, rows: list[dict]) -> dict[tuple[int, int], dict]:
    """현황표 줄의 캡션 자리 (구역, 문단) → 그 캡션의 그림 파일. 캡션 하나에 그림이 여럿이면 캡션에 가장 가까운 것."""
    return pictures_by_caption(picture_records(document), [tuple(row["문단"]) for row in rows if row.get("문단")])


def _page(row: dict) -> int | None:
    """현황표의 쪽(출력본 PDF를 함께 올렸을 때만 있음) → 수록 위치의 쪽. 한 쪽으로 정해지고 숫자일 때만."""
    folios = row.get("쪽 번호") or []
    return int(folios[0]) if len(folios) == 1 and str(folios[0]).isdigit() else None


def save_to_image_db(dsn: str, manuscript: str | Path, module_code: str, report: dict, *, by: str,
                     submitted_on: date | None = None) -> dict:
    """→ {'그림': 적재한 그림 수, '새 그림', '증빙': 새로 이은 증빙 수, '건너뜀': 그림 파일을 찾지 못한 그림 수, '거부': […]}."""
    pictures = _pictures_by_caption(load_document(manuscript), report["현황표"])
    records, evidence, skipped = [], [], 0
    for row in report["현황표"]:
        picture = pictures.get(tuple(row["문단"])) if row["원고"] and row.get("문단") else None
        if picture is None:
            skipped += bool(row["원고"])
            continue
        rights = {}
        primary = [code for code in row["방식 코드"] if code in CATEGORIES]
        if len(primary) == 1:
            rights["category"] = primary[0]
        if row["AI 방식"]:
            rights["ai"] = {"mode": row["AI 방식"], "tool": row["AI 도구"], "date": row["AI 일자"]}
        records.append({
            "content": picture["data"], "title": row["그림명"] or None,
            "placements": [{"module_code": module_code, "label": row["그림 번호"], "caption": row["그림명"] or None,
                            "source_line": row["출처 줄"] or None, "para_index": picture["para"],
                            "page": _page(row),
                            "width_mm": picture["mm"][0] or None, "height_mm": picture["mm"][1] or None}],
            **({"rights": rights} if rights else {}),
        })
        evidence.append([(EVIDENCE_KINDS[item["증빙"]], item["근거"] or None) for item in row["증빙"]
                         if item["상태"] == "제출" and item["증빙"] in EVIDENCE_KINDS])
    loaded = image_db.load_records(dsn, records, changed_by=by)
    rejected = {item["index"] for item in loaded.rejected}
    added = 0
    for index, (record, items) in enumerate(zip(records, evidence)):
        if index in rejected:
            continue
        sha256 = image_db.normalize(record).asset["sha256"]
        for kind, file_ref in dict.fromkeys(items):
            added += image_store.add_evidence(dsn, sha256, kind, by=by, file_ref=file_ref, submitted_on=submitted_on,
                                              note="권리 증빙 점검에서 확인")
    return {"그림": loaded.accepted, "새 그림": loaded.created, "증빙": added, "건너뜀": skipped, "거부": loaded.rejected}
