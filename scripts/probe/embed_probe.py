"""그림 임베딩 점검 — 모델이 이 컴퓨터에서 올라오는지, 한국어 글과 그림이 맞게 짝지어지는지 간단히 본다(외부로 보내는 것 없음).

  set -a; source .env; set +a
  python scripts/probe/embed_probe.py                         # 저장소 예시 그림 + 기본 문장
  python scripts/probe/embed_probe.py 그림1.jpg 그림2.jpg       # 내 그림으로
  python scripts/probe/embed_probe.py samples/kogl/*.jpg --text "호텔 프런트 데스크" --text "객실 침대"

문장마다 그림들과의 코사인 유사도, 바탕을 뺀 σ(rank.visual_scores), 추천에서 받는 유사도 점수(0~100%)를 σ가 높은 순으로 보여 준다.
추천 화면은 추천된 그림만 보여 주지만 여기서는 모든 그림이 나온다 — **순서가 납득되는지**, 맞는 그림의 σ가 문턱
(rank.VISUAL_Z_MIN ~ VISUAL_Z_FULL)을 넘는지 본다.
--dump 파일.json을 주면 그림·바탕 글·점검 문장(DUMP_TEXTS)의 벡터를 파일로 남긴다 — 점수 계산법을 모델 없이 맞춰 보기 위한 것.
모델은 .env의 NCS_EMBED_MODEL, 없으면 --model. 처음 한 번은 모델 파일을 내려받느라 오래 걸린다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ncs_recommend import embed, rank  # noqa: E402

DEFAULT_MODEL = "google/siglip2-base-patch16-224"
DEFAULT_TEXTS = ["호텔 프런트 데스크", "호텔 객실 침대", "연회장", "객실 복도", "건물 외부 전경"]


# --dump에 함께 담는 점검 문장: 맞는 그림이 있는 문단, 그 문단의 핵심어, 짧은 묘사, 맞는 그림이 없어야 하는 문단
DUMP_TEXTS = [
    "고객이 호텔에 도착하면 접수대에서 직원이 예약 내역을 확인하고 투숙 절차를 안내한다.",
    "고객", "호텔", "접수대", "직원", "예약 내역", "투숙 절차", "호텔 접수대", "호텔 프런트 데스크", "hotel front desk reception counter",
    "대규모 행사를 치르기 위해 원형 탁자와 의자를 배치한 넓은 홀을 준비한다.",
    "대규모 행사", "원형 탁자", "의자", "넓은 홀", "연회장", "원형 탁자와 의자를 배치한 넓은 홀",
    "투숙객이 머무는 방에는 침구가 정돈된 침대가 놓여 있고 창으로 바깥 풍경이 보인다.",
    "투숙객", "방", "침구", "침대", "창", "바깥 풍경", "침대가 놓인 호텔 객실", "객실 침대와 창",
    "객실 유형은 침대의 수와 크기에 따라 싱글, 더블, 트윈으로 구분하며 예약 접수 시 고객이 원하는 객실 유형을 확인한다.",
    "객실 복도", "긴 복도", "복도에 설치된 소화전", "탈의실 사물함", "건물 외부 전경", "산속 숙박 시설을 하늘에서 내려다본 모습",
    "용접 작업 전에 보호구를 착용하고 가스 누출 여부를 점검한다.",
    "센서에서 수집한 데이터는 게이트웨이를 거쳐 클라우드 플랫폼으로 전송되며, 저전력 무선 통신 프로토콜을 사용한다.",
    "밭에 퇴비를 뿌리고 트랙터로 흙을 갈아엎는다.",
    "치과 진료 기구를 고압 증기로 멸균하고 포장한다.",
    "아스팔트 포장 두께를 측정하고 다짐 상태를 확인한다.",
    "주식 시세 차트에서 이동 평균선의 교차 지점을 찾는다.",
    "호텔 경영 전략을 수립하고 연간 매출 목표를 정한다.",
    "호텔 직원의 근무 일정을 편성하고 급여를 계산한다.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="그림 임베딩 모델 점검(이 컴퓨터에서만 계산)")
    parser.add_argument("images", nargs="*", type=Path, help="그림 파일들(없으면 저장소 예시 그림)")
    parser.add_argument("--text", action="append", help="견줄 문장(여러 번 줄 수 있음)")
    parser.add_argument("--dump", type=Path, help="그림·바탕 글·점검 문장의 벡터를 이 JSON 파일로 남긴다")
    parser.add_argument("--model", help=f"모델 이름(기본: NCS_EMBED_MODEL 또는 {DEFAULT_MODEL})")
    args = parser.parse_args()
    os.environ["NCS_EMBED_MODEL"] = args.model or embed.model_name() or DEFAULT_MODEL
    images = args.images or sorted((ROOT / "docs" / "examples").rglob("*.png"))
    started = time.time()
    embedder = embed.get()
    if embedder is None:
        print(embed.why_not(), file=sys.stderr)
        print('설치: pip install -e ".[embed]"', file=sys.stderr)
        return 1
    print(f"모델 {embedder.name} ({embedder.device}) — 올리는 데 {time.time() - started:.1f}초")
    started = time.time()
    vectors = embedder.images([path.read_bytes() for path in images])
    print(f"그림 {len(images)}장 — {time.time() - started:.1f}초, 벡터 길이 {next((len(v) for v in vectors if v), 0)}")
    references = embed.reference_vectors(embedder)
    rows = [{"vector": vector} for vector in vectors]
    print(f"문턱: σ {rank.VISUAL_Z_MIN} 이하는 0%, {rank.VISUAL_Z_FULL} 이상은 100% (핵심어가 안 맞는 그림은 50%부터 추천)")
    for text in args.text or DEFAULT_TEXTS:
        scores = rank.visual_scores(rows, embedder.text(text), references)
        ranked = sorted(((similarity, z, position, images[index].name) for index, (similarity, z, position) in scores.items()), key=lambda row: -row[1])
        print(f"\n“{text}”\n  유사도     σ    점수  그림")
        for similarity, z, position, name in ranked:
            print(f"  {similarity:+.4f}  {z:+5.1f}  {position * 100:3.0f}%  {name}")
    if args.dump:
        import json

        def short(vector):
            return None if vector is None else [round(value, 5) for value in vector]

        texts = list(dict.fromkeys([*(args.text or []), *DUMP_TEXTS]))
        args.dump.write_text(json.dumps({
            "model": embedder.name,
            "images": {path.name: short(vector) for path, vector in zip(images, vectors)},
            "references": {text: short(vector) for text, vector in zip(embed.REFERENCE_TEXTS, references)},
            "texts": {text: short(embedder.text(text)) for text in texts},
        }, ensure_ascii=False), encoding="utf-8")
        print(f"\n벡터를 {args.dump}에 남겼습니다(그림 {len(images)}, 바탕 글 {len(references)}, 점검 문장 {len(texts)})")
    unreadable = [path.name for path, vector in zip(images, vectors) if vector is None]
    if unreadable:
        print(f"\n읽지 못한 그림: {', '.join(unreadable)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
