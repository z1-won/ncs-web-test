"""생성형 AI 결과물 현황(REQ-02-006 ④) — 원고에서 AI 활용 줄이 붙은 그림을 모아 서약서 붙임 양식의 칸으로 만든다.

양식의 칸(생성형 AI 결과물 집필자 서약서 붙임): 순번 | 결과물 명 | 학습모듈 해당 쪽수 | 활용 AI | 비고.
결과물 명은 '그림 1-1 그림명', 쪽수는 출력본 PDF를 함께 받았을 때만 'p.12'로 적는다(한글 파일만으로는 쪽을 알 수 없다).
같은 그림 번호가 출력본의 여러 쪽에서 캡션으로 나오면 그 쪽을 모두 적고 비고에 알린다. 비고에는 활용 방식과 일자를 적는다.
"""

from __future__ import annotations

import io

from ncs_core.figures import MODE_WORDS

HEAD = ("순번", "결과물 명", "학습모듈 해당 쪽수", "활용 AI", "비고")
WIDTHS = (8, 46, 20, 24, 44)
TITLE = "생성형 AI 결과물 현황"


def _pages(label: str, minor, pages: dict | None) -> tuple[str, str]:
    """(쪽수 칸, 비고에 덧붙일 말)."""
    if pages is None:
        return "", ""
    if minor is None:
        return "", "뒤 번호가 빈 그림이라 쪽을 찾지 못함"
    places = pages.get(label) or []
    folios = [str(place["쪽"]) for place in places if place.get("쪽")]
    if not folios:
        return "", "출력본에서 캡션을 찾지 못함" if not places else "출력본에 쪽 번호가 없음"
    note = "같은 그림 번호가 여러 쪽에 있음" if len(folios) > 1 else ("쪽 번호는 추정" if places[0].get("추정") else "")
    return ", ".join(f"p.{folio}" for folio in folios), note


def result_rows(figures: list[dict], pages: dict | None = None) -> list[dict]:
    """figures: service.inspect의 그림 줄(예정 표기를 합친 것). AI 표기가 있는 그림만 현황 줄이 된다."""
    rows = []
    for figure in figures:
        ai = figure.get("AI 표기")
        if not ai:
            continue
        page, page_note = _pages(figure["그림 번호"], figure.get("뒤 번호"), pages)
        when = ai.get("일자") or ""
        terms = figure.get("공공누리")
        # 원본의 공공누리 유형을 결과물에 적는다(REQ-02-006 ⑥, REQ-04-006): 제2·4유형은 비상업 조건, 제3·4유형은 변경금지 원본
        kogl_note = ""
        if terms and terms["변경금지"]:
            kogl_note = f"원본 {terms['이름']}: 변경금지 원본에 AI 활용 표기가 있음 — AI 수정 보완 대상이 아닌 원본, 확인 필요"
        elif terms and terms["비상업"]:
            kogl_note = f"원본 {terms['이름']}: 비상업적 이용만 가능"
        elif terms:
            kogl_note = f"원본 {terms['이름']}"
        notes = [f"{MODE_WORDS.get(ai['방식'], ai['방식'])}" + (f". {when}" if when else ""), page_note,
                 "이번에 넣을 표기" if ai.get("예정") else "", kogl_note]
        rows.append({"순번": len(rows) + 1, "결과물 명": f"{figure['그림 번호']} {figure['그림명']}".strip(),
                     "학습모듈 해당 쪽수": page, "활용 AI": ai["도구"], "비고": ", ".join(note for note in notes if note),
                     "key": figure["key"]})
    return rows


def build_xlsx(rows: list[dict], *, manuscript: str = "") -> bytes:
    """현황 xlsx 한 장. 원고에서 온 글은 문자열로만 쓴다('='로 시작해도 수식이 되지 않게 — ncs_service.export와 같은 이유)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(vertical="center", wrap_text=True)
    wb = Workbook()
    ws = wb.active
    ws.title = TITLE
    ws.cell(1, 1, TITLE).font = Font(bold=True, size=13)
    if manuscript:
        note = ws.cell(2, 1, f"원고: {manuscript}")
        note.data_type = "s"
    for col, (name, width) in enumerate(zip(HEAD, WIDTHS), 1):
        cell = ws.cell(4, col, name)
        cell.font, cell.border, cell.alignment = Font(bold=True), border, wrap
        cell.fill = PatternFill("solid", fgColor="E8EEF7")
        ws.column_dimensions[get_column_letter(col)].width = width
    for r, row in enumerate(rows, 5):
        for col, name in enumerate(HEAD, 1):
            cell = ws.cell(r, col, row[name])
            if isinstance(row[name], str):
                cell.data_type = "s"
            cell.border, cell.alignment = border, wrap
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
