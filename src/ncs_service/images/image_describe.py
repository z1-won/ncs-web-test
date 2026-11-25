"""이미지 저작권 DB의 그림에 설명을 붙인다 — 이미지 추천(REQ-02-011)의 설명 색인 0단계.

그림을 보는 모델이 그림을 글(종류, 장면, 대상, 그림 속 글자, 핵심어)로 풀어 image_descriptions에 둔다. 추천은 이 낱말을
사람이 단 키워드와 따로, 더 낮은 점수로 맞춰 본다(ncs_recommend.rank의 'described' 칸). 지시문·형식·검사는 ncs_recommend.describe.

**그림이 밖으로 나간다.** 지금 구현한 엔진은 외부 그림 모델(ncs_figures.vision — 그림 검수의 판독과 같은 길)뿐이다.
  NCS_DESCRIBE_ENGINE   api 이면 켜짐. **비어 있으면 꺼짐**(기본) — 추천은 설명 없이 지금처럼 돈다
  NCS_DESCRIBE_MODEL    '제공자:모델'(예: anthropic:claude-sonnet-5-5). 없으면 FIG_VISION_MODEL, 그것도 없으면 그림 검수의 기본 모델
  LLM_ALLOW_UPLOAD=1 그리고 LLM_ALLOW_IMAGE_UPLOAD=1 — 둘 다 있어야 보낸다(ncs_figures.vision.why_not_send)
이 컴퓨터에서 도는 로컬 엔진은 아직 없다(설계 문서 5절 — 모델 선정이 먼저다).

보내는 그림의 범위(--scope):
  public(기본)  이미 공개된 그림만 — 라이선스 체계가 공공누리·CC·만료·기증인 것. 원고에서 온 그림은 보내지 않는다
  all           비공개(release_class = private)를 뺀 모든 그림. 원고 그림이 밖으로 나가므로 기관 승인이 있을 때만 쓴다
비공개 그림은 어느 범위에서도 보내지 않는다.

  python -m ncs_service.images.image_describe            아직 설명이 없는 그림(범위 안)
  python -m ncs_service.images.image_describe --status   엔진과 채워진 개수만 보기
  python -m ncs_service.images.image_describe --scope all --limit 20
업스케일본이 아니라 원본을 보낸다 — 업스케일본은 글자를 지어낼 수 있다(ncs_figures.vision의 규칙).
이미 있는 설명은 다시 만들지 않는다(엔진마다 한 벌). 검사에서 떨어진 답(빈 설명, 형식 오류)은 저장하지 않고 '거른 그림'으로 센다.
"""

import argparse
import json
import os
import sys

import psycopg
from psycopg.types.json import Jsonb

from ncs_figures import vision
from ncs_recommend import describe

SCOPES = {
    "public": "r.license_scheme IN ('kogl', 'cc', 'expired', 'donated') AND r.release_class IS DISTINCT FROM 'private'",
    "all": "r.release_class IS DISTINCT FROM 'private'",
}


def engine_name() -> str:
    return os.getenv("NCS_DESCRIBE_ENGINE", "").strip().lower()


def why_not() -> str:
    """설명을 만들 수 없는 까닭(만들 수 있으면 빈 글)."""
    vision.load_dotenv()
    if engine_name() != "api":
        return "그림 설명이 꺼져 있습니다(.env의 NCS_DESCRIBE_ENGINE이 비어 있음 — api로 두면 켜집니다)"
    return vision.why_not_send()


def load_model():
    """설정된 그림 모델(ncs_figures.vision.VisionModel). 꺼져 있거나 보낼 수 없으면 ValueError(까닭)."""
    problem = why_not()
    if problem:
        raise ValueError(problem)
    return vision.load_model(os.getenv("NCS_DESCRIBE_MODEL", "").strip() or None)


def status(dsn: str, scope: str = "public") -> dict:
    with psycopg.connect(dsn) as connection:
        with_file, in_scope, described, checked = connection.execute(
            "SELECT count(*) FILTER (WHERE a.content IS NOT NULL), "
            f"count(*) FILTER (WHERE a.content IS NOT NULL AND {SCOPES[scope]}), "
            "count(*) FILTER (WHERE EXISTS (SELECT 1 FROM image_descriptions d WHERE d.image_id = a.id)), "
            "count(*) FILTER (WHERE EXISTS (SELECT 1 FROM image_descriptions d WHERE d.image_id = a.id AND d.checked_by IS NOT NULL)) "
            "FROM image_assets a LEFT JOIN image_rights r ON r.image_id = a.id").fetchone()
    return {"엔진": engine_name() or "꺼짐", "모델": os.getenv("NCS_DESCRIBE_MODEL", "") or os.getenv("FIG_VISION_MODEL", "") or vision.DEFAULT_SPEC,
            "그림 파일이 있는 그림": with_file, f"보낼 수 있는 그림({scope})": in_scope, "설명이 있는 그림": described, "사람이 확인한 설명": checked}


