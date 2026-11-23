"""화질 보정(업스케일)한 그림을 이미지 저작권 DB에 올린다 — REQ-02-006 ② 'AI 수정 보완'의 결과를 REQ-02-010의 AI 기준 필드에 잇는다.

그림 파일(원본)과 업스케일본, 수록 위치(모듈 코드·그림 번호·캡션·출처 줄), AI 활용 정보를 이미지 레코드로 만들어 적재한다
(image_db.load_records — 이미 있는 그림은 합치고, 기관이 확정한 권리 정보는 건드리지 않는다. 업스케일본은 아직 없을 때만 들어간다).
AI 활용 정보: 활용 유형 3(기존 이미지 보정, 수정 보완), 도구(업스케일 모델), 일자, 원본 출처(원고의 출처 줄).
캡션을 찾지 못한 그림은 어느 그림인지 적을 수 없어 건너뛰고 그 수를 알려 준다. 분류 체계와 재사용 범위는 정하지 않는다(기관이 확정한다).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.figures import SOURCE, manuscript_figures
from ncs_core.pictures import picture_records, pictures_by_caption

from . import image_db

AI_USAGE_ADJUST = 3      # AI 도구 사용 표기 예 3: 기존 이미지 보정(image_terms.AI_USAGE)


def register_upscaled(dsn: str, manuscript: str | Path, work: str | Path, module_code: str, *, by: str, on: date,
                      target_dpi: int | None = None) -> dict:
    """→ {'그림': 적재한 그림 수, '새 그림', '확정 유지': 권리 정보를 그대로 둔 그림 수, '캡션 없음': [bin_id…], '거부': […]}."""
    from ncs_upscale import service as upscale

    document = load_document(manuscript)
    figures = manuscript_figures(document)
    paired = pictures_by_caption(picture_records(document), [(figure.section, figure.para) for figure in figures])
    by_place = {(figure.section, figure.para): figure for figure in figures}
    places: dict[str, list[tuple]] = {}
    for spot, record in sorted(paired.items()):
        places.setdefault(record["bin_id"], []).append((by_place[spot], record))
    records, skipped = [], []
    for info in upscale.finished(Path(work), target_dpi):
        used = places.get(info["bin_id"])
        if not used:
            skipped.append(info["bin_id"])
            continue
        data, _media, _ext = upscale.upscaled_file(Path(work), info["bin_id"])
        first, picture = used[0]
        records.append({
            "content": picture["data"], "title": first.title or None,
            "upscaled": {"content": data, "engine": info.get("engine")},
            "placements": [{"module_code": module_code, "label": figure.label, "caption": figure.title or None,
                            "source_line": figure.source_line or None, "para_index": record["para"],
                            "width_mm": record["mm"][0] or None, "height_mm": record["mm"][1] or None} for figure, record in used],
            "rights": {"ai": {"used": True, "usage": AI_USAGE_ADJUST, "mode": "modified", "tool": upscale.tool_name(info.get("engine")),
                              "date": on.isoformat(), "original_source": SOURCE.sub("", first.source_line).strip() or None}},
        })
    if not records:
        return {"그림": 0, "새 그림": 0, "확정 유지": 0, "캡션 없음": skipped, "거부": []}
    loaded = image_db.load_records(dsn, records, changed_by=by)
    return {"그림": loaded.accepted, "새 그림": loaded.created, "확정 유지": len(loaded.kept_confirmed), "캡션 없음": skipped, "거부": loaded.rejected}
