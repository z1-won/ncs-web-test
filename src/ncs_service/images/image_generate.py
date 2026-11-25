"""도표·표·그래프 생성(REQ-02-006 ①)으로 만든 그림을 이미지 저작권 DB(REQ-02-010)에 잇는다 — 닮은 그림 대조와 등록.

닮은 그림 대조(similar): 만든 그림을 DB의 그림과 세 가지로 견준다.
  ① 같은 파일(sha256) ② 지각 해시(pHash 64비트)의 해밍 거리가 NEAR 이하 ③ 임베딩을 켠 서버에서는 코사인 유사도가 COSINE 이상.
  지각 해시는 image_phashes에 둔다(마이그레이션 023). 아직 없는 그림은 대조할 때 FILL개씩 채운다 — 한 번에 다 채우지 않으므로
  '남은 그림'이 0이 아니면 일부만 견준 것이다. 기준값(NEAR, COSINE)은 실제 그림으로 맞춘 값이 아니다(scripts/probe/similar_recall.py로 잰다).
  틀이 같은 도표끼리는(같은 칸 수의 순서도 등) 내용이 달라도 지각 해시가 가까울 수 있다 — 닮았다는 알림이지 같은 그림이라는 판정이 아니다.
등록(register): PNG와 종류, AI 활용 정보(활용 유형 1: 집필진 작성 내용 기반 AI 생성, 도구, 일자), 수록 위치(모듈 코드와 번호를 주면)를
  이미지 레코드로 적재한다(image_db.load_records — 같은 파일이 이미 있으면 합치고, 기관이 확정한 권리 정보는 건드리지 않는다).
  분류는 '집필진 제작'으로 적되 권리 귀속과 재사용 범위는 정하지 않는다(기관이 확정한다). 확정 전에는 추천에 나오지 않는다.
"""

from __future__ import annotations

import hashlib
from datetime import date

import psycopg

from ncs_aiimage.diagram import ASSET_KIND, Spec
from ncs_figures.ids import hamming, phash

from . import image_db

NEAR = 10            # 지각 해시 해밍 거리(64비트 가운데) — ncs_figures.db의 근접 기준과 같다
COSINE = 0.9         # 임베딩 코사인 유사도
FILL = 300           # 한 번의 대조에서 새로 채우는 지각 해시 수
AI_USAGE_FROM_TEXT = 1      # AI 도구 사용 표기 예 1(image_terms.AI_USAGE)


def fill_phashes(connection, limit: int = FILL) -> int:
    """지각 해시가 없는 그림을 limit개까지 채우고 남은 수를 돌려준다. 읽을 수 없는 그림은 빈 값으로 적어 다시 읽지 않는다."""
    rows = connection.execute(
        "SELECT a.id, a.content FROM image_assets a LEFT JOIN image_phashes p ON p.image_id = a.id "
        "WHERE p.image_id IS NULL AND a.content IS NOT NULL ORDER BY a.created_at LIMIT %s", (limit,)).fetchall()
    for image_id, content in rows:
        connection.execute("INSERT INTO image_phashes (image_id, phash) VALUES (%s, %s) ON CONFLICT (image_id) DO NOTHING",
                           (image_id, phash(bytes(content)) or ""))
    return connection.execute(
        "SELECT count(*) FROM image_assets a LEFT JOIN image_phashes p ON p.image_id = a.id "
        "WHERE p.image_id IS NULL AND a.content IS NOT NULL").fetchone()[0]


