"""결과표 — 의견별 판정 후보와 담당자 확정을 한 표(xlsx)로 적어 보관한다. 사람 작업 4 '최종 판단·보관: 반영 후보를 사람이 확정하고 서류를 보관해 추적한다'.

확정은 사람이 한다(반영/미반영). 프로그램은 확정값을 받아 적고, 후보와 얼마나 달랐는지(검증 기준: 반영 여부 판단 오차율 6% 이내)를 함께 남긴다.
"""

from __future__ import annotations

import io

from .pipeline import error_rate

DECISIONS = ("반영", "미반영")
HEAD = ("번호", "차수", "위치", "의견", "유형", "판정 후보", "담당자 확정", "근거 문단", "수정 제안", "집필자 확인", "검수 기준", "비고")
WIDTHS = (6, 8, 22, 50, 12, 14, 14, 50, 36, 36, 44, 44)


def decision_summary(rows: list[dict], decisions: dict) -> dict:
    """확정값 정리 — 의견 번호에 있는 것, 값이 반영/미반영인 것만 받는다. → {'의견별', '확정', '반영', '미반영', '후보와 다름', '보류였던 것', '오차율'}."""
    numbers = {str(row["번호"]): row for row in rows}
    kept = {str(no): value for no, value in (decisions or {}).items() if str(no) in numbers and value in DECISIONS}
    rate = error_rate(rows, {int(no): value for no, value in kept.items()})
    return {"의견별": kept, "확정": len(kept), "반영": sum(1 for v in kept.values() if v == "반영"), "미반영": sum(1 for v in kept.values() if v == "미반영"),
            "후보와 다름": rate["틀림"], "보류였던 것": rate["보류(확인 필요)"], "오차율": rate}


def _where(row: dict) -> str:
    return " ".join(str(part) for part in (row.get("구분"), row.get("구성"), f"{row['쪽']}쪽" if row.get("쪽") else "") if part)


def _evidence(row: dict) -> str:
    return "\n".join(f"({item.get('위치') or ''}{', ' + str(item['출력본 쪽']) + '쪽' if item.get('출력본 쪽') else ''}) {item.get('문단') or ''}"
                     for item in row.get("근거") or [])


def build_xlsx(manuscript: str, rows: list[dict], decisions: dict | None = None, *, llm: str = "") -> bytes:
    """원고 이름, ncs_opinion.review의 '의견' 행, 담당자 확정 {번호: 반영|미반영} → 결과표 xlsx. 원고·의견에서 온 글은 문자열로만 쓴다."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    if not rows:
        raise ValueError("결과표로 만들 의견이 없습니다")
    summary = decision_summary(rows, decisions or {})
    rate = summary["오차율"]
    book = Workbook()
    sheet = book.active
    sheet.title = "의견 반영 검토"
    sheet.append(["검토의견서·심의의견서 반영 여부 검토 결과표"])
    sheet.append([f"원고: {manuscript}"])
    sheet.append([f"의견 {len(rows)}개 · 담당자 확정 {summary['확정']}개(반영 {summary['반영']}, 미반영 {summary['미반영']}) · 후보와 다름 {summary['후보와 다름']} · "
                  f"확인 필요였던 것 {summary['보류였던 것']} · 오차율 {rate['오차율'] or '-'}(기준 6% 이내, {rate['결과']})"])
    sheet.append([f"판정 후보는 생성형 AI({llm or '미사용'})가 낸 후보이고 최종 판단은 담당자 확정 칸입니다."])
    sheet["A1"].font = Font(bold=True, size=13)
    sheet.append([])
    sheet.append(list(HEAD))
    head_row = sheet.max_row
    for cell in sheet[head_row]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E6E8EA")
    for row in rows:
        values = [row["번호"], row.get("차수") or "", _where(row), row.get("의견") or "", row.get("유형") or "", row.get("판정") or "",
                  summary["의견별"].get(str(row["번호"])), _evidence(row), row.get("수정 제안") or "", row.get("집필자 확인") or "",
                  "\n".join(row.get("검수 기준") or []), "\n".join(row.get("비고") or [])]
        sheet.append([None] * len(values))
        line = sheet.max_row
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(line, column)
            if isinstance(value, str):
                cell.value = value
                cell.data_type = "s"          # '='로 시작하는 의견 글이 수식이 되지 않게
            else:
                cell.value = value
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for index, width in enumerate(WIDTHS):
        sheet.column_dimensions[chr(ord("A") + index)].width = width
    sheet.freeze_panes = sheet.cell(head_row + 1, 1)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
