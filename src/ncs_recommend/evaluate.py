"""추천 평가 — 정답 세트(문단마다 맞는 그림과 등급)로 추천 결과를 잰다(REQ-02-011). DB·모델을 모른다.

정답 세트(JSON, docs/examples/recommend_gold.example.json):
  {"schema": "recommend-gold/0.1", "note": "…",
   "queries": [{"id": "q01", "text": "문단", "unit_code": "", "criterion_no": "",
                "relevant": {"<그림 이름표>": 2, "<그림 이름표>": 1},    # 2 = 딱 맞음, 1 = 관련 있으나 꼭 맞지는 않음
                "no_image": false,                                       # true면 '그림을 권하지 말아야 하는 문단'(relevant는 비운다)
                "note": "낱말이 다름(접수대 ↔ 프런트 데스크)"}]}
그림 이름표는 그림의 id, sha256, source_id(수집 목록의 고유번호 — KOGL-0002), 파일 이름(확장자 없이도) 가운데 아무것이나 쓴다.
등급은 TREC AToMiC의 세 등급(0 무관, 1 관련 있으나 꼭 맞지 않음, 2 잘 맞음)을 따른다. 적지 않은 그림은 0이다.

지표(문단마다, 그리고 평균):
  hit@1·hit@5   1위(5위 안)에 등급 1 이상인 그림이 있는가
  recall@5      맞는 그림(등급 1 이상) 가운데 5위 안에 든 비율
  ndcg@10       등급을 이득(2^등급 − 1)으로 본 순위 품질. 이상적인 순서 대비 0~1
  mrr           처음 맞는 그림의 순위의 역수
  no_image 문단은 위 지표에서 빼고 false_recs(권한 그림 수 — 0이어야 한다)만 센다.
맞는 그림이 추천 후보에 없으면(기관 확정 전, 재사용 범위 미확인) 어떤 방식으로도 찾을 수 없다 — missing으로 따로 알린다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import PurePath

SCHEMA = "recommend-gold/0.1"
GRADES = (1, 2)


class GoldError(ValueError):
    pass


@dataclass(frozen=True)
class Query:
    id: str
    text: str
    unit_code: str = ""
    criterion_no: str = ""
    relevant: dict[str, int] = field(default_factory=dict)     # 그림 이름표(소문자) → 등급
    no_image: bool = False
    note: str = ""


def _key(value) -> str:
    return str(value or "").strip().lower()


def keys_of(item: dict) -> set[str]:
    """그림 1건을 가리킬 수 있는 이름표들 — id, sha256, source_id, 파일 이름(확장자 있는 것과 없는 것)."""
    names = {_key(item.get(name)) for name in ("id", "sha256", "source_id", "filename")}
    if item.get("filename"):
        names.add(_key(PurePath(str(item["filename"])).stem))
    return names - {""}


def load_gold(data) -> list[Query]:
    """정답 세트 JSON → 문단 목록. 형식이 틀리면 GoldError(어디가 틀렸는지 함께)."""
    if not isinstance(data, dict) or not isinstance(data.get("queries"), list):
        raise GoldError('정답 세트는 {"queries": [...]} 꼴이어야 합니다')
    out, seen = [], set()
    for number, raw in enumerate(data["queries"], 1):
        where = f"queries[{number}]"
        if not isinstance(raw, dict):
            raise GoldError(f"{where}: 객체가 아닙니다")
        text, unit = str(raw.get("text") or "").strip(), str(raw.get("unit_code") or "").strip()
        if not text and not unit:
            raise GoldError(f"{where}: text(문단)나 unit_code가 있어야 합니다")
        query_id = str(raw.get("id") or f"q{number:02d}").strip()
        if query_id in seen:
            raise GoldError(f"{where}: id가 겹칩니다({query_id})")
        seen.add(query_id)
        relevant = raw.get("relevant") or {}
        if not isinstance(relevant, dict):
            raise GoldError(f"{where}: relevant는 {{그림 이름표: 등급}} 꼴이어야 합니다")
        grades = {}
        for name, grade in relevant.items():
            if grade not in GRADES or isinstance(grade, bool):
                raise GoldError(f"{where}: 등급은 1 또는 2입니다({name}: {grade!r}). 무관한 그림은 적지 않습니다")
            grades[_key(name)] = int(grade)
        no_image = bool(raw.get("no_image"))
        if no_image and grades:
            raise GoldError(f"{where}: no_image인 문단에는 relevant를 적지 않습니다")
        if not no_image and not grades:
            raise GoldError(f"{where}: 맞는 그림(relevant)이 없으면 no_image를 true로 적습니다")
        out.append(Query(query_id, text, unit, str(raw.get("criterion_no") or "").strip(), grades, no_image, str(raw.get("note") or "")))
    if not out:
        raise GoldError("문단이 하나도 없습니다")
    return out


def grade_of(item: dict, query: Query) -> int:
    return max((query.relevant.get(key, 0) for key in keys_of(item)), default=0)


def missing(query: Query, pool: list[dict]) -> list[str]:
    """정답에 적힌 그림 가운데 추천 후보에 없는 것(이름표 그대로)."""
    known = set().union(*(keys_of(item) for item in pool)) if pool else set()
    return sorted(name for name in query.relevant if name not in known)


def _dcg(grades: list[int]) -> float:
    return sum((2 ** grade - 1) / math.log2(position + 1) for position, grade in enumerate(grades, 1))


def score(query: Query, items: list[dict], pool: list[dict] | None = None) -> dict:
    """문단 하나의 추천 결과(items, 순위 순) → 지표. pool을 주면 후보에 있는 정답만으로 이상적인 순서를 잡는다
    (후보에 없는 그림은 어떤 방식으로도 찾을 수 없으므로 방식 비교에서 뺀다)."""
    grades = [grade_of(item, query) for item in items]
    if query.no_image:
        return {"id": query.id, "no_image": True, "false_recs": len(items), "returned": len(items)}
    reachable = sorted((grade for grade in (grade_of(item, query) for item in pool) if grade), reverse=True) if pool is not None \
        else sorted(query.relevant.values(), reverse=True)
    found_at = next((position for position, grade in enumerate(grades, 1) if grade), None)
    ideal = _dcg(reachable[:10])
    return {"id": query.id, "no_image": False, "returned": len(items), "reachable": len(reachable),
            "hit@1": float(bool(grades[:1] and grades[0])), "hit@5": float(any(grades[:5])),
            "recall@5": (sum(1 for grade in grades[:5] if grade) / len(reachable)) if reachable else None,
            "ndcg@10": (_dcg(grades[:10]) / ideal) if ideal else None,
            "mrr": 1.0 / found_at if found_at else 0.0, "first": found_at}


def summarize(rows: list[dict]) -> dict:
    """문단별 지표 → 평균. 후보에 정답이 하나도 없는 문단(reachable 0)은 평균에서 빼고 수만 센다."""
    judged = [row for row in rows if not row["no_image"] and row.get("reachable")]
    unreachable = sum(1 for row in rows if not row["no_image"] and not row.get("reachable"))
    negatives = [row for row in rows if row["no_image"]]

    def mean(name: str):
        values = [row[name] for row in judged if row.get(name) is not None]
        return round(sum(values) / len(values), 3) if values else None

    return {"queries": len(judged), "unreachable": unreachable,
            "hit@1": mean("hit@1"), "hit@5": mean("hit@5"), "recall@5": mean("recall@5"), "ndcg@10": mean("ndcg@10"), "mrr": mean("mrr"),
            "no_image_queries": len(negatives), "no_image_with_recs": sum(1 for row in negatives if row["false_recs"]),
            "false_recs": sum(row["false_recs"] for row in negatives)}
