"""이미지 추천 방식 비교 — 정답 세트의 문단마다 방식별 추천을 내고 지표를 나란히 잰다(REQ-02-011).

  set -a; source .env; set +a
  python scripts/probe/recommend_compare.py docs/examples/recommend_gold.example.json --out 결과/추천비교
  python scripts/probe/recommend_compare.py 정답.json --out 결과/추천비교 --no-llm            # 생성형 AI 없이(규칙 핵심어)
  python scripts/probe/recommend_compare.py 정답.json --out 결과/추천비교 --dump 후보.json     # 후보·문맥·벡터를 남겨 두고
  python scripts/probe/recommend_compare.py 정답.json --out 결과/추천비교 --load 후보.json     # DB·모델 없이 같은 자료로 다시(점수 식만 고쳐 볼 때)

정답 세트의 형식과 지표는 ncs_recommend.evaluate. 후보는 추천 화면과 같은 것(v_image_recommendable — 기관 확정 + 재사용 범위 확인)이다.
정답에 적은 그림이 후보에 없으면(확정 전 등) 어떤 방식으로도 찾을 수 없으므로 '후보에 없음'으로 따로 적고 평균에서 뺀다.

견주는 방식(VARIANTS): 신호를 하나씩 더해 가며 무엇이 얼마나 보태는지 본다.
  핵심어+연결 → +다른 이름 → +그림 설명 → +그림 유사도(요약) → +그림 유사도(지점) → 모두(지금 화면) → 모두, 순위 융합
문단마다 생성형 AI 문맥 읽기는 한 번만 하고(방식마다 같은 문맥), 글의 벡터도 한 번만 계산한다.
산출물: <out>/report.md(요약 표 + 문단별 상위 5장), <out>/report.json(모든 수치).
문단을 생성형 AI로 읽으면 문단이 밖으로 나간다(추천 화면과 같은 조건: 키 + LLM_ALLOW_UPLOAD=1). 그림은 보내지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ncs_recommend import context as recommend_context  # noqa: E402
from ncs_recommend import evaluate, rank  # noqa: E402
from ncs_recommend import embed as recommend_embed  # noqa: E402

BASE = frozenset({"keyword", "link"})
VARIANTS = [
    ("핵심어+연결", BASE, "sum"),
    ("+다른 이름", BASE | {"alias"}, "sum"),
    ("+그림 설명", BASE | {"alias", "describe"}, "sum"),
    ("+그림 유사도(요약)", BASE | {"alias", "describe", "visual"}, "sum"),
    ("+그림 유사도(지점)", BASE | {"alias", "describe", "visual", "points"}, "sum"),
    ("모두(지금 화면)", rank.SIGNALS, "sum"),
    ("모두, 순위 융합", rank.SIGNALS, "rrf"),
]
METRICS = ("hit@1", "hit@5", "recall@5", "ndcg@10", "mrr")


class StoredEmbedder:
    """--load로 읽은 벡터만 돌려주는 대역 — 모델 없이 같은 자료로 다시 재기 위한 것. 없는 글은 None(그 글로는 그림 유사도를 재지 않는다)."""

    def __init__(self, name: str, vectors: dict[str, list[float]]):
        self.name, self.vectors = name, vectors

    def text(self, text: str):
        return self.vectors.get(text)


def context_from(saved: dict) -> recommend_context.Context:
    points = [recommend_context.Point(p["description"], p.get("kind", ""), p.get("terms", []), p.get("aliases", [])) for p in saved.get("points", [])]
    return recommend_context.Context(saved.get("summary", ""), saved.get("keywords", []), saved.get("method", "rule"), saved.get("model", ""),
                                     saved.get("note", ""), saved.get("dropped", []), points, saved.get("needs_image"), saved.get("needs_reason", ""))


def context_to(analyzed: recommend_context.Context) -> dict:
    return {"summary": analyzed.summary, "keywords": analyzed.keywords, "method": analyzed.method, "model": analyzed.model, "note": analyzed.note,
            "dropped": analyzed.dropped, "points": [point.as_dict() for point in analyzed.points], "needs_image": analyzed.needs_image,
            "needs_reason": analyzed.needs_reason}


def name_of(item: dict) -> str:
    return str(item.get("source_id") or item.get("filename") or item.get("title") or item.get("id"))


def run(queries: list[evaluate.Query], pool: list[dict], contexts: dict[str, recommend_context.Context], embedder, references, vectors: dict,
        limit: int) -> dict:
    """방식마다 문단별 추천과 지표. image_recommend.rank_pool과 같은 순서로 글의 벡터를 만든다."""
    from ncs_service.images import image_recommend       # DB 드라이버(psycopg)가 있어야 불러진다 — --load만 쓸 때도 같은 함수로 줄 세운다

    recommend_embed._references[getattr(embedder, "name", "")] = references       # 바탕 글의 벡터를 다시 계산하지 않게(저장해 둔 것 포함)
    out = {}
    for label, signals, fusion in VARIANTS:
        rows, started = [], time.perf_counter()
        for query in queries:
            ranked = image_recommend.rank_pool(pool, contexts[query.id], embedder=embedder, unit_code=query.unit_code, criterion_no=query.criterion_no,
                                               limit=limit, signals=signals, fusion=fusion, vectors=vectors)
            row = evaluate.score(query, ranked["items"], pool)
            row["top"] = [{"name": name_of(item), "grade": evaluate.grade_of(item, query), "score": item["score"], "matched": item["matched"],
                           "alias": item["matched_alias"], "described": item["described_matched"], "visual": item["visual"],
                           "point": item["point"]} for item in ranked["items"][:5]]
            rows.append(row)
        out[label] = {"signals": sorted(signals), "fusion": fusion, "summary": evaluate.summarize(rows), "queries": rows,
                      "seconds": round(time.perf_counter() - started, 2)}
    return out


def report(gold_name: str, queries: list[evaluate.Query], pool: list[dict], contexts: dict, results: dict, info: dict) -> str:
    cell = lambda value: "-" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))  # noqa: E731
    lines = [f"# 이미지 추천 방식 비교 — {gold_name}", "",
             f"- 문단 {len(queries)}개(그림을 권하지 말아야 하는 문단 {sum(1 for q in queries if q.no_image)}개), 추천 후보 {len(pool)}건",
             f"- 문맥 읽기: {info['context']}", f"- 그림 임베딩: {info['embedding']}", f"- 그림 설명이 있는 후보: {info['described']}건", ""]
    absent = {query.id: evaluate.missing(query, pool) for query in queries}
    if any(absent.values()):
        lines += ["정답에 적었지만 추천 후보에 없는 그림(기관 확정 전이거나 재사용 범위 미확인 — 평균에서 뺀다):", ""]
        lines += [f"- {query_id}: {', '.join(names)}" for query_id, names in absent.items() if names] + [""]
    lines += ["## 요약", "", "| 방식 | 잰 문단 | " + " | ".join(METRICS) + " | 권하지 말아야 할 문단에서 권한 횟수 |", "|---|---|" + "---|" * (len(METRICS) + 1)]
    for label, result in results.items():
        s = result["summary"]
        lines.append(f"| {label} | {s['queries']} | " + " | ".join(cell(s[name]) for name in METRICS)
                     + f" | {s['no_image_with_recs']}/{s['no_image_queries']} (그림 {s['false_recs']}장) |")
    lines += ["", "hit@1, hit@5: 1위(5위 안)에 맞는 그림이 있는 문단의 비율. recall@5: 맞는 그림 가운데 5위 안에 든 비율. "
              "ndcg@10: 등급(2 딱 맞음, 1 관련 있음)을 반영한 순위 품질. mrr: 처음 맞는 그림 순위의 역수.", "",
              "문단 수가 적으면 방식 사이의 작은 차이는 우연일 수 있다. 문턱과 가중치를 이 자료에 맞춘 뒤 같은 자료로 재면 수치가 부풀려진다.", "",
              "## 문단별 상위 5장", ""]
    for query in queries:
        analyzed = contexts[query.id]
        lines += [f"### {query.id} — {query.text[:80] or query.unit_code}{'…' if len(query.text) > 80 else ''}", ""]
        wanted = "그림을 권하지 말아야 함" if query.no_image else ", ".join(f"{name}({grade})" for name, grade in query.relevant.items())
        lines += [f"- 정답: {wanted}" + (f" — {query.note}" if query.note else ""),
                  f"- 핵심어({analyzed.method}): {', '.join(analyzed.keywords) or '-'}"]
        for number, point in enumerate(analyzed.points, 1):
            lines.append(f"- 지점 {number}: {point.description} [{point.kind or '종류 없음'}] 낱말 {', '.join(point.terms)}"
                         + (f" / 다른 이름 {', '.join(point.aliases)}" if point.aliases else ""))
        if analyzed.needs_image is False:
            lines.append(f"- 생성형 AI의 판단: 그림이 꼭 필요하지 않음({analyzed.needs_reason})")
        lines += ["", "| 방식 | 1 | 2 | 3 | 4 | 5 |", "|---|---|---|---|---|---|"]
        for label, result in results.items():
            row = next(item for item in result["queries"] if item["id"] == query.id)
            tops = [f"{'**' if top['grade'] else ''}{top['name']}{'**' if top['grade'] else ''}{'(' + str(top['grade']) + ')' if top['grade'] else ''} {top['score']}"
                    for top in row["top"]]
            lines.append(f"| {label} | " + " | ".join(tops + [""] * (5 - len(tops))) + " |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="정답 세트로 이미지 추천 방식을 견준다")
    parser.add_argument("gold", type=Path, help="정답 세트 JSON(ncs_recommend.evaluate의 형식)")
    parser.add_argument("--out", type=Path, required=True, help="보고서를 쓸 폴더")
    parser.add_argument("--no-llm", action="store_true", help="생성형 AI로 문단을 읽지 않는다(규칙 핵심어, 지점 없음)")
    parser.add_argument("--limit", type=int, default=10, help="문단마다 받을 추천 수(기본 10)")
    parser.add_argument("--dump", type=Path, help="후보·문맥·벡터를 이 JSON으로 남긴다(그림 파일은 넣지 않는다)")
    parser.add_argument("--load", type=Path, help="--dump로 남긴 파일로 DB·모델 없이 다시 잰다")
    args = parser.parse_args(argv)
    try:
        queries = evaluate.load_gold(json.loads(args.gold.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, evaluate.GoldError) as error:
        print(f"정답 세트를 읽지 못했습니다: {error}", file=sys.stderr)
        return 2
    if args.load:
        saved = json.loads(args.load.read_text(encoding="utf-8"))
        pool, vectors, references = saved["pool"], saved["vectors"], saved["references"]
        embedder = StoredEmbedder(saved["model"], vectors) if saved["model"] else None
        contexts = {query.id: context_from(saved["contexts"][query.id]) for query in queries if query.id in saved["contexts"]}
        absent = [query.id for query in queries if query.id not in contexts]
        if absent:
            print(f"--load 파일에 문맥이 없는 문단: {', '.join(absent)} — 같은 정답 세트로 --dump한 파일을 쓰세요", file=sys.stderr)
            return 2
        info = saved["info"]
    else:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            print("DATABASE_URL이 필요합니다(또는 --load 파일)", file=sys.stderr)
            return 2
        from ncs_service.images import image_recommend

        embedder = recommend_embed.get()
        pool = image_recommend.candidates(dsn, embedder.name if embedder else "")[:image_recommend.MAX_CANDIDATES]
        references = recommend_embed.reference_vectors(embedder) if embedder else []
        vectors, contexts = {}, {}
        for query in queries:
            criterion, _ = image_recommend.criterion_text(query.unit_code, query.criterion_no)
            contexts[query.id] = recommend_context.analyze(query.text, criterion, use_llm=not args.no_llm)
        methods = sorted({analyzed.method for analyzed in contexts.values()})
        info = {"context": ", ".join("생성형 AI" if method == "llm" else "규칙" for method in methods)
                + (f"({next(a.model for a in contexts.values() if a.model)})" if any(a.model for a in contexts.values()) else ""),
                "embedding": f"{embedder.name}, 벡터가 있는 후보 {sum(1 for row in pool if row.get('vector'))}건" if embedder
                else f"사용 안 함 — {recommend_embed.why_not()}",
                "described": sum(1 for row in pool if row.get("described"))}
    results = run(queries, pool, contexts, embedder, references, vectors, args.limit)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.md").write_text(report(args.gold.name, queries, pool, contexts, results, info), encoding="utf-8")
    (args.out / "report.json").write_text(json.dumps({"gold": args.gold.name, "info": info, "pool": len(pool), "variants": results},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    if args.dump:
        args.dump.write_text(json.dumps({"model": embedder.name if embedder else "", "info": info, "pool": pool, "references": references,
                                         "vectors": vectors, "contexts": {key: context_to(value) for key, value in contexts.items()}},
                                        ensure_ascii=False), encoding="utf-8")
    print(f"{'방식':<22}" + "".join(f"{name:>10}" for name in METRICS) + "   오탐 문단")
    for label, result in results.items():
        s = result["summary"]
        print(f"{label:<22}" + "".join(f"{'-' if s[name] is None else format(s[name], '.3f'):>10}" for name in METRICS)
              + f"   {s['no_image_with_recs']}/{s['no_image_queries']}")
    print(f"\n보고서: {args.out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
