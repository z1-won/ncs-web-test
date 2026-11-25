"""후보 그림에 점수를 매겨 순서를 정하고, 집필자가 봐야 할 권리·출처·화질 안내를 붙인다.

점수(높을수록 앞):
  핵심어가 그림의 키워드에 있으면 3, 제목·캡션에 있으면 2, 그림 사용 문장에 있으면 1 — 핵심어마다 가장 높은 것 하나.
  앞 순위 핵심어일수록 조금 더 쳐 준다(첫 핵심어 ×1.0 … 마지막 ×0.6).
  수행준거 연결: 같은 능력단위 1, 같은 능력단위요소 2, 같은 수행준거 3 — 가산점일 뿐, 연결해 둔 그림만 나오게 하지는 않는다.
  후보 대부분(80% 이상, 후보 8장부터)에 맞는 핵심어는 그림을 가려 주지 못한다 — 점수를 1/4만 치고, 그것만 맞은 그림은 추천하지 않는다
    (같은 호텔 사진 8장에 '호텔'이 모두 맞는 경우). 다만 그렇게 해서 추천이 하나도 없으면 그 그림들을 그대로 보여 준다.
  그림 유사도(그림 임베딩이 켜져 있을 때): 문맥과 그림의 코사인 유사도에서 두 가지 바탕을 뺀 값(σ)으로 본다.
    ① 그림의 바탕 — 그 그림이 **관련 없는 글들**(embed.REFERENCE_TEXTS)과 닮은 정도의 중앙값. 무슨 글에나 닮게 나오는 그림을 거른다.
    ② 글의 바탕 — 후보(5장부터)들의 ①을 뺀 값의 중앙값(0보다 클 때만). 후보 대부분에 고르게 닮는 글('호텔 경영 전략'과 호텔 사진들)을 거른다.
    단위(σ)는 후보 그림들의 바탕 퍼짐의 중앙값이다 — 모델마다 유사도 크기가 달라도 같은 문턱을 쓰기 위한 것.
    σ 1.5 이하는 0, 3.0 이상은 1로 고쳐 ×6. 맞는 그림이 하나도 없으면 아무도 점수를 받지 않는다.
    문턱은 2026-11-20에 SigLIP 2(so400m-patch16-256), 공공누리 호텔 사진 8장, 점검 문장 29개로 맞춘 값이다(docs/RECOMMEND.md).
    그림마다 제 퍼짐으로 나누지 않는다 — 그렇게 하면 바탕이 고른 그림이 부풀려져 순서가 뒤집힌다(같은 자료에서 확인).
  핵심어도 연결도 맞지 않는 그림은, 그림 유사도가 뚜렷이 높을 때(0.5 이상, σ 2.25부터)만 추천한다.
  정부 귀속 + 전체 재사용 자산은 +1 — 비슷하게 맞는 그림 가운데서는 이것이 앞에 온다
  (원고 집필 계약서 제12조, 사진·삽화 제작 계약서 제11조. 관련이 훨씬 높은 다른 그림을 밀어내지는 않는다).

2026-11-23에 더한 것(모두 signals로 켜고 끌 수 있다 — 정답 세트로 방식별 효과를 견주기 위해. scripts/probe/recommend_compare.py):
  alias     지점(context.Point)의 '다른 이름'이 그림의 글에 있으면 같은 칸 점수의 0.7배. 문단에 없는 넓힌 말이라 낮게 친다.
  describe  그림 설명(image_descriptions — 그림을 글로 풀어 둔 것)의 핵심어·대상 이름·그림 속 글자에 있으면 2
            (사람이 단 키워드 3보다 낮다 — 모델이 쓴 것이라 틀릴 수 있다).
  points    그림 유사도를 요약 한 줄이 아니라 지점의 짧은 묘사마다 따로 재고, 그림마다 가장 높은 것을 쓴다.
  kind      가장 잘 맞은 지점이 바라는 그림 종류와 그림의 종류가 같으면 +0.5.
  fusion    'sum'(기본, 위 점수를 더함) / 'rrf'(글·연결·그림 유사도의 순위를 따로 내어 1/(60+순위)를 더함 — 손으로 정한 가중치에
            덜 기댄다). 어느 쪽이 나은지는 재 본 뒤 정한다. 추천할지 말지(qualified)의 기준은 두 방식이 같다.
"""

