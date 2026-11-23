"""그림 DB — 010 이미지 저작권 DB가 생기기 전의 스텁(SQLite 파일 하나).

쓰임(2026-11-20 정리): 원고 그림이 저작권 문제이거나 오래되었을 때 **바꿔 쓸 같은 주제의 그림을 찾는 것**(similar).
DB에 같은 그림이 있다는 것 자체는 문제가 아니므로 판정(위험도)에는 넣지 않는다. 같은 그림 찾기(find)는 남겨 둔다
(재사용 현황 집계·나중의 복제 탐지용).

채우는 법: 009 태깅 결과(figures.jsonl 또는 modules/*.jsonl)를 그대로 넣는다(`python -m ncs_figures db build`).
그림 하나(image_id)·쓰인 모듈마다 한 줄: 지각 해시, 그림 번호·제목, 출처, 권리 정보, 그림 파일 경로.

찾는 법(find): ① image_id가 같으면 완전 일치(exact) ② 지각 해시(pHash 64비트) 해밍 거리가 기준 이하면 근접(near).
검수하는 원고 자신의 모듈은 뺀다(자기 그림과 맞는 것은 재사용이 아님).
다음 단계(설계 5.3): 근접 후보를 SSCD(복제 탐지 벡터)로 다시 재서 자르기·색 보정한 사본까지 잡는다 — 지금은 pHash만.

권리 정보(rights_status)는 010 DB가 생기면 거기서 받는다. 스텁은 출처 종류로 어림한다:
- 출처 없음·집필진 제작·기존 학습모듈 → '교육부 귀속'(학습모듈용 제작 그림 — 사진·삽화 제작 계약서 제6조)
- 공공누리 → '공공누리 제N유형'(유형 조건 안에서 출처를 밝히면 이용 가능)
- 그 밖(문헌·웹·기업 자료) → '미확인'(원 저작자에게 이용허락을 받았는지 모름)
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .ids import hamming
from .models import Match

SCHEMA_VERSION = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
  image_id TEXT NOT NULL, module TEXT NOT NULL, phash TEXT, figure_label TEXT, figure_title TEXT,
  lesson INTEGER, source_kind TEXT, source_text TEXT, cited_module TEXT, cited_page INTEGER, kogl_type TEXT,
  rights_status TEXT, license_type TEXT, rights_basis TEXT, image_file TEXT, origin TEXT, added_at TEXT,
  element_code TEXT, element_name TEXT, keywords TEXT, image_type TEXT,
  PRIMARY KEY (image_id, module, figure_label)
);
CREATE INDEX IF NOT EXISTS images_id ON images(image_id);
"""
EDU = "교육부 귀속"


_STOP = {"사례", "예시", "예", "및", "의", "등", "그림", "표"}


def _words(text: str) -> list[str]:
    """제목·키워드 → 낱말(기호·괄호 빼고, 너무 흔한 말 빼고)."""
    import re
    words = re.findall(r"[가-힣A-Za-z0-9]+", text or "")
    return [w for w in words if w not in _STOP and len(w) >= 2]


def _grams(words: list[str]) -> set[str]:
    """낱말마다 두 글자 조각(짧은 영문 약어는 통째로)."""
    out = set()
    for w in words:
        w = w.lower()
        out.update({w} if len(w) <= 2 else {w[i:i + 2] for i in range(len(w) - 1)})
    return out


def rights_of(source: dict | None) -> tuple[str, str | None, str]:
    """(rights_status, license_type, 근거) — 스텁의 어림값. 010 DB가 생기면 그 값을 쓴다."""
    kind = (source or {}).get("kind")
    if source is None or kind in ("집필진 제작", "기존 학습모듈"):
        return EDU, None, "학습모듈용 제작 그림은 교육부 귀속(사진·삽화 제작 계약서 제6조) — 스텁 어림값"
    if kind == "공공누리":
        kogl = source.get("kogl_type")
        label = "공공누리 AI유형" if kogl == "AI" else (f"공공누리 제{kogl}유형" if kogl else "공공누리 유형 미상")
        return label, f"KOGL-{kogl or '?'}", "출처 줄의 공공누리 표기"
    return "미확인", None, f"{kind} 출처 — 원 저작자 이용허락 여부를 모름"


