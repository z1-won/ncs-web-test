"""결과 행(엔진 체크리스트 행과 같은 모양 + 위험도 칸)과 원고 요약. 메모 원고(ncs_service.annotate)·화면이 이 행을 그대로 쓴다."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict

from ncs_core.text import TRI, X, verdict

from .models import FigureReview

LEVELS = ("고위험", "확인 필요", "문제없음", "판정 안 함")



def _around(lines, ctx) -> list[str]:
    """앞·뒤 문단에서 그림 자신의 캡션·출처 줄·AI 표기 줄을 뺀다(주변 글은 그림 밖의 글만)."""
    squash = lambda s: "".join((s or "").split())  # noqa: E731
    own = [squash(x) for x in (ctx.caption, ctx.source_line, ctx.ai_marker_line) if x]
    keep = []
    for line in lines:
        text = squash(line)
        if any(o and o in text and len(text) - len(o) < 15 for o in own):
            continue
        keep.append(line)
    return keep

def item_id(review: FigureReview) -> str:
    return f"IMG-s{review.item.ctx.section}-p{review.item.ctx.para}"


def to_row(review: FigureReview) -> dict:
    item, ctx = review.item, review.item.ctx
    checks = {c.name: c.value for c in review.checks if c.value is not None}
    notes = {c.name: c.note for c in review.checks if c.value is not None and c.note}
    suggestions = [c.suggestion for c in review.checks if c.value in (X, TRI) and c.suggestion]
    source = item.source
    return {
        "item_id": item_id(review),
        "region_path": ctx.region_path,
        "원고": ctx.caption or f"문단 {ctx.para}의 그림",
        "그림 종류": item.kind,
        "체크": checks,
        "판정": verdict(checks),
        "비고": notes,
        "수정 제안": " / ".join(dict.fromkeys(suggestions)) or None,
        "미실행": [f"{c.name}({c.skipped})" for c in review.checks if c.value is None],
        "출처 해석": None if source is None else {
            "source_kind": source.kind, "author": source.author, "year": source.year, "url": source.url,
            "checked_date": source.checked_date, "cited_module": source.cited_module, "page": source.cited_page,
            "kogl_type": source.kogl_type, "text": source.text},
        "AI 표기": None if item.ai is None else asdict(item.ai),
        "위험도": review.risk,
        "위험 근거": list(review.risk_reasons),
        "03-003 연계": review.risk in ("확인 필요", "고위험"),
        "DB 후보": [asdict(m) for m in review.matches],
        "대체 후보": list(review.replacements),
        "image_id": item.image_id,
        "외부 전송": {"값": item.transfer, "이유": item.transfer_reason},
        "그림": {"px": list(ctx.px), "mm": list(ctx.mm), "dpi": ctx.dpi, "format": ctx.format, "표 안": ctx.in_table, "그림 틀": ctx.in_frame},
        "문맥": {"캡션": ctx.caption, "본문 참조": list(ctx.references), "앞": _around(ctx.before, ctx), "뒤": _around(ctx.after, ctx),
                "표": list(ctx.table_context)},
        "판독": None if review.reading is None else {k: v for k, v in review.reading.items() if k not in ("usage",)},
    }


def summarize(reviews: list[FigureReview], *, total: int | None = None) -> dict:
    kinds = Counter(r.item.kind for r in reviews)
    checked = [r for r in reviews if r.risk is not None]
    levels = Counter(r.risk for r in checked)
    by_check: dict[str, list[int]] = {}
    skipped: Counter = Counter()
    for review in checked:
        for c in review.checks:
            if c.value is None:
                skipped[f"{c.name}({c.skipped})"] += 1
                continue
            counts = by_check.setdefault(c.name, [0, 0])
            counts[0] += c.value == X
            counts[1] += c.value == TRI
    need = [r for r in checked if r.risk in ("확인 필요", "고위험")]
    return {
        "그림": total if total is not None else len(reviews),
        "양식 제외": kinds.get("양식", 0), "양식 후보": kinds.get("양식 후보", 0), "검수 대상": len(checked),
        "위험도": {level: levels.get(level, 0) for level in LEVELS},
        "확인 필요 이상 중 캡션 없는 그림": sum(1 for r in need if r.item.kind == "캡션 없는 그림"),
        "체크별 X/△": by_check,
        "미실행": dict(skipped),
    }