import re

from .context import Context, squash
from .embed import cosine

KEYWORD_POINTS = (("keywords", 3.0), ("titles", 2.0), ("described", 2.0), ("contexts", 1.0))
ALIAS_FACTOR = 0.7           # 지점의 '다른 이름'(문단에 없는 넓힌 말)이 맞았을 때 곱하는 값
KIND_BONUS = 0.5             # 지점이 바라는 그림 종류와 그림의 종류가 같을 때
RRF_K = 60                   # 순위 융합의 상수(Cormack 외 2009의 관례값)
SIGNALS = frozenset({"keyword", "alias", "describe", "link", "visual", "points", "kind"})
PRIORITY_BONUS = 1.0
PRINT_DPI = 300
LOW_WIDTH_MM = 40            # 300dpi로 가로 40mm도 못 싣는 그림(약 470px 미만)은 '화질 낮음'
CONDITION_NAMES = (("attribution", "출처표시"), ("non_commercial", "상업적 이용금지"), ("no_derivatives", "변경금지"),
                   ("share_alike", "동일조건 변경허락"))
AI_GUIDANCE = (
    "맞는 그림이 없거나 화질이 낮으면 생성형 AI로 새로 만들거나 수정 보완할 수 있습니다(REQ-02-006).",
    "그렇게 만든 그림에는 「AI 도구 사용 표기 예」(2026. 9.)에 따라 그림 아래에 AI 활용 표기를 넣어야 합니다.",
    "「생성형 AI 결과물 집필자 서약서」의 결과물 현황(결과물명·쪽수·활용 AI)에도 올려야 합니다 — 권리 증빙 점검에서 대조합니다.",
)


def unit_base(code) -> str:
    """'LM1203020201_24v3'·'1203020201' → '1203020201'(능력단위 숫자 10자리). 꼴이 다르면 빈 글."""
    found = re.search(r"\d{10}", str(code or ""))
    return found.group(0) if found else ""


def _element_no(code) -> str:
    """'1203020201_24v3.1' → '1'."""
    return str(code or "").rpartition(".")[2] if "." in str(code or "") else ""


def _link_level(links: list[dict], unit: str, criterion_no: str) -> str:
    """가장 가깝게 맞는 연결: 'criterion' > 'element' > 'unit' > ''."""
    level = ""
    element = criterion_no.split(".")[0] if criterion_no else ""
    for link in links or []:
        if not unit or unit_base(link.get("unit_code")) != unit:
            continue
        if criterion_no and str(link.get("criterion_no") or "") == criterion_no:
            return "criterion"
        if element and _element_no(link.get("element_code")) == element:
            level = "element"
        elif not level:
            level = "unit"
    return level


LINK_POINTS = {"": 0.0, "unit": 1.0, "element": 2.0, "criterion": 3.0}
VISUAL_WEIGHT = 6.0
VISUAL_ALONE = 0.5           # 핵심어·연결이 하나도 안 맞아도 이만큼 그림이 닮았으면 추천한다
VISUAL_MIN_REFS = 8          # 바탕으로 삼을 '관련 없는 글'이 이보다 적으면 그림 유사도를 쓰지 않는다
VISUAL_Z_MIN, VISUAL_Z_FULL = 1.5, 3.0   # σ가 이 사이에서 0 → 1. 실제 벡터로 맞춘 값(위 설명)
VISUAL_SPREAD_FLOOR = 0.005  # 바탕의 퍼짐이 0에 가까울 때 σ가 터지지 않게 하는 바닥
VISUAL_POOL_MIN = 5          # 후보가 이보다 적으면 '글의 바탕'(후보 중앙값)을 빼지 않는다
COMMON_MIN_POOL = 8          # 후보가 이보다 적으면 '흔한 핵심어'를 따지지 않는다(비율이 너무 성기다)
COMMON_SHARE = 0.8           # 후보의 이 비율 이상에 맞는 핵심어는 흔한 핵심어
COMMON_FACTOR = 0.25