def licensed(rights_status: str | None) -> bool:
    """출처만 맞으면 쓸 수 있는 권리인가 — 교육부 귀속·확정, 공공누리 모든 유형(제0~4·AI). 유형 미상·미확인은 아님.
    (2026-11-21: 제2·3·4유형도 쓸 수 있게 — 유형 조건(상업 금지·변경 금지)은 쓰는 사람이 지킨다)"""
    status = rights_status or ""
    return status in ("확정", EDU) or status.startswith("공공누리 제") or status == "공공누리 AI유형"


def _records(paths) -> list[dict]:
    out = []
    for path in map(Path, paths):
        files = sorted((path / "modules").glob("*.jsonl")) if path.is_dir() else [path]
        for file in files:
            for line in file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    record["_root"] = str((path if path.is_dir() else file.parent).resolve())
                    out.append(record)
    return out


def build(paths, db_path: Path, *, origin: str = "기존 학습모듈") -> dict:
    """009 결과(폴더 또는 jsonl) → 스텁 DB. 같은 (image_id, 모듈, 그림 번호)는 덮어쓴다."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    added, skipped = 0, 0
    with sqlite3.connect(db_path) as con:
        if con.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            con.execute("DROP TABLE IF EXISTS images")          # 칸이 바뀐 옛 DB는 새로 만든다
            con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.executescript(SCHEMA)
        for record in _records(paths):
            if not record.get("image_id") or not record.get("phash"):
                skipped += 1
                continue
            source = record.get("source")
            status, license_type, basis = rights_of(source)
            image_file = record.get("image_file")
            image_path = str(Path(record["_root"]) / image_file) if image_file else None
            module_default = (record.get("module") or {}).get("code")
            for use in record.get("uses") or []:
                module = use.get("module") or module_default or use.get("file") or "?"
                llm = record.get("llm") or {}
                con.execute("INSERT OR REPLACE INTO images VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    record["image_id"], module, record["phash"], use.get("figure_label") or "", use.get("figure_title"),
                    use.get("lesson"), (source or {}).get("kind"), use.get("source_text") or (source or {}).get("text"),
                    (source or {}).get("cited_module"), (source or {}).get("cited_page"), (source or {}).get("kogl_type"),
                    status, license_type, basis, image_path, origin, time.strftime("%Y-%m-%dT%H:%M:%S"),
                    use.get("element_code"), use.get("element_name"), " ".join(llm.get("keywords") or []), llm.get("image_type")))
                added += 1
        total = con.execute("SELECT COUNT(*), COUNT(DISTINCT image_id), COUNT(DISTINCT module) FROM images").fetchone()
    return {"넣은 줄": added, "건너뜀(그림 없음)": skipped, "DB 줄": total[0], "DB 그림": total[1], "DB 모듈": total[2], "db": str(db_path)}


def default_db_path() -> Path:
    """FIG_DB가 있으면 그것, 없으면 저장소 결과/figure_db.sqlite."""
    import os
    env = os.getenv("FIG_DB", "").strip()
    return Path(env) if env else Path(__file__).resolve().parents[2] / "결과" / "figure_db.sqlite"


def open_lookup(path=None):
    """경로를 주면 그 DB(없으면 오류), 안 주면 기본 경로에 DB가 있을 때만 연다(없으면 None = ④ 미실행)."""
    if path:
        return StubLookup(Path(path))
    target = default_db_path()
    return StubLookup(target) if target.is_file() else None


class StubLookup:
    """Resources.lookup 자리에 들어가는 대조기. 010 DB가 생기면 같은 find()를 가진 클래스로 바꾼다."""

    def __init__(self, db_path: Path, *, near: int = 10):
        self.db_path = Path(db_path)
        if not self.db_path.is_file():
            raise ValueError(f"이미지 DB가 없습니다: {self.db_path} — python -m ncs_figures db build 로 만드세요")
        self.near = near
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            self.rows = [dict(r) for r in con.execute("SELECT * FROM images")]
        self.by_id: dict[str, list[dict]] = {}
        for row in self.rows:
            self.by_id.setdefault(row["image_id"], []).append(row)
        self.name = f"스텁 DB({self.db_path.name}, 그림 {len(self.by_id)}개)"

    def _gram_weights(self) -> dict[str, float]:
        """조각마다 드문 정도(IDF) — DB 그림 제목 중 몇 개에 나오나. 한 번 계산해 둔다."""
        if getattr(self, "_weights", None) is None:
            import math
            df: dict[str, int] = {}
            titled = [r for r in self.rows if r["figure_title"]]
            for row in titled:
                for g in _grams(_words(f"{row['figure_title']} {row['keywords'] or ''}")):
                    df[g] = df.get(g, 0) + 1
            n = max(1, len(titled))
            self._weights = {g: math.log((n + 1) / (c + 0.5)) for g, c in df.items()}
            self._max_weight = math.log((n + 1) / 0.5)
        return self._weights

    def size(self) -> dict:
        return {"그림": len(self.by_id), "줄": len(self.rows), "모듈": len({r["module"] for r in self.rows}), "db": str(self.db_path)}

    def row(self, image_id: str) -> dict | None:
        rows = self.by_id.get(image_id)
        return rows[0] if rows else None

    def similar(self, title: str, keywords=(), *, exclude_image: str | None = None, exclude_module: str = "",
                k: int = 3, minimum: float = 0.25) -> list[dict]:
        """같은 주제(태그)의 DB 그림 — 저작권이 문제이거나 오래된 그림을 바꿔 쓸 후보.

        주제 = 캡션 제목 + (있으면) 판독 키워드. 두 글자씩 끊은 조각이 얼마나 겹치는지(자카드)로 잰다 — 한국어는 띄어쓰기·조사가
        달라도 '구성도', '시스템' 같은 말이 같은 조각으로 겹친다. 재사용 가능한 권리(교육부 귀속·공공누리 제N유형)를 먼저 보인다.
        모델·외부 전송 없음. 다음 단계: 의미 벡터(SigLIP 2·bge-m3)로 말이 달라도 뜻이 같은 그림까지.
        """
        query = _words(f"{title} {' '.join(keywords)}")
        if not query:
            return []
        grams = _grams(query)
        weight = self._gram_weights()
        skip = (exclude_module or "")[:12]
        seen, out = set(), []
        for row in self.rows:
            if row["image_id"] == exclude_image or (skip and row["module"][:12] == skip) or row["image_id"] in seen:
                continue
            words = _words(f"{row['figure_title'] or ''} {row['keywords'] or ''}")
            if not words:
                continue
            other = _grams(words)
            # 흔한 조각('SW제품'·'프로세스'·'사례')은 가볍게 — DB 안에서 드문 말이 겹칠수록 같은 주제
            union = sum(weight.get(g, self._max_weight) for g in grams | other)
            score = sum(weight.get(g, self._max_weight) for g in grams & other) / union if union else 0.0
            if score < minimum:
                continue
            seen.add(row["image_id"])
            common = [w for w in query if any(w in x or x in w for x in words) and len(w) >= 2]
            out.append({**{key: row[key] for key in ("image_id", "module", "figure_label", "figure_title", "source_text",
                                                      "source_kind", "rights_status", "element_name")},
                        "score": round(score, 3), "common": list(dict.fromkeys(common))[:5], "licensed": licensed(row["rights_status"])})
        out.sort(key=lambda c: (not c["licensed"], -c["score"]))
        return out[:k]

    def find(self, image_id: str | None, phash: str | None, *, exclude_module: str = "", k: int = 5) -> list[tuple[Match, dict]]:
        """(Match, DB 줄) 목록 — 완전 일치 먼저, 그다음 해밍 거리 순. exclude_module(검수 중인 원고의 모듈)은 뺀다."""
        found: dict[tuple[str, str, str], tuple[Match, dict]] = {}
        skip = (exclude_module or "")[:12]      # 'LM' + 10자리 — 판(_19v4)이 달라도 같은 모듈이면 뺀다
        for row in self.rows:
            if skip and row["module"][:12] == skip:
                continue
            if image_id and row["image_id"] == image_id:
                kind, score = "exact", 1.0
            elif phash and row["phash"]:
                distance = hamming(phash, row["phash"])
                if distance > self.near:
                    continue
                kind, score = "near", round(1 - distance / 64, 3)
            else:
                continue
            match = Match(image_id=row["image_id"], match_type=kind, score=score,
                          source_ref=f"{row['module']} {row['figure_label'] or ''}".strip(),
                          license_type=row["license_type"], reuse_scope=None, rights_status=row["rights_status"],
                          module=row["module"], figure_label=row["figure_label"] or None, figure_title=row["figure_title"],
                          source_text=row["source_text"], source_kind=row["source_kind"], rights_basis=row["rights_basis"])
            found[(row["image_id"], row["module"], row["figure_label"])] = (match, row)
        ordered = sorted(found.values(), key=lambda pair: (pair[0].match_type != "exact", -pair[0].score))
        return ordered[:k]
