"""005 원고 이미지 검수 흐름 — prepare_figures(그림 맥락·식별·종류·출처 해석·전송 표시) → review_figures(점검·위험도) → run_review.

결과 저장(save_result)은 JSON·검수표(HTML)·03-003 기록까지. 메모 원고는 상위 계층(CLI·웹)이 ncs_service.annotate로 만든다
— 이 패키지는 ncs_service를 import하지 않는다.
"""

from __future__ import annotations

import json
import random
import string
import time
from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.figure_context import figure_contexts
from ncs_core.module_code import resolve_module_code
from ncs_core.source_line import parse_ai_marker, parse_source

from .checks import CHECKS, run_checks
from .config import DEFAULT_CONFIG, FigureConfig
from .ids import file_sha256, image_id, phash
from .models import FigureItem, FigureReview, FigureReviewResult, Resources
from .reading import read_figure
from .report import write_html
from .risk import DEFAULT_RULES, assess
from .rows import summarize, to_row
from .select import classify, transfer_of
from .templates import load_templates
from .vision import cost

REPORT_NAME = "이미지검수"


def prepare_figures(document, *, cfg: FigureConfig = DEFAULT_CONFIG, templates: frozenset[str] | None = None,
                    overrides: dict[str, str] | None = None) -> list[FigureItem]:
    """그림 자리마다 FigureItem. overrides: {image_id: 전송 표시} — 사람이 정한 값."""
    if templates is None:
        templates = load_templates(cfg.templates_path)
    overrides = overrides or {}
    items = []
    for ctx in figure_contexts(document, lookback=cfg.lookback):
        key = image_id(ctx.data)
        source = parse_source(ctx.source_line) if ctx.source_line else None
        transfer, why = transfer_of(source, cfg, override=overrides.get(key or ""))
        items.append(FigureItem(
            ctx=ctx, image_id=key, file_sha256=file_sha256(ctx.data), phash=phash(ctx.data),
            kind=classify(ctx, key, templates=templates, cfg=cfg), source=source,
            ai=parse_ai_marker(ctx.ai_marker_line) if ctx.ai_marker_line else None,
            transfer=transfer, transfer_reason=why,
        ))
    return items


def review_figures(items: list[FigureItem], resources: Resources = Resources(), *, cfg: FigureConfig = DEFAULT_CONFIG,
                   checks=CHECKS, rules=DEFAULT_RULES, read: bool = False, module_name: str = "",
                   module_code: str = "") -> list[FigureReview]:
    """read=True이고 그림 모델(resources.asker)이 있으면 점검 대상 그림마다 판독(유형·설명·글자·키워드·맥락 요약)도 한다."""
    reviews = []
    if getattr(resources, "marks", None) is not None and hasattr(resources.marks, "prefetch"):
        resources.marks.prefetch([i for i in items if i.kind not in ("양식", "양식 후보")])   # OCR은 한 번에
    for item in items:
        if item.kind in ("양식", "양식 후보"):
            reviews.append(FigureReview(item=item, checks=()))
            continue
        outcomes, prior = run_checks(item, resources, cfg, checks, module_name=module_name, module_code=module_code)
        matches = tuple(prior.get("matches", ()))
        risk, reasons = assess(outcomes, matches, item, rules=rules, required=cfg.required_checks, prior=prior)
        reading = read_figure(item, resources.asker, module_name=module_name) if read and resources.asker is not None else None
        reviews.append(FigureReview(item=item, checks=tuple(outcomes), matches=matches, risk=risk, risk_reasons=reasons,
                                    reading=reading, model_calls=tuple(prior.get("model_calls", ())),
                                    replacements=tuple(replacements_for(item, resources, module_code, reading))))
    return reviews


def replacements_for(item: FigureItem, resources: Resources, module_code: str, reading: dict | None) -> list[dict]:
    """그림 DB에서 같은 주제(캡션 제목 + 판독 키워드)의 그림 — 저작권 문제·오래된 그림을 바꿔 쓸 후보. 판정에는 안 쓴다."""
    lookup = getattr(resources, "lookup", None)
    title = item.ctx.figure_title or ""
    if lookup is None or not hasattr(lookup, "similar") or not title:
        return []
    keywords = (reading or {}).get("키워드") or []
    return lookup.similar(title, keywords, exclude_image=item.image_id, exclude_module=module_code)


