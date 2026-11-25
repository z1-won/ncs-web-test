"""추천 선택 기록(REQ-02-011) — 추천된 그림을 집필자가 '쓸 그림'으로 골랐는지 '맞지 않음'으로 보았는지 남기고, 정답 세트로 내보낸다.

추천을 고치려면 재 볼 자료가 있어야 한다. 사람이 따로 정답 세트를 만들지 않아도, 쓰면서 남긴 선택이 쌓이면 그것이 정답 세트가 된다
(ncs_recommend.evaluate의 형식: 쓴 그림 = 등급 2). '맞지 않음'은 등급 0이라 relevant에는 넣지 않고 rejected로 따로 싣는다.
문단 글을 함께 남긴다 — 같은 문단으로 방식을 다시 견주려면 글이 있어야 한다. 같은 사람이 같은 문단·같은 그림을 다시 고르면 앞의 기록을 바꾼다.
기록할 수 있는 그림은 추천 대상(v_image_recommendable, 비공개 제외)뿐이다.
"""

import hashlib
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ncs_recommend import evaluate

from .image_store import RECOMMENDABLE, ImageNotFound, _uuid

CHOICES = ("used", "rejected")
CLEAR = "none"
MAX_TEXT = 4000


def query_key(text: str, unit_code: str, criterion_no: str) -> str:
    """같은 문단·수행준거인지 가리는 열쇠 — 띄어쓰기 차이는 같은 문단으로 본다."""
    joined = "\n".join((" ".join((text or "").split()), (unit_code or "").strip(), (criterion_no or "").strip()))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def record(dsn: str, *, by: str, image_id: str, choice: str, text: str = "", unit_code: str = "", criterion_no: str = "",
           rank: int | None = None, score: float | None = None, detail: dict | None = None) -> dict:
    """선택 하나를 남긴다(choice: used | rejected) 또는 지운다(none). 반환 {'choice': 남은 선택|None}.
    by가 비었거나 문단·능력단위가 모두 비었으면 ValueError, 추천 대상이 아닌 그림이면 ImageNotFound."""
    by, text = (by or "").strip(), (text or "").strip()[:MAX_TEXT]
    unit_code, criterion_no = (unit_code or "").strip(), (criterion_no or "").strip()
    if choice not in (*CHOICES, CLEAR):
        raise ValueError(f"choice는 {', '.join((*CHOICES, CLEAR))} 가운데 하나입니다")
    if not by:
        raise ValueError("by(고른 사람)가 필요합니다")
    if not text and not unit_code:
        raise ValueError("문단이나 능력단위 코드가 있어야 합니다")
    key = query_key(text, unit_code, criterion_no)
    image_id = _uuid(image_id)
    with psycopg.connect(dsn) as connection:
        found = connection.execute(f"SELECT 1 FROM v_image_recommendable v WHERE v.id = %s AND {RECOMMENDABLE}", (image_id,)).fetchone()
        if found is None:
            raise ImageNotFound("추천 대상 그림이 아닙니다")
        if choice == CLEAR:
            connection.execute("DELETE FROM recommend_choices WHERE chosen_by = %s AND query_key = %s AND image_id = %s", (by, key, image_id))
            return {"choice": None}
        connection.execute(
            "INSERT INTO recommend_choices (id, chosen_by, query_key, query_text, unit_code, criterion_no, image_id, choice, rank, score, detail) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (chosen_by, query_key, image_id) DO UPDATE SET choice = EXCLUDED.choice, rank = EXCLUDED.rank, score = EXCLUDED.score, "
            "detail = EXCLUDED.detail, created_at = now()",
            (uuid4(), by, key, text, unit_code, criterion_no, image_id, choice, rank, score, Jsonb(detail or {})))
    return {"choice": choice}


def mine(dsn: str, *, by: str, text: str = "", unit_code: str = "", criterion_no: str = "") -> dict[str, str]:
    """이 사람이 이 문단에서 남긴 선택 — {그림 id: used | rejected}."""
    key = query_key((text or "").strip()[:MAX_TEXT], unit_code, criterion_no)
    with psycopg.connect(dsn) as connection:
        rows = connection.execute("SELECT image_id, choice FROM recommend_choices WHERE chosen_by = %s AND query_key = %s", ((by or "").strip(), key)).fetchall()
    return {str(image_id): choice for image_id, choice in rows}


def counts(dsn: str) -> dict:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        return connection.execute(
            "SELECT count(DISTINCT query_key) AS queries, count(*) FILTER (WHERE choice = 'used') AS used, "
            "count(*) FILTER (WHERE choice = 'rejected') AS rejected FROM recommend_choices").fetchone()


def export_gold(dsn: str) -> dict:
    """선택 기록 → 정답 세트(ncs_recommend.evaluate의 형식). 문단마다: 누구든 '쓸 그림'으로 고른 그림은 등급 2.
    쓴 사람이 없고 '맞지 않음'만 있는 그림은 rejected에 싣는다(평가에는 쓰이지 않는 참고 값).
    쓴 그림이 하나도 없는 문단은 정답이 없으므로 빼고 그 수를 note에 적는다 — '그림을 권하지 말아야 하는 문단'인지는 사람이 정한다.
    그림 이름표는 source_id(있으면), 없으면 sha256."""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT c.query_key, c.query_text, c.unit_code, c.criterion_no, c.choice, c.chosen_by, c.created_at, a.sha256, a.source_id "
            "FROM recommend_choices c JOIN image_assets a ON a.id = c.image_id ORDER BY c.created_at, c.id").fetchall()
    grouped: dict[str, dict] = {}
    for row in rows:
        entry = grouped.setdefault(row["query_key"], {"text": row["query_text"], "unit_code": row["unit_code"], "criterion_no": row["criterion_no"],
                                                      "used": {}, "rejected": {}, "people": set()})
        name = row["source_id"] or row["sha256"]
        entry[row["choice"]][name] = entry[row["choice"]].get(name, 0) + 1
        entry["people"].add(row["chosen_by"])
    queries, skipped = [], 0
    for number, entry in enumerate(grouped.values(), 1):
        if not entry["used"]:
            skipped += 1
            continue
        queries.append({"id": f"c{number:03d}", "text": entry["text"], "unit_code": entry["unit_code"], "criterion_no": entry["criterion_no"],
                        "relevant": {name: 2 for name in entry["used"]},
                        "rejected": sorted(name for name in entry["rejected"] if name not in entry["used"]),
                        "no_image": False, "note": f"선택 기록에서 만듦(고른 사람 {len(entry['people'])}명)"})
    return {"schema": evaluate.SCHEMA,
            "note": f"추천 선택 기록에서 내보낸 정답 세트. 쓴 그림이 없어 뺀 문단 {skipped}개. "
                    "등급 2는 '집필자가 쓸 그림으로 고름'이며 사람이 다시 읽고 등급 1(관련 있으나 꼭 맞지 않음)을 보태면 더 정확해진다.",
            "queries": queries}
