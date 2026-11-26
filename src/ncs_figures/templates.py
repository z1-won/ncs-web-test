"""양식 그림 목록 — 여러 학습모듈에 똑같이 들어간 띠 배너·표지 같은 양식 그림. 검수·태깅 대상에서 뺀다.

목록 파일(TSV): image_id, 가로mm, 세로mm, 원고 수, 처음 본 원고, 설명. 사람 검수를 통과한 최종본 폴더에서
build_templates로 만들고(두 개 이상의 서로 다른 학습모듈에 같은 image_id), 손으로 줄을 더할 수 있다.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

HEADER = ["image_id", "가로mm", "세로mm", "원고 수", "처음 본 원고", "설명"]


def load_templates(path: Path) -> frozenset[str]:
    if not path.is_file():
        return frozenset()
    with open(path, encoding="utf-8-sig", newline="") as f:
        return frozenset(row["image_id"] for row in csv.DictReader(f, delimiter="\t") if row.get("image_id"))


def template_checker(path: Path | None = None):
    """그림 파일 바이트 → 양식 그림 목록에 있는가(읽지 못한 그림은 False). 권리 증빙 점검이 캡션 없는 그림에서 양식 그림을 뺄 때 웹 층이 받아 넘긴다."""
    from .config import DEFAULT_CONFIG
    from .ids import image_id

    known = load_templates(path or DEFAULT_CONFIG.templates_path)
    return lambda data: image_id(data) in known


def build_templates(paths: list[Path], *, min_modules: int = 2) -> list[dict]:
    """최종본 원고들에서 양식 그림 후보. 캡션 없는 그림만 본다(캡션이 있으면 본문 그림)."""
    from ncs_core.documents import load_document
    from ncs_core.figure_context import figure_contexts

    from .ids import image_id

    seen: dict[str, dict] = {}
    modules: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        document = load_document(path)
        for ctx in figure_contexts(document, structure={}):   # 위치는 필요 없음 — 구조 읽기 생략
            if ctx.figure_label:
                continue
            key = image_id(ctx.data)
            if key is None:
                continue
            modules[key].add(path.name)
            seen.setdefault(key, {"image_id": key, "가로mm": ctx.mm[0], "세로mm": ctx.mm[1], "처음 본 원고": path.name})
    out = []
    for key, info in seen.items():
        if len(modules[key]) >= min_modules:
            w, h = info["가로mm"], info["세로mm"]
            shape = "쪽 전체" if w >= 200 and h >= 280 else "띠(배너)" if h <= 15 else "그 밖"
            out.append({**info, "원고 수": len(modules[key]), "설명": f"{shape} — 최종본 {len(modules[key])}개 원고 공통"})
    return sorted(out, key=lambda r: (-r["원고 수"], r["image_id"]))


def write_templates(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
