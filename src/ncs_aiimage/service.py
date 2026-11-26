"""AI 활용 표기와 결과물 현황의 묶음 — 화면(ncs_web.routes.aiimage)이 부른다.

  inspect      원고의 그림 목록(그림 번호, 그림명, 출처 줄, 이미 있는 AI 표기, 출력본의 쪽)과 유의 안내
  preview      넣으려는 표기를 합쳐 그림마다 표기 세 줄과 결과물 현황 줄을 미리 만든다(원고는 바꾸지 않는다)
  marked_copy  표기를 넣은 원고 사본(hwpx)
  source_copy  출처 줄이 없는 그림에 출처 줄을 넣은 원고 사본(hwpx) — 이미지 추천의 출처 문구를 원고에 넣을 때
넣으려는 표기(marks)는 [{'key': '구역:문단', 'tool', 'mode', 'date': 'YYYY-MM-DD', 'source'(선택)}] — 화면이 inspect의 key를 그대로 돌려준다.
source: 출처 줄이 없는 그림에 AI 활용 줄과 함께 넣을 출처 줄('출처: 집필진 제작(2026)'처럼 사용자가 고르거나 적은 것). 지어내지 않는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.source_line import kogl_terms
from ncs_core.figures import MODE_WORDS, ai_line, clean_tool, figure_pages, manuscript_figures, marking_lines
from ncs_core.pictures import picture_records, pictures_by_caption

from .marking import Mark, clean_source, insert_marks, insert_source_line
from .notice import BASIS, NOTICE
from .results import HEAD, result_rows

MAX_MARKS = 500


def _read_pages(print_copy: str | Path | None) -> tuple[dict | None, str]:
    """(그림 번호 → 쪽, 알림). 출력본을 읽지 못해도 그림 목록과 표기는 그대로 만든다."""
    if not print_copy:
        return None, ""
    from ncs_core.pdf import load_pdf

    try:
        return figure_pages(load_pdf(print_copy)), ""
    except ValueError as error:      # PDF가 아님, 글자를 못 뽑음, pypdf 없음
        return None, f"출력본 PDF를 읽지 못해 쪽수는 비워 둡니다: {error}"


def _day(value) -> str:
    return f"{value.year}. {value.month}. {value.day}." if value else ""


def _rows(document, pages: dict | None) -> list[dict]:
    figures = manuscript_figures(document)
    paired = pictures_by_caption(picture_records(document), [(f.section, f.para) for f in figures]) if document.format == "hwpx" else {}
    rows = []
    for figure in figures:
        places = (pages or {}).get(figure.label, []) if figure.minor is not None else []
        rows.append({
            "key": f"{figure.section}:{figure.para}", "구역": figure.section, "문단": figure.para,
            "그림 번호": figure.label, "뒤 번호": figure.minor, "그림명": figure.title, "출처 줄": figure.source_line,
            "공공누리": kogl_terms(figure.source_line),      # 출처 줄에 적힌 유형과 조건 — 변경금지(제3·4유형)는 AI 표기 대상에서 뺀다
            "AI 표기": None if figure.ai is None else {"도구": figure.ai.tool, "방식": figure.ai.mode, "일자": _day(figure.ai.on), "글": figure.ai.text},
            "쪽": [str(place["쪽"]) for place in places if place.get("쪽")],
            "그림 파일": (figure.section, figure.para) in paired,
        })
    return rows


def parse_marks(marks: list, rows: list[dict]) -> list[Mark]:
    """화면이 보낸 표기 목록 → Mark. 형식이 틀리면 ValueError(화면에 그대로 보일 말)."""
    if not isinstance(marks, list):
        raise ValueError("넣을 표기는 목록이어야 합니다")
    if len(marks) > MAX_MARKS:
        raise ValueError(f"표기는 한 번에 {MAX_MARKS}개까지 넣을 수 있습니다")
    known = {row["key"]: row for row in rows}
    parsed, seen = [], set()
    for item in marks:
        if not isinstance(item, dict) or item.get("key") not in known:
            raise ValueError("원고에 없는 그림을 골랐습니다. 그림을 다시 읽어 주세요")
        row = known[item["key"]]
        if item["key"] in seen:
            raise ValueError(f"{row['그림 번호']}을(를) 두 번 골랐습니다")
        seen.add(item["key"])
        try:
            tool = clean_tool(str(item.get("tool") or ""))
            on = date.fromisoformat(str(item.get("date") or ""))
        except ValueError as error:
            message = str(error) if "AI 도구" in str(error) else "활용 일자는 YYYY-MM-DD 날짜여야 합니다"
            raise ValueError(f"{row['그림 번호']}: {message}") from None
        if item.get("mode") not in MODE_WORDS:
            raise ValueError(f"{row['그림 번호']}: 활용 방식을 골라 주세요(생성함 또는 수정 보완함)")
        source = ""
        if str(item.get("source") or "").strip():
            if row["출처 줄"]:
                raise ValueError(f"{row['그림 번호']}: 이미 출처 줄이 있어 출처 줄을 넣지 않습니다")
            try:
                source = clean_source(str(item["source"]))
            except ValueError as error:
                raise ValueError(f"{row['그림 번호']}: {error}") from None
        parsed.append(Mark(row["구역"], row["문단"], tool, item["mode"], on, source))
    return parsed


LOCKED_BASIS = "REQ-02-006 ⑥: 공공누리 제3·4유형(변경금지) 원본은 AI 수정 보완·생성의 재료에서 제외"


def split_locked(marks: list[Mark], rows: list[dict]) -> tuple[list[Mark], list[dict]]:
    """(넣어도 되는 표기, 변경금지 원본이라 뺀 것 [{'그림', '이유'}]). 출처 줄에 공공누리 제3·4유형이 적힌 그림에는 AI 활용 표기를 넣지 않는다.
    함께 넣으려는 출처 줄(Mark.source)에 그 유형이 적혀 있어도 같다."""
    by_place = {(row["구역"], row["문단"]): row for row in rows}
    allowed, locked = [], []
    for mark in marks:
        row = by_place.get((mark.section, mark.para)) or {}
        terms = row.get("공공누리") or (kogl_terms(mark.source) if mark.source else None)
        if terms and terms["변경금지"]:
            locked.append({"그림": row["그림 번호"], "이유": f"출처가 {terms['이름']}(변경금지) — AI 수정 보완·생성에 쓸 수 없는 원본입니다({LOCKED_BASIS})"})
        else:
            allowed.append(mark)
    return allowed, locked


def inspect(manuscript: str | Path, *, print_copy: str | Path | None = None) -> dict:
    """원고의 그림 목록과 유의 안내. hwp도 읽지만 표기를 넣은 사본은 hwpx 원고에서만 만든다."""
    document = load_document(manuscript)
    pages, note = _read_pages(print_copy)
    rows = _rows(document, pages)
    return {
        "원고": Path(manuscript).name, "형식": document.format, "표기 넣기": document.format == "hwpx",
        "출력본": Path(print_copy).name if print_copy and pages is not None else None,
        "그림": rows,
        "요약": {"그림": len(rows), "AI 표기 있음": sum(1 for row in rows if row["AI 표기"]),
                 "출처 줄 없음": sum(1 for row in rows if not row["출처 줄"])},
        "유의 안내": {"근거": BASIS, "항목": list(NOTICE)},
        "알림": [text for text in (note, "" if document.format == "hwpx" else "hwp 원고에는 표기를 넣지 못합니다. 한글에서 hwpx로 저장해 올리면 넣을 수 있습니다.") if text],
        "오늘": date.today().isoformat(),
    }


def preview(manuscript: str | Path, marks: list, *, print_copy: str | Path | None = None) -> dict:
    """넣으려는 표기를 합친 모습 — 그림마다 표기 세 줄, 그리고 결과물 현황 줄(이미 있는 표기 + 넣을 표기)."""
    document = load_document(manuscript)
    pages, note = _read_pages(print_copy)
    rows = _rows(document, pages)
    allowed, locked = split_locked(parse_marks(marks, rows), rows)
    by_place = {(mark.section, mark.para): mark for mark in allowed}
    lines, skipped = [], []
    for row in rows:
        mark = by_place.get((row["구역"], row["문단"]))
        if mark is None:
            continue
        if row["AI 표기"]:
            skipped.append(row["그림 번호"])
            continue
        row["AI 표기"] = {"도구": mark.tool, "방식": mark.mode, "일자": _day(mark.on), "글": ai_line(mark.tool, mark.mode, mark.on), "예정": True}
        lines.append({"key": row["key"], "그림": row["그림 번호"],
                      "줄": marking_lines(source_line=row["출처 줄"] or mark.source, tool=mark.tool, mode=mark.mode, on=mark.on, label=row["그림 번호"], title=row["그림명"]),
                      "출처 줄 없음": not (row["출처 줄"] or mark.source), "출처 줄 넣음": bool(mark.source and not row["출처 줄"])})
    return {"원고": Path(manuscript).name, "표기": lines, "이미 있음": skipped, "변경금지 원본 제외": locked, "현황 머리": list(HEAD),
            "현황": result_rows(rows, pages), "쪽수": pages is not None, "알림": [note] if note else []}


def marked_copy(manuscript: str | Path, marks: list) -> tuple[bytes, dict]:
    """표기를 넣은 원고 사본(hwpx)과 요약(insert_marks의 요약)."""
    document = load_document(manuscript)
    if document.format != "hwpx":
        raise ValueError("hwp 원고에는 표기를 넣지 못합니다. 한글에서 hwpx로 저장해 다시 올려 주세요")
    rows = _rows(document, None)
    parsed, locked = split_locked(parse_marks(marks, rows), rows)
    if not parsed and locked:
        raise ValueError("고른 그림이 모두 변경금지 원본이라 표기를 넣지 않았습니다. " + "; ".join(f"{item['그림']}: {item['이유']}" for item in locked))
    if not parsed:
        raise ValueError("표기를 넣을 그림을 골라 주세요")
    content, summary = insert_marks(Path(manuscript).read_bytes(), parsed, manuscript_figures(document),
                                    [len(section) for section in document.sections])
    if not summary["넣음"]:
        reasons = [f"{item['그림']}: {item['이유']}" for item in summary["넣지 못함"]] + [f"{name}: 이미 AI 활용 줄이 있습니다" for name in summary["이미 있음"]]
        raise ValueError("표기를 넣은 그림이 없습니다. " + "; ".join(reasons))
    summary["변경금지 원본 제외"] = locked
    return content, summary


def source_copy(manuscript: str | Path, key: str, credit: str) -> tuple[bytes, dict]:
    """그림 하나(key = inspect의 key)의 캡션 위에 출처 줄(credit)을 넣은 원고 사본(hwpx)과 요약 {'넣음': 그림 번호, '줄'}."""
    document = load_document(manuscript)
    if document.format != "hwpx":
        raise ValueError("hwp 원고에는 출처 줄을 넣지 못합니다. 한글에서 hwpx로 저장해 다시 올려 주세요")
    row = next((row for row in _rows(document, None) if row["key"] == key), None)
    if row is None:
        raise ValueError("원고에 없는 그림을 골랐습니다. 원고를 다시 올려 주세요")
    content, summary = insert_source_line(Path(manuscript).read_bytes(), row["구역"], row["문단"], credit, manuscript_figures(document),
                                          [len(section) for section in document.sections])
    if not summary["넣음"]:
        raise ValueError(f"{row['그림 번호']}에 출처 줄을 넣지 못했습니다: {summary['이유']}")
    return content, summary