def describe_missing(dsn: str, model=None, *, scope: str = "public", limit: int | None = None) -> dict:
    """설명이 없는 그림(범위 안)을 모델에 보내 설명을 받아 넣는다. model을 주지 않으면 설정된 모델(꺼져 있으면 ValueError).
    model: ncs_figures.vision.VisionModel 모양(.name, .ask(task, system, text, image_png, schema)) — 테스트는 FakeVision을 넣는다."""
    if scope not in SCOPES:
        raise ValueError(f"scope는 {' 또는 '.join(SCOPES)}입니다: {scope}")
    model = model or load_model()
    made, rejected, failed, cached = 0, [], [], 0
    with psycopg.connect(dsn) as connection:
        ids = [row[0] for row in connection.execute(
            "SELECT a.id FROM image_assets a JOIN image_rights r ON r.image_id = a.id "
            f"WHERE a.content IS NOT NULL AND {SCOPES[scope]} "
            "AND NOT EXISTS (SELECT 1 FROM image_descriptions d WHERE d.image_id = a.id AND d.engine = %s) "
            "ORDER BY a.created_at, a.id" + (" LIMIT %s" if limit else ""), (model.name, limit) if limit else (model.name,))]
        for image_id in ids:
            content, sha256 = connection.execute("SELECT content, sha256 FROM image_assets WHERE id = %s", (image_id,)).fetchone()
            try:
                answer = model.ask(task=describe.TASK, system=describe.SYSTEM, text=describe.USER,
                                   image_png=vision.png_for_model(bytes(content)), schema=describe.SCHEMA)
            except vision.VisionError as error:
                failed.append({"sha256": sha256, "까닭": str(error)[:200]})
                if any(word in str(error) for word in ("미승인", "API_KEY", "로컬 전용", "모델 이름")):
                    break                       # 설정 문제는 끝까지 같은 오류다 — 남은 그림을 보내 보지 않는다
                continue
            except Exception as error:          # noqa: BLE001 — 열 수 없는 그림 하나 때문에 나머지를 버리지 않는다
                failed.append({"sha256": sha256, "까닭": f"{type(error).__name__}: {error}"[:200]})
                continue
            cleaned, problems = describe.clean(answer.data)
            if cleaned is None:
                rejected.append({"sha256": sha256, "까닭": problems})
                continue
            connection.execute(
                "INSERT INTO image_descriptions (image_id, engine, kind, scene, objects, visible_text, keywords) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (image_id, engine) DO NOTHING",
                (image_id, model.name, cleaned["kind"], cleaned["scene"], Jsonb(cleaned["objects"]), cleaned["visible_text"], cleaned["keywords"]))
            connection.commit()                 # 그림마다 남긴다 — 오래 걸리다 끊겨도 한 만큼은 남는다
            made += 1
            cached += 1 if answer.cached else 0
    return {"엔진": model.name, "범위": scope, "새로 만든 설명": made, "캐시에서 읽음": cached, "거른 그림": rejected, "실패": failed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="이미지 저작권 DB의 그림에 설명을 붙인다(그림을 외부 그림 모델로 보낸다)")
    parser.add_argument("--status", action="store_true", help="만들지 않고 엔진과 채워진 개수만 본다")
    parser.add_argument("--scope", choices=sorted(SCOPES), default="public", help="보낼 그림의 범위(기본 public: 이미 공개된 그림만)")
    parser.add_argument("--limit", type=int, help="이번에 보낼 그림 수 상한")
    args = parser.parse_args(argv)
    vision.load_dotenv()
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL이 필요합니다", file=sys.stderr)
        return 2
    try:
        result = status(dsn, args.scope) if args.status else {**describe_missing(dsn, scope=args.scope, limit=args.limit),
                                                              **{k: v for k, v in status(dsn, args.scope).items() if k not in ("엔진", "모델")}}
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
