"""수행준거 문맥 기반 이미지 추천(REQ-02-011)의 DB 쪽 — 후보를 꺼내 ncs_recommend에 넘긴다.

후보는 v_image_recommendable(기관 확정 + 재사용 범위 확인)에서 비공개를 뺀 것뿐이다. 그래서 권리가 확인되지 않은 그림은
어떤 입력으로도 추천에 나오지 않는다('권리 미확인 이미지 추천 노출 0건'). 그림 파일은 꺼내지 않는다 —
화면은 /api/images/recommendable/{id}/file로 받는다.
"""

import psycopg
from psycopg.rows import dict_row

from ncs_core.ncs_catalog import catalog
from ncs_recommend import context as recommend_context
from ncs_recommend import describe as recommend_describe
from ncs_recommend import embed as recommend_embed
from ncs_recommend import rank as recommend_rank

from . import kogl_import
from .image_store import RECOMMENDABLE, _row

MAX_CANDIDATES = 5000        # PoC 규모. 넘으면 앞에서부터만 보고 그 사실을 결과에 적는다

CANDIDATES = f"""
SELECT v.*, a.source_id, a.upscaled_width_px, a.upscaled_height_px,
       (SELECT e.vector FROM image_embeddings e WHERE e.image_id = v.id AND e.model = %s) AS vector,
       (SELECT coalesce(array_agg(DISTINCT p.caption) FILTER (WHERE p.caption IS NOT NULL), '{{}}')
          FROM image_placements p WHERE p.image_id = v.id) AS captions,
       (SELECT coalesce(array_agg(DISTINCT p.context_text) FILTER (WHERE p.context_text IS NOT NULL), '{{}}')
          FROM image_placements p WHERE p.image_id = v.id) AS contexts,
       (SELECT coalesce(array_agg(DISTINCT p.module_code), '{{}}') FROM image_placements p WHERE p.image_id = v.id) AS module_codes,
       (SELECT coalesce(jsonb_agg(jsonb_build_object('unit_code', l.unit_code, 'element_code', l.element_code,
                                                     'criterion_no', l.criterion_no)), '[]'::jsonb)
          FROM image_ncs_links l WHERE l.image_id = v.id) AS links,
       (SELECT coalesce(jsonb_agg(jsonb_build_object('engine', d.engine, 'kind', d.kind, 'scene', d.scene, 'objects', d.objects,
                                                     'visible_text', d.visible_text, 'keywords', d.keywords,
                                                     'checked', d.checked_by IS NOT NULL)
                                  ORDER BY (d.checked_by IS NOT NULL) DESC, d.created_at DESC), '[]'::jsonb)
          FROM image_descriptions d WHERE d.image_id = v.id) AS descriptions
FROM v_image_recommendable v JOIN image_assets a ON a.id = v.id
WHERE {RECOMMENDABLE}
ORDER BY v.confirmed_at DESC, v.id
LIMIT %s
"""


def waiting(dsn: str) -> dict:
    """추천에 못 나오는 그림 수 — {'unknown_scope': 확정됐지만 재사용 범위 미확인, 'unconfirmed': 아직 확정 전(권리 정보 없음 포함)}."""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        return connection.execute(
            "SELECT count(*) FILTER (WHERE r.status = 'confirmed' AND r.reuse_scope = 'unknown') AS unknown_scope, "
            "count(*) FILTER (WHERE r.status IS DISTINCT FROM 'confirmed') AS unconfirmed "
            "FROM image_assets a LEFT JOIN image_rights r ON r.image_id = a.id").fetchone()


def _no_candidates(dsn: str) -> list[str]:
    counts = waiting(dsn)
    lines = ["추천에 쓸 수 있는 그림이 아직 없습니다. 기관이 확정했고 재사용 범위가 정해진 그림만 추천합니다."]
    if counts["unknown_scope"]:
        lines.append(f"확정됐지만 재사용 범위가 ‘미확인’인 그림이 {counts['unknown_scope']}건 있습니다 — 이미지 저작권 DB에서 그림을 열어 "
                     "‘확정 취소’ → 재사용 범위 선택 → ‘저장하고 기관 확정’을 하면 추천 대상이 됩니다.")
    if counts["unconfirmed"]:
        lines.append(f"아직 확정하지 않은 그림이 {counts['unconfirmed']}건 있습니다 — 이미지 저작권 DB에서 그림을 열어 ‘기관 확정’을 하세요.")
    return lines


