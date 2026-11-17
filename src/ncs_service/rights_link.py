"""권리 증빙 점검(ncs_rights) 결과를 이미지 저작권 DB에 잇는다 — REQ-02-014 '확인된 증빙은 이미지 저작권 DB(REQ-02-010)에 연결'.

점검 결과의 그림을 원고(hwpx)의 그림 파일과 캡션으로 짝지어:
  1. 그림 파일·수록 위치·(목록의 제작 방식에서 온) 분류·AI 표기를 이미지 레코드로 적재한다(image_db.load_records —
     이미 있는 그림은 합치고, 기관이 확정한 권리 정보는 건드리지 않는다)
  2. 현황표에서 '제출'로 확인된 증빙을 그 그림에 잇는다(image_store.add_evidence — 같은 증빙은 한 번만)
캡션으로 그림 파일을 찾지 못한 그림(그림 개체가 없거나 hwp 원고)은 건너뛰고 그 수를 알려 준다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.figures import parse_label
from ncs_core.pictures import picture_records

from . import image_db, image_store

EVIDENCE_KINDS = {"양도 동의서(집필자)": "transfer_consent", "양도 동의서(제작자)": "transfer_consent",
                  "이용허락 동의서": "license_consent", "초상권 동의서": "portrait_consent", "AI 서약서": "ai_pledge"}
CATEGORIES = ("author_made", "commissioned", "public_license", "blanket_license", "prior_module")


def _label(caption: str) -> str:
    found = parse_label(caption)
    return f"그림 {found[0]}-{found[1] if found[1] is not None else ''}" if found else ""


def save_to_image_db(dsn: str, manuscript: str | Path, module_code: str, report: dict, *, by: str,
                     submitted_on: date | None = None) -> dict:
    """→ {'그림': 적재한 그림 수, '새 그림', '증빙': 새로 이은 증빙 수, '건너뜀': 그림 파일을 찾지 못한 그림 수, '거부': […]}."""
    document = load_document(manuscript)
    pictures = {}
    for record in picture_records(document):
        label = _label(record["caption"])
        if label and record["data"] and label not in pictures:
            pictures[label] = record
    records, evidence, skipped = [], [], 0
    for row in report["현황표"]:
        picture = pictures.get(row["그림 번호"]) if row["원고"] else None
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
