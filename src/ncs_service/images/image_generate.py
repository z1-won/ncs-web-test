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
AI_USAGE_CREATED = 4        # 표기 예 4: AI 창작(문단 없이 주제만 주고 만든 그림)
TARGET_DPI = 300
PNG_HEAD = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_BYTES = 20 << 20


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
    return _load(dsn, png, title=spec.title, asset_kind=ASSET_KIND[spec.kind], table=spec.kind == "table", by=by, on=on, tool=tool,
                 usage=AI_USAGE_FROM_TEXT if ai else None, module_code=module_code, number=number)


def register_image(dsn: str, png: bytes, *, kind: str, usage: int, title: str = "", by: str, on: date, tool: str,
                   module_code: str = "", number: str = "") -> dict:
    """이미지 생성 모델로 만든 사진·삽화를 올린다. kind: 'photo' | 'illustration', usage: 표기 예 1(문단 기반) 또는 4(AI 창작).
    화면이 보낸 PNG를 받으므로(다시 만들 수 없다) PNG인지와 크기만 본다. 돌려주는 것은 register와 같다."""
    if kind not in ("photo", "illustration"):
        raise ValueError("kind는 photo 또는 illustration이어야 합니다")
    if usage not in (AI_USAGE_FROM_TEXT, AI_USAGE_CREATED):
        raise ValueError("usage는 1(문단을 바탕으로 생성) 또는 4(AI 창작)여야 합니다")
    check_png(png)
    return _load(dsn, png, title=" ".join((title or "").split()), asset_kind=kind, table=False, by=by, on=on, tool=tool, usage=usage,
                 module_code=module_code, number=number)


def check_png(png: bytes) -> None:
    if not png.startswith(PNG_HEAD):
        raise ValueError("PNG 그림이 아닙니다")
    if len(png) > MAX_IMAGE_BYTES:
        raise ValueError(f"그림이 너무 큽니다({MAX_IMAGE_BYTES >> 20}MB까지)")


def inspect(png: bytes, width_mm: float) -> dict:
    """받기 전에 볼 것 가운데 규칙으로 잴 수 있는 것 — 놓을 폭에서의 해상도. → {'width', 'height', 'dpi', '충분', '300 DPI 폭'(mm)}."""
    from ncs_core.pictures import image_header

    check_png(png)
    header = image_header(png)
    if header is None or not header[1] or not header[2]:
        raise ValueError("그림의 크기를 읽지 못했습니다")
    _format, width, height = header
    dpi = round(width / (width_mm / 25.4))
    return {"width": width, "height": height, "width_mm": width_mm, "dpi": dpi, "충분": dpi >= TARGET_DPI,
            "300 DPI 폭": int(width / TARGET_DPI * 25.4)}


def _load(dsn: str, png: bytes, *, title: str, asset_kind: str, table: bool, by: str, on: date, tool: str, usage: int | None,
          module_code: str, number: str) -> dict:
    tool = " ".join((tool or "").split())
    if usage and not tool:
        raise ValueError("AI로 만든 그림은 도구 이름이 필요합니다")
    if number and not module_code.strip():
        raise ValueError("번호를 적으려면 모듈 코드가 필요합니다")
    record: dict = {"content": png, "title": title or None, "filename": f"{title or '그림'}.png", "kind": asset_kind,
                    "rights": {"category": "author_made"}}
    title = title or None
    if usage:
        record["rights"]["ai"] = {"used": True, "usage": usage, "tool": tool, "date": on.isoformat()}
    if module_code.strip():
        label = (("표 " if table else "그림 ") + number) if number else ""
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