def conditions(row: dict) -> list[str]:
    return [name for key, name in CONDITION_NAMES if row.get(key)]


def _notes(row: dict) -> list[str]:
    notes = []
    if row.get("kogl_ai"):
        notes.append(f"AI유형이 함께 표시돼 있지만 그것은 AI 학습 목적에만 해당합니다. 원고에 싣는 데는 제{row.get('kogl_type')}유형 조건이 그대로 적용됩니다.")
    if row.get("license_scheme") == "kogl" and row.get("kogl_type") == 0:
        notes.append("제0유형은 공공누리상 출처표시 의무가 없지만, 원고에는 계약서 제4조에 따라 출처를 적습니다.")
    if row.get("non_commercial"):
        notes.append("상업적 이용금지 조건이 있습니다 — 학습모듈의 배포·판매 방식에 맞는지 확인하세요.")
    if row.get("no_derivatives"):
        notes.append("변경금지 조건이 있습니다 — 자르기·합성·색 보정 없이 원본 그대로 실어야 합니다.")
    return notes


def describe(row: dict) -> dict:
    """후보 1건에 집필자가 볼 안내를 붙인다(점수와 무관한 부분)."""
    width = row.get("upscaled_width_px") or row.get("width_px")
    max_width_mm = round(width / PRINT_DPI * 25.4) if width else None
    credit = (row.get("credit_line") or "").strip()
    return {
        "priority": row.get("ownership") == "government" and row.get("reuse_scope") == "all",
        # 이용허락 한정 자산은 '범위 확인 필요'로 표시한다
        "scope_check_needed": row.get("ownership") == "licensed" or row.get("reuse_scope") == "module_only",
        "conditions": conditions(row),
        "notes": _notes(row),
        "credit": f"출처: {credit}" if credit else None,
        "credit_note": "" if credit else "출처 문구가 DB에 없습니다 — 이미지 저작권 DB에서 출처를 채운 뒤 쓰세요.",
        "max_width_mm": max_width_mm,
        "low_quality": max_width_mm is not None and max_width_mm < LOW_WIDTH_MM,
    }


def _fields(row: dict, signals: frozenset = SIGNALS) -> dict[str, list[str]]:
    """그림의 글을 칸별로(squash한 꼴). 'describe'가 꺼져 있으면 그림 설명 칸은 비운다."""
    return {"keywords": [squash(k) for k in row.get("keywords") or []],
            "titles": [squash(t) for t in [row.get("title"), *(row.get("captions") or [])] if t],
            "described": [squash(t) for t in row.get("described_terms") or [] if t] if "describe" in signals else [],
            "contexts": [squash(t) for t in row.get("contexts") or [] if t]}


def _field_points(word: str, fields: dict[str, list[str]]) -> tuple[float, str]:
    """낱말이 맞은 칸 가운데 가장 높은 것의 (점수, 칸 이름). 안 맞으면 (0, '')."""
    key = squash(word)
    if len(key) < 2:
        return 0.0, ""
    for name, value in KEYWORD_POINTS:
        if any(key in text or (len(text) >= 2 and text in key) for text in fields[name]):
            return value, name
    return 0.0, ""


def _keyword_hits(row: dict, context: Context, signals: frozenset = SIGNALS) -> list[tuple[str, float, str]]:
    """[(핵심어, 점수, 맞은 칸)] — 핵심어마다 가장 높은 칸 하나, 앞 순위 핵심어일수록 더 쳐 준다."""
    fields = _fields(row, signals)
    hits = []
    count = len(context.keywords)
    for position, keyword in enumerate(context.keywords):
        points, name = _field_points(keyword, fields)
        if points:
            hits.append((keyword, points * (1.0 - 0.4 * position / max(count - 1, 1)), name))
    return hits


