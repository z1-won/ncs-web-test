"""출처 목록 추출 — 그림·표·본문 출처 줄을 하나의 목록으로. 참고 자료 항목은 참고 자료 엔진이 읽은 것을 그대로 쓴다."""

from __future__ import annotations

import re

from ncs_core.source_line import CAPTION_START, SRC_HEAD, parse_ai_marker, parse_source

TABLE_CAPTION = re.compile(r"^[\[〈<]\s*표\s*(\d+)\s*-\s*(\d+)\s*[\]〉>]\s*(.*)$")   # 최종본은 '<표 1-1> 제목'
FIGURE_CAPTION = re.compile(r"^\[\s*그림\s*(\d+)\s*-\s*(\d+)\s*\]\s*(.*)$")
TABLE_LOOKAHEAD = 80          # 필요 지식 ⑧과 같은 값: 표 캡션 아래 몇 문단 안에서 출처 줄을 찾는가
FIGURE_BELOW = 3              # 출처 줄 아래 이만큼 안에 그림 캡션이 오면 그 그림의 출처


def _strip(text: str) -> str:
    return (text or "").strip()


def figure_sources(document) -> list[dict]:
    """캡션 있는 본문 그림마다 출처 줄·AI 활용 줄·캡션의 위치와 내용(그림 맥락 모듈이 이미 찾은 것)."""
    from ncs_core.figure_context import figure_contexts

    out = []
    for ctx in figure_contexts(document):
        if not ctx.caption:
            continue                      # 캡션 없는 그림(아이콘 등)은 005에서 본다
        out.append({
            "kind": "그림", "label": ctx.figure_label, "title": ctx.figure_title, "caption": ctx.caption,
            "section": ctx.section, "caption_para": ctx.caption_para, "source_para": ctx.source_para,
            "source_line": ctx.source_line, "ai_para": ctx.ai_marker_para, "ai_line": ctx.ai_marker_line,
            "region": " > ".join(p for p in ctx.region_path.split(" > ") if not p.startswith("section")) or "본문",
            "lesson": ctx.lesson,
        })
    return out


def table_sources(document, section: int = 1) -> list[dict]:
    """표 캡션([표 N-M])마다 표 아래 첫 '출처:' 줄(필요 지식 ⑧과 같은 규칙). 바로 아래에 그림 캡션이 오면 그 그림의 것."""
    if section >= len(document.sections):
        return []
    paragraphs = document.sections[section]
    out = []
    for p, text in enumerate(paragraphs):
        m = TABLE_CAPTION.match(_strip(text))
        if not m:
            continue
        src = ai = None
        for i in range(p + 1, min(p + 1 + TABLE_LOOKAHEAD, len(paragraphs))):
            line = _strip(paragraphs[i])
            if line and CAPTION_START.match(line):
                break
            if line and SRC_HEAD.match(line):
                below = [_strip(paragraphs[j]) for j in range(i + 1, min(i + 1 + FIGURE_BELOW, len(paragraphs)))]
                if not any(FIGURE_CAPTION.match(b) for b in below):
                    src = i
                    ai = next((j for j in range(i + 1, min(i + 3, len(paragraphs))) if parse_ai_marker(paragraphs[j] or "")), None)
                break
        out.append({
            "kind": "표", "label": f"표 {m.group(1)}-{m.group(2)}", "title": m.group(3).strip() or None, "caption": _strip(text),
            "section": section, "caption_para": p, "source_para": src, "source_line": _strip(paragraphs[src]) if src is not None else None,
            "ai_para": ai, "ai_line": _strip(paragraphs[ai]) if ai is not None else None,
            "region": f"학습 {m.group(1)} > <표 {m.group(1)}-{m.group(2)}>", "lesson": int(m.group(1)),
        })
    return out


def body_sources(document, used: set[tuple[int, int]], *, section: int = 1, end: int | None = None) -> list[dict]:
    """그림·표에 붙지 않은 본문의 '출처:' 줄 — 어문 자료(문장·문단) 인용의 출처. 참고 자료 구역 이후는 보지 않는다."""
    if section >= len(document.sections):
        return []
    paragraphs = document.sections[section]
    aside = document.section_aside_paragraphs(section) or frozenset()
    stop = end if end is not None else len(paragraphs)
    out = []
    for i in range(stop):
        line = _strip(paragraphs[i])
        if not line or i in aside or (section, i) in used or not SRC_HEAD.match(line):
            continue
        before = next((_strip(paragraphs[j]) for j in range(i - 1, max(-1, i - 4), -1) if _strip(paragraphs[j])), "")
        out.append({
            "kind": "본문", "label": None, "title": None, "caption": None, "section": section, "caption_para": None,
            "source_para": i, "source_line": line, "ai_para": None, "ai_line": None,
            "region": f"{i + 1:,}번째 문단", "lesson": None, "before": before,
        })
    return out


def attach(entry: dict) -> dict:
    """출처 줄·AI 활용 줄을 읽어 붙인다."""
    line = entry.get("source_line")
    entry["source"] = parse_source(line) if line else None          # '출처:' 머리말까지 넣어야 머리말 모양도 본다
    entry["ai"] = parse_ai_marker(entry["ai_line"]) if entry.get("ai_line") else None
    return entry