def candidates(dsn: str, model: str = "") -> list[dict]:
    """추천 후보. model을 주면 그 모델로 계산해 둔 그림 벡터를 'vector'로 함께 준다(없는 그림은 None)."""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(CANDIDATES, (model, MAX_CANDIDATES + 1)).fetchall()
    out = []
    for row in rows:
        item = _row(row)
        # 공공누리인데 출처 문구가 비어 있으면 URL·검색일·유형으로 만든다(적재 때와 같은 문구)
        if not item.get("credit_line") and item.get("license_scheme") == "kogl" and row.get("source_url") and row.get("retrieved_on"):
            item["credit_line"] = kogl_import.credit_line(row["source_url"], row["retrieved_on"], row["kogl_type"])
        # 그림 설명(설명 색인): 엔진이 여럿이면 낱말은 모두 모으고, 화면에는 사람이 확인한 것 → 최근 것 하나를 보인다
        descriptions = item.pop("descriptions", None) or []
        item["described_terms"] = list(dict.fromkeys(term for one in descriptions for term in recommend_describe.terms(one)))
        item["described"] = ({"engine": descriptions[0]["engine"], "kind": descriptions[0]["kind"], "scene": descriptions[0]["scene"],
                              "checked": descriptions[0]["checked"]} if descriptions else None)
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


def rank_pool(pool: list[dict], analyzed, *, embedder=None, unit_code: str = "", criterion_no: str = "", limit: int = 10,
              signals=recommend_rank.SIGNALS, fusion: str = "sum", vectors: dict | None = None) -> dict:
    """후보(pool)를 문맥(analyzed)으로 줄 세운다 → {'items', 'used', 'model', 'queries', 'covered', 'note'}.

    그림과 견줄 글: 요약(없으면 핵심어) 한 줄 + 지점마다의 짧은 묘사. 모델의 글 길이 상한이 짧아 문단을 통째로 넣지 않는다.
    vectors: 글 → 벡터의 캐시(같은 문단을 방식만 바꿔 여러 번 줄 세울 때 — scripts/probe/recommend_compare.py). 주면 여기에 채운다.
    """
    signals = frozenset(signals)
    covered = sum(1 for row in pool if row.get("vector"))
    summary_text = analyzed.summary or " ".join(analyzed.keywords)
    wanted = "visual" in signals and embedder is not None and covered > 0
    cache = vectors if vectors is not None else {}

    def vector_of(text: str):
        if not text:
            return None
        if text not in cache:
            cache[text] = embedder.text(text)
        return cache[text]

    query_vector = vector_of(summary_text) if wanted else None
    point_vectors = [vector_of(point.description) for point in analyzed.points] if wanted and "points" in signals else []
    has_query = query_vector is not None or any(vector is not None for vector in point_vectors)
    # 그림 유사도의 바탕: 관련 없는 글들의 벡터. 그림마다 이것과 견주어 문맥과 뚜렷이 맞는지 본다(rank.visual_scores)
    reference = recommend_embed.reference_vectors(embedder) if has_query else []
    items = recommend_rank.rank(pool, analyzed, unit_code=unit_code, criterion_no=criterion_no, limit=limit, query_vector=query_vector,
                                reference_vectors=reference, point_vectors=point_vectors, signals=signals, fusion=fusion)
    used = has_query and len(reference) >= recommend_rank.VISUAL_MIN_REFS
    if used:
        note = "" if covered == len(pool) else f"후보 {len(pool)}건 중 {covered}건만 그림 벡터가 있습니다(python -m ncs_service.images.image_embed로 채웁니다)"
    elif "visual" not in signals:
        note = "그림 유사도를 쓰지 않도록 골랐습니다"
    elif embedder is None:
        note = recommend_embed.why_not()
    elif not covered:
        note = "그림 벡터가 아직 없습니다 — python -m ncs_service.images.image_embed로 채웁니다"
    else:
        note = "그림과 견줄 글이 없거나 바탕 글의 벡터를 만들지 못해 그림 유사도를 쓰지 않았습니다"
    queries = [text for text, vector in [(summary_text, query_vector), *zip([point.description for point in analyzed.points], point_vectors)]
               if vector is not None]
    for item in items:           # 화면에 필요 없는 긴 글은 뺀다
        item.pop("contexts", None)
        item.pop("described_terms", None)
    return {"items": items, "used": used, "model": embedder.name if embedder else "", "queries": queries if used else [],
            "covered": covered, "note": note}