def keyword_hits(row: dict, context: Context, signals: frozenset = SIGNALS) -> list[tuple[str, float]]:
    """그 그림에 맞은 핵심어와 점수 — 핵심어마다 가장 높은 칸 하나, 앞 순위 핵심어일수록 더 쳐 준다."""
    return [(keyword, points) for keyword, points, _ in _keyword_hits(row, context, signals)]


def alias_hits(row: dict, context: Context, signals: frozenset = SIGNALS) -> list[tuple[str, float, int]]:
    """[(다른 이름, 점수, 지점 순번)] — 지점의 '다른 이름'이 그림의 글에 있을 때. **지점마다 가장 높은 것 하나만** 친다:
    한 지점의 다른 이름들은 같은 대상을 가리키는 말이라(프런트 데스크, 프런트) 여럿이 맞아도 근거는 하나다. 같은 말은 한 번만(먼저 나온 지점)."""
    fields = _fields(row, signals)
    hits, seen = [], set()
    for index, point in enumerate(context.points):
        best = None
        for alias in point.aliases:
            key = squash(alias)
            if key in seen:
                continue
            points, _ = _field_points(alias, fields)
            if points and (best is None or points > best[1]):
                best = (alias, points, key)
        if best is not None:
            seen.add(best[2])
            hits.append((best[0], best[1] * ALIAS_FACTOR, index))
    return hits


def common_keywords(hits: list[list[tuple[str, float]]]) -> set[str]:
    """후보 대부분에 맞아 그림을 가려 주지 못하는 핵심어. 후보가 적으면 따지지 않는다."""
    if len(hits) < COMMON_MIN_POOL:
        return set()
    counts: dict[str, int] = {}
    for row_hits in hits:
        for keyword, _ in row_hits:
            counts[keyword] = counts.get(keyword, 0) + 1
    return {keyword for keyword, count in counts.items() if count / len(hits) >= COMMON_SHARE}


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def visual_scores(candidates: list[dict], query_vector: list[float] | None,
                  reference_vectors: list[list[float]] | None = None) -> dict[int, tuple[float, float, float]]:
    """후보 순번 → (코사인 유사도, σ, 가산 비율 0~1). 벡터가 없는 후보는 빠진다. 바탕 글이 모자라면 빈 dict.

    σ = (유사도 − 그림의 바탕 − 글의 바탕) ÷ 단위.
      그림의 바탕: 그 그림이 관련 없는 글들과 닮은 정도의 중앙값(하나가 우연히 맞아도 흔들리지 않게 중앙값).
      글의 바탕: 후보들의 (유사도 − 그림의 바탕)의 중앙값, 0보다 클 때만. 후보가 VISUAL_POOL_MIN장 미만이면 0.
      단위: 후보 그림들의 바탕 퍼짐(MAD)의 중앙값 — 그림마다 다른 값으로 나누지 않는다.
    """
    references = [vector for vector in reference_vectors or [] if vector]
    if not query_vector or len(references) < VISUAL_MIN_REFS:
        return {}
    centered: dict[int, tuple[float, float]] = {}
    spreads = []
    for index, row in enumerate(candidates):
        similarity = cosine(row.get("vector"), query_vector)
        if similarity is None:
            continue
        base = [value for reference in references if (value := cosine(row["vector"], reference)) is not None]
        if len(base) < VISUAL_MIN_REFS:
            continue
        middle = _median(base)
        spreads.append(1.4826 * _median([abs(value - middle) for value in base]))
        centered[index] = (similarity, similarity - middle)
    if not centered:
        return {}
    unit = max(_median(spreads), VISUAL_SPREAD_FLOOR)
    level = max(0.0, _median([value for _, value in centered.values()])) if len(centered) >= VISUAL_POOL_MIN else 0.0
    scores = {}
    for index, (similarity, value) in centered.items():
        z = (value - level) / unit
        scores[index] = (similarity, z, min(1.0, max(0.0, (z - VISUAL_Z_MIN) / (VISUAL_Z_FULL - VISUAL_Z_MIN))))
    return scores


