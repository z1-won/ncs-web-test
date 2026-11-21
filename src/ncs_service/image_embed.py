"""이미지 저작권 DB의 그림에 임베딩 벡터를 붙인다 — 이미지 추천(REQ-02-011)이 그림 자체를 문맥과 맞춰 보는 데 쓴다.

벡터는 ncs_recommend.embed가 이 컴퓨터에서 직접 계산한다(외부 전송 없음). 그림마다 모델별로 한 벌(image_embeddings).
그림을 적재하면 자동으로 계산하고, 모델을 바꿨거나 나중에 켰으면 이 명령으로 한꺼번에 채운다.

  python -m ncs_service.image_embed            아직 벡터가 없는 그림 모두
  python -m ncs_service.image_embed --status   모델과 채워진 개수만 보기
업스케일본이 있으면 그것으로, 없으면 원본으로 계산한다(사람이 보게 될 그림과 같은 것).
"""

import argparse
import json
import os
import sys

import psycopg

from ncs_recommend import embed

CHUNK = 16


def status(dsn: str, model: str | None = None) -> dict:
    model = model or embed.model_name()
    with psycopg.connect(dsn) as connection:
        with_file, done = connection.execute(
            "SELECT count(*) FILTER (WHERE a.content IS NOT NULL OR a.upscaled_content IS NOT NULL), "
            "count(*) FILTER (WHERE e.image_id IS NOT NULL) "
            "FROM image_assets a LEFT JOIN image_embeddings e ON e.image_id = a.id AND e.model = %s", (model,)).fetchone()
    return {"모델": model, "그림 파일이 있는 그림": with_file, "벡터가 있는 그림": done}


def embed_missing(dsn: str, embedder=None, *, limit: int | None = None) -> dict:
    """벡터가 없는 그림을 계산해 넣는다. embedder를 주지 않으면 설정된 모델을 쓴다(꺼져 있으면 ValueError)."""
    embedder = embedder or embed.get()
    if embedder is None:
        raise ValueError(embed.why_not())
    made = failed = 0
    with psycopg.connect(dsn) as connection:
        ids = [row[0] for row in connection.execute(
            "SELECT a.id FROM image_assets a WHERE (a.content IS NOT NULL OR a.upscaled_content IS NOT NULL) "
            "AND NOT EXISTS (SELECT 1 FROM image_embeddings e WHERE e.image_id = a.id AND e.model = %s) "
            "ORDER BY a.created_at, a.id" + (" LIMIT %s" if limit else ""), (embedder.name, limit) if limit else (embedder.name,))]
        for start in range(0, len(ids), CHUNK):
            chunk = ids[start:start + CHUNK]
            rows = connection.execute(
                "SELECT id, coalesce(upscaled_content, content) FROM image_assets WHERE id = ANY(%s)", (chunk,)).fetchall()
            vectors = embedder.images([bytes(content) for _, content in rows])
            for (image_id, _), vector in zip(rows, vectors):
                if vector is None:
                    failed += 1
                    continue
                connection.execute(
                    "INSERT INTO image_embeddings (image_id, model, dim, vector) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (image_id, model) DO UPDATE SET dim = EXCLUDED.dim, vector = EXCLUDED.vector, created_at = now()",
                    (image_id, embedder.name, len(vector), vector))
                made += 1
            connection.commit()      # 묶음마다 남긴다 — 오래 걸리다 끊겨도 한 만큼은 남는다
    return {"모델": embedder.name, "새로 계산": made, "읽지 못한 그림": failed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="이미지 저작권 DB의 그림에 임베딩 벡터를 붙인다(외부 전송 없음)")
    parser.add_argument("--status", action="store_true", help="계산하지 않고 모델과 채워진 개수만 본다")
    parser.add_argument("--limit", type=int, help="이번에 계산할 그림 수 상한")
    args = parser.parse_args(argv)
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL이 필요합니다", file=sys.stderr)
        return 2
    try:
        result = status(dsn) if args.status else {**embed_missing(dsn, limit=args.limit), **{k: v for k, v in status(dsn).items() if k != "모델"}}
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