def recommend(dsn: str, *, text: str = "", unit_code: str = "", criterion_no: str = "", limit: int = 10,
              use_llm: bool = True, asker=None, embedder=None) -> dict:
    """문단·수행준거에 맞는 그림 추천. 반환: {'context', 'criterion', 'embedding', 'items', 'total_candidates', 'guidance'}.

    embedder: 테스트에서 그림 임베딩 모델 대신 넣는 것(.name, .text(str) → 벡터). 주지 않으면 설정된 모델(꺼져 있으면 쓰지 않음).
    """
    text, unit_code, criterion_no = (text or "").strip(), (unit_code or "").strip(), (criterion_no or "").strip()
    if not text and not recommend_rank.unit_base(unit_code):
        raise ValueError("문단을 적거나 능력단위 코드를 넣어 주세요")
    if unit_code and not recommend_rank.unit_base(unit_code):
        raise ValueError("능력단위 코드는 숫자 10자리가 들어 있어야 합니다(예: 1203020201, LM1203020201_24v3)")
    criterion, unit_name = criterion_text(unit_code, criterion_no)
    analyzed = recommend_context.analyze(text, criterion, use_llm=use_llm, asker=asker)
    embedder = embedder if embedder is not None else recommend_embed.get()
    pool = candidates(dsn, embedder.name if embedder else "")
    truncated = len(pool) > MAX_CANDIDATES
    pool = pool[:MAX_CANDIDATES]
    ranked = rank_pool(pool, analyzed, embedder=embedder, unit_code=unit_code, criterion_no=criterion_no, limit=limit)
    items = ranked["items"]
    guidance = recommend_rank.guidance(items) if pool else _no_candidates(dsn)
    if analyzed.needs_image is False:
        guidance = [f"이 문단은 그림이 꼭 필요해 보이지 않습니다(생성형 AI의 판단: {analyzed.needs_reason or '그림으로 나타낼 대상이 없음'}). "
                    "아래 추천은 참고로만 보세요.", *guidance]
    return {
        "context": {"summary": analyzed.summary, "keywords": analyzed.keywords, "method": analyzed.method,
                    "model": analyzed.model, "note": analyzed.note, "dropped": analyzed.dropped,
                    "points": [point.as_dict() for point in analyzed.points],
                    "needs_image": analyzed.needs_image, "needs_reason": analyzed.needs_reason},
        "criterion": {"unit_code": unit_code, "unit_name": unit_name, "criterion_no": criterion_no, "text": criterion,
                      "found": bool(criterion) if criterion_no else bool(unit_name)},
        "items": items,
        "embedding": {"used": ranked["used"], "model": ranked["model"], "query": " / ".join(ranked["queries"]), "queries": ranked["queries"],
                      "covered": ranked["covered"], "note": ranked["note"]},
        "described": sum(1 for row in pool if row.get("described")),
        "total_candidates": len(pool),
        "truncated": truncated,
        # 후보가 하나도 없으면 '맞는 그림이 없다'가 아니라 '확정된 그림이 없다'가 원인이다 — AI 생성으로 안내하지 않는다
        "guidance": guidance,
    }
