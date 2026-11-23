"""그림 종류 분류(설계 8.1)와 외부 전송 표시(설계 5.7). 판정 없음."""

from __future__ import annotations

from ncs_core.figure_context import FigureContext
from ncs_core.source_line import SourceInfo

from .config import FigureConfig


def classify(ctx: FigureContext, image_id: str | None, *, templates: frozenset[str], cfg: FigureConfig) -> str:
    """양식 / 양식 후보 / 본문 그림 / 캡션 없는 그림."""
    if image_id and image_id in templates:
        return "양식"
    if ctx.figure_label:
        return "본문 그림"
    w, h = ctx.mm
    if (w >= cfg.page_size_mm[0] and h >= cfg.page_size_mm[1]) or (h and h <= cfg.banner_max_height_mm):
        return "양식 후보"
    return "캡션 없는 그림"


def transfer_of(source: SourceInfo | None, cfg: FigureConfig, *, override: str | None = None) -> tuple[str, str]:
    """(허용·금지·확인 전, 이유). 사람이 정한 값이 먼저. 원고 단위 반출 승인(LLM_ALLOW_UPLOAD·LLM_ALLOW_IMAGE_UPLOAD)은
    LLM 호출 쪽(ncs_core.llm)이 따로 본다.

    2026-11-21 결정: 출처 종류와 상관없이 모든 그림을 보낸다(전에는 공공누리 제0·1·AI유형만).
    다시 막아야 하면 FIG_TRANSFER_OTHERS=확인 전(또는 금지).
    """
    if override:
        return override, "사람이 정함"
    what = "출처 줄 없음" if source is None else (f"공공누리 {source.kogl_type}유형" if source.kind == "공공누리" and source.kogl_type else source.kind)
    if cfg.transfer_others != "허용":
        return cfg.transfer_others, f"{what} — FIG_TRANSFER_OTHERS={cfg.transfer_others}로 막아 둠"
    return "허용", f"{what} — 모든 그림 전송"