def model_usage(reviews: list[FigureReview]) -> dict:
    """모델 호출 수·새 호출·토큰·비용(추정)."""
    calls = [c for r in reviews for c in (*r.model_calls, *([r.reading] if r.reading else ())) if c.get("status") == "완료"]
    fresh = [c for c in calls if not c.get("cached")]
    total = {"호출": len(calls), "새 호출": len(fresh), "입력 토큰": sum(c["usage"].get("input", 0) for c in fresh),
             "출력 토큰": sum(c["usage"].get("output", 0) for c in fresh)}
    costs = [cost(c["model"], c["usage"]) for c in fresh]
    total["비용(USD, 추정)"] = round(sum(x for x in costs if x), 4) if fresh else 0.0
    total["모델"] = sorted({c["model"] for c in calls})
    return total


def run_review(manuscript: Path, *, resources: Resources | None = None, cfg: FigureConfig = DEFAULT_CONFIG,
               module_code: str = "", read: bool = False) -> FigureReviewResult:
    document = load_document(manuscript)
    if document.format not in ("hwpx", "hwp"):
        raise ValueError("그림 검수는 hwpx·hwp 원고만 읽습니다")
    started = time.perf_counter()
    resources = resources or Resources()
    items = prepare_figures(document, cfg=cfg)
    try:
        code = resolve_module_code(Path(manuscript), module_code)
    except ValueError:
        if module_code:
            raise                   # 직접 준 코드가 틀리면 알린다
        code = ""                   # 파일명에 코드가 없어도 그림 검수는 한다(결과 폴더는 '코드없음')
    reviews = review_figures(items, resources, cfg=cfg, read=read, module_name=Path(manuscript).stem, module_code=code)
    rows = [to_row(r) for r in reviews if r.risk is not None]
    rows.sort(key=lambda row: (("고위험", "확인 필요", "문제없음", "판정 안 함").index(row["위험도"]), row["item_id"]))
    if resources.link is not None:
        for row in rows:
            if row["03-003 연계"]:
                resources.link.notify(row)
    summary = summarize(reviews)
    summary["모델 사용"] = model_usage(reviews)
    if resources.submissions is not None:      # ⑥⑦ 목록에는 있는데 원고에 없는 그림(누락·번호 불일치)
        labels = {r.item.ctx.figure_label for r in reviews if r.item.ctx.figure_label}
        summary["목록에만 있음"] = resources.submissions.unmatched(labels)
    diagnostics = {"구역 맞춤": getattr(document, "layout", None), "시간(초)": round(time.perf_counter() - started, 1),
                   "자원": {name: getattr(resources, name) is not None for name in ("lookup", "scorer", "sscd", "semantic", "asker", "marks", "submissions", "link", "sink")},
                   "그림 모델": getattr(resources.asker, "name", None)}
    return FigureReviewResult(module_code=code, reviews=tuple(reviews), rows=rows, summary=summary, diagnostics=diagnostics)


def result_dir(out_dir: Path, module_code: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tail = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return Path(out_dir) / f"{module_code or '코드없음'}_{stamp}_{REPORT_NAME}_{tail}"


def save_result(result: FigureReviewResult, out_dir: Path, *, title: str = "") -> Path:
    """<out>/<코드>_<시각>_이미지검수_xxxx/ 에 rows.json·summary.json·diagnostics.json·검수표.html."""
    folder = result_dir(out_dir, result.module_code)
    folder.mkdir(parents=True, exist_ok=True)
    prefix = f"{result.module_code or '코드없음'}_{REPORT_NAME}"
    for name, value in (("행", result.rows), ("요약", result.summary), ("진단", result.diagnostics)):
        (folder / f"{prefix}_{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_html(result, folder / f"{prefix}_검수표.html", title=title or result.module_code)
    return folder
