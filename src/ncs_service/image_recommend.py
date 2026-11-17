"""수행준거 문맥 기반 이미지 추천(REQ-02-011)의 DB 쪽 — 후보를 꺼내 ncs_recommend에 넘긴다.

후보는 v_image_recommendable(기관 확정 + 재사용 범위 확인)에서 비공개를 뺀 것뿐이다. 그래서 권리가 확인되지 않은 그림은
어떤 입력으로도 추천에 나오지 않는다('권리 미확인 이미지 추천 노출 0건'). 그림 파일은 꺼내지 않는다 —
화면은 /api/images/recommendable/{id}/file로 받는다.
"""

import psycopg
from psycopg.rows import dict_row

from ncs_core.ncs_catalog import catalog
from ncs_recommend import context as recommend_context
from ncs_recommend import rank as recommend_rank

from . import kogl_import
from .image_store import RECOMMENDABLE, _row

MAX_CANDIDATES = 5000        # PoC 규모. 넘으면 앞에서부터만 보고 그 사실을 결과에 적는다

CANDIDATES = f"""
SELECT v.*, a.source_id, a.upscaled_width_px, a.upscaled_height_px,
       (SELECT coalesce(array_agg(DISTINCT p.caption) FILTER (WHERE p.caption IS NOT NULL), '{{}}')
          FROM image_placements p WHERE p.image_id = v.id) AS captions,
       (SELECT coalesce(array_agg(DISTINCT p.context_text) FILTER (WHERE p.context_text IS NOT NULL), '{{}}')
          FROM image_placements p WHERE p.image_id = v.id) AS contexts,
       (SELECT coalesce(array_agg(DISTINCT p.module_code), '{{}}') FROM image_placements p WHERE p.image_id = v.id) AS module_codes,
       (SELECT coalesce(jsonb_agg(jsonb_build_object('unit_code', l.unit_code, 'element_code', l.element_code,
                                                     'criterion_no', l.criterion_no)), '[]'::jsonb)
          FROM image_ncs_links l WHERE l.image_id = v.id) AS links
FROM v_image_recommendable v JOIN image_assets a ON a.id = v.id
WHERE {RECOMMENDABLE}
ORDER BY v.confirmed_at DESC, v.id
LIMIT %s
"""


def candidates(dsn: str) -> list[dict]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(CANDIDATES, (MAX_CANDIDATES + 1,)).fetchall()
    out = []
    for row in rows:
        item = _row(row)
        # 공공누리인데 출처 문구가 비어 있으면 URL·검색일·유형으로 만든다(적재 때와 같은 문구)
        if not item.get("credit_line") and item.get("license_scheme") == "kogl" and row.get("source_url") and row.get("retrieved_on"):
            item["credit_line"] = kogl_import.credit_line(row["source_url"], row["retrieved_on"], row["kogl_type"])
        out.append(item)
    return out


def criterion_text(unit_code: str, criterion_no: str) -> tuple[str, str]:
    """(수행준거 글, 능력단위 이름). NCS 목록에 없으면 빈 글 — 그때는 문단만으로 추천한다."""
    found = catalog()
    unit = recommend_rank.unit_base(unit_code)
    detail = found.unit_detail(unit) if found and unit else None
    if not detail:
        return "", ""
    for element in detail["elements"]:
        for text in element["criteria"]:
            number, _, body = text.strip().partition(" ")
            if criterion_no and number == criterion_no:
                return body.strip(), detail.get("name", "")
    return "", detail.get("name", "")


def recommend(dsn: str, *, text: str = "", unit_code: str = "", criterion_no: str = "", limit: int = 10,
              use_llm: bool = True, asker=None) -> dict:
    """문단·수행준거에 맞는 그림 추천. 반환: {'context', 'criterion', 'items', 'total_candidates', 'guidance'}."""
    text, unit_code, criterion_no = (text or "").strip(), (unit_code or "").strip(), (criterion_no or "").strip()
    if not text and not recommend_rank.unit_base(unit_code):
        raise ValueError("문단을 적거나 능력단위 코드를 넣어 주세요")
    if unit_code and not recommend_rank.unit_base(unit_code):
        raise ValueError("능력단위 코드는 숫자 10자리가 들어 있어야 합니다(예: 1203020201, LM1203020201_24v3)")
    criterion, unit_name = criterion_text(unit_code, criterion_no)
    analyzed = recommend_context.analyze(text, criterion, use_llm=use_llm, asker=asker)
    pool = candidates(dsn)
    truncated = len(pool) > MAX_CANDIDATES
    items = recommend_rank.rank(pool[:MAX_CANDIDATES], analyzed, unit_code=unit_code, criterion_no=criterion_no, limit=limit)
    for item in items:           # 화면에 필요 없는 긴 글은 뺀다
        item.pop("contexts", None)
    return {
        "context": {"summary": analyzed.summary, "keywords": analyzed.keywords, "method": analyzed.method,
                    "model": analyzed.model, "note": analyzed.note, "dropped": analyzed.dropped},
        "criterion": {"unit_code": unit_code, "unit_name": unit_name, "criterion_no": criterion_no, "text": criterion,
                      "found": bool(criterion) if criterion_no else bool(unit_name)},
        "items": items,
        "total_candidates": min(len(pool), MAX_CANDIDATES),
        "truncated": truncated,
        "guidance": recommend_rank.guidance(items),
    }
