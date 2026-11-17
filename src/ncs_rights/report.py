"""증빙 제출 현황표 xlsx — 시트 '증빙 제출 현황'(그림마다 한 줄)과 '누락·확인'(지적마다 한 줄)."""

from __future__ import annotations

import io

HEAD = ("그림 번호", "그림명", "원고", "목록", "제작 방식", "증빙", "AI 표기(원고)", "AI 결과물 현황", "판정", "비고")
FINDING_HEAD = ("대상", "수준", "종류", "내용", "조치")
WIDTHS = (12, 34, 7, 7, 24, 34, 28, 30, 10, 60)
FILLS = {"부적합": "FDE7E7", "판단불가": "FFF4D6", "적합": "E6F4EA"}


def _mark(value) -> str:
    return "" if value is None else ("○" if value else "×")


def build_xlsx(report: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(vertical="center", wrap_text=True)
    head_fill = PatternFill("solid", fgColor="E8EEF7")

    def put(ws, row: int, col: int, value, *, bold: bool = False, fill: str | None = None):
        # 원고·서류에서 온 글은 문자열로만 쓴다 — '='로 시작하는 글이 수식이 되지 않게(ncs_service.export와 같은 이유)
        cell = ws.cell(row, col, value)
        if isinstance(value, str):
            cell.data_type = "s"
        cell.border, cell.alignment = border, wrap
        if bold:
            cell.font = Font(bold=True)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        return cell

    wb = Workbook()
    ws = wb.active
    ws.title = "증빙 제출 현황"
    summary, deadline = report["요약"], report["기한"]
    put(ws, 1, 1, "권리 증빙 제출 현황표", bold=True).font = Font(size=14, bold=True)
    lines = [
        f"원고: {report.get('원고', {}).get('파일', '')}    학습모듈명(목록): {summary.get('학습모듈명') or '—'}",
        f"판정: {summary['판정']}    그림 {summary['원고 그림']}개 · 적합 {summary['적합']} · 부적합 {summary['부적합']} · 판단불가 {summary['판단불가']}",
        f"제출 기한: {deadline['내용']}",
    ]
    for offset, line in enumerate(lines):
        ws.cell(2 + offset, 1, line).data_type = "s"
    top = 3 + len(lines)
    for col, name in enumerate(HEAD, 1):
        put(ws, top, col, name, bold=True).fill = head_fill
        ws.column_dimensions[get_column_letter(col)].width = WIDTHS[col - 1]
    for index, row in enumerate(report["현황표"], 1):
        r = top + index
        values = (row["그림 번호"], row["그림명"], _mark(row["원고"]), _mark(row["목록"]), "\n".join(row["제작 방식"]),
                  "\n".join(f"{e['증빙']}: {e['상태']}" for e in row["증빙"]), row["AI 표기"], row["결과물 현황"], row["판정"],
                  "\n".join(row["비고"]))
        for col, value in enumerate(values, 1):
            put(ws, r, col, value, fill=FILLS.get(row["판정"]) if col == 9 else None)
    ws.freeze_panes = ws.cell(top + 1, 1)

    ws2 = wb.create_sheet("누락·확인")
    for col, (name, width) in enumerate(zip(FINDING_HEAD, (34, 10, 16, 70, 50)), 1):
        put(ws2, 1, col, name, bold=True).fill = head_fill
        ws2.column_dimensions[get_column_letter(col)].width = width
    for index, finding in enumerate(report["지적사항"], 2):
        for col, key in enumerate(("그림", "수준", "종류", "내용", "조치"), 1):
            put(ws2, index, col, finding[key], fill=FILLS.get(finding["수준"]) if col == 2 else None)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