def similar(dsn: str, png: bytes, *, limit: int = 5, confirmed_only: bool = False, embedder=None) -> dict:
    """→ {'같은 파일': id | None, '닮은 그림': [{id, title, kind, 방법, 거리, 점수, 확정}], '대조한 그림', '남은 그림', '임베딩', '기준'}.

    confirmed_only: 기관이 확정하고 재사용 범위가 정해진 그림(v_image_recommendable)하고만 견준다 — 확정 전 그림을 보이면 안 되는 사람에게.
    embedder: ncs_recommend.embed.get()이 준 것(없으면 임베딩 대조를 하지 않는다).
    """
    sha256 = hashlib.sha256(png).hexdigest()
    mine = phash(png)
    pool = "v_image_recommendable" if confirmed_only else "image_assets"
    found: dict[str, dict] = {}
    with psycopg.connect(dsn) as connection:
        left = fill_phashes(connection)
        same = connection.execute(f"SELECT a.id FROM {pool} a WHERE a.sha256 = %s", (sha256,)).fetchone()
        rows = connection.execute(
            f"SELECT a.id, p.phash FROM {pool} a JOIN image_phashes p ON p.image_id = a.id WHERE p.phash <> ''").fetchall()
        if mine:
            for image_id, other in rows:
                distance = hamming(mine, other)
                if distance <= NEAR:
                    found[str(image_id)] = {"방법": "지각 해시", "거리": distance, "점수": round(1 - distance / 64, 3)}
        vector = embedder.images([png])[0] if embedder is not None else None
        if vector is not None:
            from ncs_recommend.embed import cosine

            for image_id, other in connection.execute(
                    f"SELECT a.id, e.vector FROM {pool} a JOIN image_embeddings e ON e.image_id = a.id WHERE e.model = %s", (embedder.name,)):
                score = cosine(vector, list(other))
                if score is not None and score >= COSINE and str(image_id) not in found:
                    found[str(image_id)] = {"방법": "임베딩", "거리": None, "점수": round(score, 3)}
        if same:
            found[str(same[0])] = {"방법": "같은 파일", "거리": 0, "점수": 1.0}
        top = sorted(found.items(), key=lambda item: (-item[1]["점수"], item[0]))[:limit]
        details = {str(row[0]): row for row in connection.execute(
            "SELECT a.id, a.title, a.kind, r.status FROM image_assets a LEFT JOIN image_rights r ON r.image_id = a.id WHERE a.id = ANY(%s::uuid[])",
            ([key for key, _ in top],)).fetchall()} if top else {}
    return {"같은 파일": str(same[0]) if same else None,
            "닮은 그림": [{"id": key, "title": details[key][1] or "", "kind": details[key][2] or "", "확정": details[key][3] == "confirmed", **how}
                       for key, how in top],
            "대조한 그림": len(rows), "남은 그림": left, "임베딩": vector is not None, "기준": {"지각 해시 거리": NEAR, "임베딩 유사도": COSINE}}


def register(dsn: str, png: bytes, spec: Spec, *, by: str, on: date, tool: str = "", ai: bool = True,
             module_code: str = "", number: str = "") -> dict:
    """→ {'id', '새 그림': bool, '확정 유지': bool, '수록 위치': 넣은 수}. 거부되면 ValueError(사유).

    ai=False: 집필자가 칸을 모두 직접 적어 그린 것 — AI 활용 정보를 적지 않는다. number: '1-2' 꼴(모듈 코드와 함께 주면 수록 위치를 적는다)."""
    tool = " ".join((tool or "").split())
    if ai and not tool:
        raise ValueError("AI로 만든 그림은 도구 이름이 필요합니다")
    if number and not module_code.strip():
        raise ValueError("번호를 적으려면 모듈 코드가 필요합니다")
    title = spec.title or None
    record: dict = {"content": png, "title": title, "filename": f"{spec.title or '도표'}.png", "kind": ASSET_KIND[spec.kind],
                    "rights": {"category": "author_made"}}
    if ai:
        record["rights"]["ai"] = {"used": True, "usage": AI_USAGE_FROM_TEXT, "tool": tool, "date": on.isoformat()}
    if module_code.strip():
        label = (("표 " if spec.kind == "table" else "그림 ") + number) if number else ""
        record["placements"] = [{"module_code": module_code.strip(), "label": label, "caption": title,
                                 "source_line": f"출처: 집필진 제작({on.year})"}]
    report = image_db.load_records(dsn, [record], changed_by=by)
    if report.rejected:
        raise ValueError("이미지 저작권 DB가 받지 않았습니다: " + "; ".join(report.rejected[0]["reasons"]))
    sha256 = hashlib.sha256(png).hexdigest()
    with psycopg.connect(dsn) as connection:
        image_id = connection.execute("SELECT id FROM image_assets WHERE sha256 = %s", (sha256,)).fetchone()[0]
        connection.execute("INSERT INTO image_phashes (image_id, phash) VALUES (%s, %s) ON CONFLICT (image_id) DO NOTHING",
                           (image_id, phash(png) or ""))
    return {"id": str(image_id), "새 그림": bool(report.created), "확정 유지": bool(report.kept_confirmed), "수록 위치": report.placements_added}
