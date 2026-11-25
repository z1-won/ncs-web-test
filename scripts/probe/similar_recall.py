"""닮은 그림 대조(REQ-02-006 ① — image_generate.similar)의 Recall@k를 잰다: DB의 그림을 조금 바꾼 것을 넣었을 때 원래 그림이 상위 k에 나오는가.

  PYTHONPATH=src python scripts/probe/similar_recall.py --dsn postgresql://… [--count 50] [--k 5] [--seed 20261125] [--embed]
DSN은 --dsn 또는 NCS_DATABASE_URL. 그림 --count장을 골라 다섯 가지로 바꾼다: 절반으로 줄임, JPEG로 다시 저장(품질 60), 흑백, 가장자리 5% 자름, 밝기 +15%.
바꾼 그림마다 similar를 불러 원래 그림이 상위 k에 있는지 센다. 원래 그림이 DB에 있으므로 '같은 파일'이 아니라 지각 해시(와 --embed면 임베딩)로 찾은 것만 맞은 것이다.
찾지 못한 까닭도 나눠 찍는다: 기준(NEAR, COSINE) 밖이라 안 나옴 / 나왔지만 k위 밖. 지각 해시가 아직 없는 그림은 먼저 모두 채운다(image_phashes에 쓴다).
이것은 '같은 그림의 변형을 다시 찾는가'만 잰다. 뜻이 비슷한 다른 그림을 찾는 일은 정답 세트가 있어야 잴 수 있다.
"""

import argparse
import io
import os
import random
from collections import Counter

import psycopg
from PIL import Image, ImageEnhance

from ncs_service.images import image_generate


def variants(content: bytes) -> dict[str, bytes]:
    image = Image.open(io.BytesIO(content))
    image = image.convert("RGB") if image.mode not in ("RGB", "L") else image
    width, height = image.size
    made = {
        "절반으로 줄임": image.resize((max(1, width // 2), max(1, height // 2))),
        "JPEG 품질 60": image,
        "흑백": image.convert("L"),
        "가장자리 5% 자름": image.crop((width // 20, height // 20, width - width // 20, height - height // 20)),
        "밝기 +15%": ImageEnhance.Brightness(image.convert("RGB")).enhance(1.15),
    }
    out = {}
    for name, picture in made.items():
        buffer = io.BytesIO()
        picture.convert("RGB").save(buffer, "JPEG", quality=60) if name == "JPEG 품질 60" else picture.save(buffer, "PNG")
        out[name] = buffer.getvalue()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=os.getenv("NCS_DATABASE_URL", ""))
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--embed", action="store_true", help="임베딩도 쓴다(NCS_EMBED_MODEL이 켜져 있어야 한다)")
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn 또는 NCS_DATABASE_URL이 필요합니다")
    embedder = None
    if args.embed:
        from ncs_recommend import embed

        embedder = embed.get()
        if embedder is None:
            parser.error(f"임베딩을 쓸 수 없습니다: {embed.why_not()}")
    with psycopg.connect(args.dsn) as connection:
        while image_generate.fill_phashes(connection, 500):
            connection.commit()
        ids = [row[0] for row in connection.execute(
            "SELECT a.id FROM image_assets a JOIN image_phashes p ON p.image_id = a.id WHERE p.phash <> '' ORDER BY a.sha256")]
        picked = random.Random(args.seed).sample(ids, min(args.count, len(ids)))
        contents = {str(image_id): bytes(content) for image_id, content in connection.execute(
            "SELECT id, content FROM image_assets WHERE id = ANY(%s)", (picked,))}
    if not contents:
        parser.error("읽을 수 있는 그림이 DB에 없습니다")
    hit, shown, tried = Counter(), Counter(), Counter()
    for image_id, content in contents.items():
        for name, data in variants(content).items():
            found = image_generate.similar(args.dsn, data, limit=max(args.k, 50), embedder=embedder)["닮은 그림"]
            order = [entry["id"] for entry in found]
            tried[name] += 1
            shown[name] += image_id in order
            hit[name] += image_id in order[:args.k]
    print(f"그림 {len(contents)}장(DB의 읽을 수 있는 그림 {len(ids)}장 가운데), k = {args.k}, 기준: 지각 해시 거리 {image_generate.NEAR} 이하"
          + (f", 임베딩 유사도 {image_generate.COSINE} 이상({embedder.name})" if embedder else ", 임베딩 안 씀"))
    for name in tried:
        outside = tried[name] - shown[name]
        print(f"  {name}: Recall@{args.k} {hit[name]}/{tried[name]} = {hit[name] / tried[name]:.1%}"
              f" (기준 밖이라 안 나옴 {outside}, 나왔지만 {args.k}위 밖 {shown[name] - hit[name]})")
    total = sum(tried.values())
    print(f"  전체: {sum(hit.values())}/{total} = {sum(hit.values()) / total:.1%}")


if __name__ == "__main__":
    main()