def _best_visual(candidates: list[dict], queries: list[tuple[int | None, list[float]]],
                 reference_vectors: list[list[float]] | None) -> dict[int, tuple[float, float, float, int | None]]:
    """글 여러 개(요약, 지점 묘사들)로 그림 유사도를 따로 재어 그림마다 가장 높은 것 — 후보 순번 → (유사도, σ, 가산 비율, 지점 순번|None)."""
    best: dict[int, tuple[float, float, float, int | None]] = {}
    for origin, vector in queries:
        for index, (similarity, z, position) in visual_scores(candidates, vector, reference_vectors).items():
            if index not in best or (position, z) > (best[index][2], best[index][1]):
                best[index] = (similarity, z, position, origin)
    return best


def _positions(values: dict[int, float]) -> dict[int, int]:
    """값이 0보다 큰 것만 높은 순으로 1위부터 — 값이 같으면 같은 순위."""
    order: dict[int, int] = {}
    last, place = None, 0
    for count, (index, value) in enumerate(sorted(((i, v) for i, v in values.items() if v > 0), key=lambda item: -item[1]), 1):
        if value != last:
            last, place = value, count
        order[index] = place
    return order


def rank(candidates: list[dict], context: Context, *, unit_code: str = "", criterion_no: str = "", limit: int = 10,
         query_vector: list[float] | None = None, reference_vectors: list[list[float]] | None = None,
         point_vectors: list[list[float] | None] | None = None, signals=SIGNALS, fusion: str = "sum") -> list[dict]:
    """관련 있는 후보만 점수순으로. 각 항목은 후보의 값 + describe() + score·matched·common·link_level·similarity·visual_z·visual
    + matched_alias(맞은 '다른 이름')·described_matched(그림 설명에서 맞은 핵심어)·point(가장 잘 맞은 지점 순번|None)·kind_match.

    query_vector: 문맥(요약·핵심어)의 임베딩. 후보의 'vector'(그림 임베딩)와 견준다. 없으면 핵심어·연결로만 한다.
    point_vectors: context.points와 같은 순서의 지점 묘사 임베딩(없는 지점은 None). 'points' 신호가 켜져 있으면 요약과 함께 견주어 가장 높은 것을 쓴다.
    reference_vectors: 관련 없는 글들의 임베딩(embed.reference_vectors). 그림 유사도의 바탕 — 없으면 그림 유사도를 쓰지 않는다.
    signals: 쓸 신호(SIGNALS의 부분집합). fusion: 'sum' | 'rrf'(모듈 머리 설명).
    """
    signals = frozenset(signals)
    if fusion not in ("sum", "rrf"):
        raise ValueError(f"fusion은 sum 또는 rrf입니다: {fusion}")
    unit = unit_base(unit_code)
    criterion_no = (criterion_no or "").strip()
    hits = [_keyword_hits(row, context, signals) if "keyword" in signals else [] for row in candidates]
    aliases = [alias_hits(row, context, signals) if "alias" in signals else [] for row in candidates]
    common = common_keywords([[(word, points) for word, points, _ in found] + [(word, points) for word, points, _ in extra]
                              for found, extra in zip(hits, aliases)])
    queries: list[tuple[int | None, list[float]]] = []
    if "visual" in signals:
        if query_vector:
            queries.append((None, query_vector))
        if "points" in signals:
            queries += [(index, vector) for index, vector in enumerate(point_vectors or []) if vector and index < len(context.points)]
    visual = _best_visual(candidates, queries, reference_vectors)
    entries = []
    for index, row in enumerate(candidates):
        level = _link_level(row.get("links") or [], unit, criterion_no) if "link" in signals else ""
        words = [(word, points) for word, points, _ in hits[index]] + [(word, points) for word, points, _ in aliases[index]]
        distinct = sum(points for word, points in words if word not in common)
        shared = COMMON_FACTOR * sum(points for word, points in words if word in common)
        similarity, z, position, origin = visual.get(index, (None, None, 0.0, None))
        # 가장 잘 맞은 지점: 그림 유사도가 지점 묘사에서 나왔으면 그 지점, 아니면 낱말(문단 속 낱말 → 다른 이름)이 맞은 첫 지점
        point = origin if position > 0 and origin is not None else None
        if point is None:
            matched_keys = {squash(word) for word, _, _ in hits[index]}
            point = next((n for n, item in enumerate(context.points) if any(squash(term) in matched_keys for term in item.terms)), None)
        if point is None and aliases[index]:
            point = aliases[index][0][2]
        kind_match = bool("kind" in signals and point is not None and context.points[point].kind
                          and context.points[point].kind == row.get("kind"))
        qualified = distinct > 0 or bool(level) or position >= VISUAL_ALONE
        entries.append({"index": index, "qualified": qualified, "text": distinct + shared, "link": LINK_POINTS[level], "level": level,
                        "similarity": similarity, "z": z, "position": position, "point": point, "kind_match": kind_match})
    # 흔한 핵심어만 맞은 그림은 빼되, 그래서 하나도 안 남으면 그 그림들을 보여 준다(같은 종류의 그림만 든 작은 DB)
    chosen = [entry for entry in entries if entry["qualified"]] or [entry for entry in entries if entry["text"] + entry["link"] > 0]
    if fusion == "rrf":
        orders = [_positions({entry["index"]: entry[name] for entry in chosen}) for name in ("text", "link", "position")]
    ranked = []
    for entry in chosen:
        index = entry["index"]
        row = candidates[index]
        extra = describe(row)
        bonus = (PRIORITY_BONUS if extra["priority"] else 0.0) + (KIND_BONUS if entry["kind_match"] else 0.0)
        if fusion == "rrf":
            # 순위 융합 점수(×1000)에 정부 귀속·종류 일치를 조금만 더한다 — 이웃한 순위를 뒤집을 만큼만(0.3배)
            final = 1000 * sum(1.0 / (RRF_K + order[index]) for order in orders if index in order) + 0.3 * bonus
        else:
            final = entry["text"] + entry["link"] + VISUAL_WEIGHT * entry["position"] + bonus
        item = {key: value for key, value in row.items() if key != "vector"}
        matched = [word for word, _, _ in hits[index]]
        matched_alias = [word for word, _, _ in aliases[index]]
        similarity, z = entry["similarity"], entry["z"]
        ranked.append({**item, **extra, "score": round(final, 2), "matched": matched, "matched_alias": matched_alias,
                       "described_matched": [word for word, _, name in hits[index] if name == "described"],
                       "common": [word for word in [*matched, *matched_alias] if word in common], "link_level": entry["level"],
                       "point": entry["point"], "kind_match": entry["kind_match"],
                       "similarity": None if similarity is None else round(similarity, 4),
                       "visual_z": None if z is None else round(max(-99.0, min(99.0, z)), 2),
                       "visual": round(entry["position"], 2) if similarity is not None else None})
    ranked.sort(key=lambda item: (-item["score"], not item["priority"], item["low_quality"], str(item.get("id"))))
    return ranked[:limit]


def guidance(items: list[dict]) -> list[str]:
    """추천할 그림이 없거나 모두 화질이 낮을 때의 안내(AI 생성·수정 보완으로 연계). 아니면 빈 목록."""
    if not items:
        return ["조건에 맞는 그림이 이미지 저작권 DB에 없습니다.", *AI_GUIDANCE]
    if all(item["low_quality"] for item in items):
        return ["추천된 그림이 모두 화질이 낮습니다.", *AI_GUIDANCE]
    return []
