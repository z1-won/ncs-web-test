"""F02 검수 확인서 내보내기 — 화면의 '확인서 한 표'를 제출용 파일로.

입력은 엔진 확인서 행(구성요소·번호·체크 항목·검수결과·비고)의 목록(여러 구성요소를 이어 붙인 것). 실행하지 않은 구성요소의
항목은 각 엔진 sheet.ITEMS에서 채워 54개 항목이 모두 나오게 한다(표시는 비움, 비고 '미검사').

- xlsx: openpyxl로 확인서 모양(구성요소 병합 | 체크 항목 | 적합 | 부적합 | 판단불가 | 비고) + 지적사항 시트는 두지 않는다(ZIP에 있음).
- hwpx: 원본 양식(ncs_core/data/F02_검수확인서_양식.hwpx)의 표에 ✓와 비고를 써 넣는다. 양식에는 적합/부적합 두 칸뿐이므로
  판단불가는 칸을 비우고 비고 앞에 '[판단불가]'를 붙인다. 양식의 비고 안내문('에디터 직접 수정 가능')은 우리 비고가 있을 때만 바꾼다.
"""

from __future__ import annotations

import io
import re
import zipfile
from importlib import import_module
from importlib.resources import files
from xml.etree import ElementTree as ET

from ncs_core.sheet import NOT_CHECKED
from ncs_core.text import FAIL, PASS, UNDECIDED

from .registry import ENGINES

FORM_FILE = "F02_검수확인서_양식.hwpx"
MARK = "✓"


def _text(ws, row: int, col: int, value) -> None:
    """원고에서 온 문구를 셀에 '문자열'로만 쓴다. openpyxl은 '='로 시작하는 문자열을 수식으로 저장하므로
    원고에 '=HYPERLINK(...)' 같은 글이 있으면 검수자가 확인서를 열 때 실행될 수 있다(수식 주입)."""
    cell = ws.cell(row, col, value)
    if isinstance(value, str):
        cell.data_type = "s"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
ET.register_namespace("hp", HP[1:-1])
for prefix, uri in (("hs", "http://www.hancom.co.kr/hwpml/2011/section"), ("hc", "http://www.hancom.co.kr/hwpml/2011/core"),
                    ("ha", "http://www.hancom.co.kr/hwpml/2011/app"), ("hh", "http://www.hancom.co.kr/hwpml/2011/head"),
                    ("hhs", "http://www.hancom.co.kr/hwpml/2011/history"), ("hm", "http://www.hancom.co.kr/hwpml/2011/master-page"),
                    ("hpf", "http://www.hancom.co.kr/schema/2011/hpf"), ("dc", "http://purl.org/dc/elements/1.1/"),
                    ("opf", "http://www.idpf.org/2007/opf/"), ("ooxmlchart", "http://www.hancom.co.kr/hwpml/2016/ooxmlchart"),
                    ("hwpunitchar", "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"), ("epub", "http://www.idpf.org/2007/ops"),
                    ("config", "urn:oasis:names:tc:opendocument:xmlns:config:1.0")):
    ET.register_namespace(prefix, uri)


def _key(component: str) -> str:
    """구성요소 이름 비교용 — 띄어쓰기·하이픈 차이('개발 이력 및판권' vs '개발 이력 및 판권', 'NCS- 학습모듈의 위치')를 무시."""
    return re.sub(r"[\s\-·]", "", component)


def full_sheet(rows: list[dict]) -> list[dict]:
    """엔진 순서대로 54개 항목을 모두 갖춘 확인서 행 목록. rows에 있는 항목은 그대로, 없는 항목은 미검사 행으로."""
    given = {(_key(r["구성요소"]), r["번호"]): r for r in rows}
    out = []
    for engine in ENGINES.values():
        sheet = import_module(engine.package + ".sheet")
        for item in sheet.ITEMS:
            found = given.get((_key(sheet.COMPONENT), item.no))
            out.append(found or {"구성요소": sheet.COMPONENT, "번호": item.no, "체크 항목": item.text,
                                 "검수결과": NOT_CHECKED, "비고": "미검사 — 이 구성요소는 실행하지 않음"})
    return out


# ───────────────────────── xlsx ─────────────────────────

def build_xlsx(module_code: str, rows: list[dict], *, title: str = "2026년도 NCS학습모듈 검수 확인서", meta: dict | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    rows = full_sheet(rows)
    wb = Workbook()
    ws = wb.active
    ws.title = "검수 확인서"
    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    head_fill = PatternFill("solid", fgColor="E8EEF7")
    comp_fill = PatternFill("solid", fgColor="EEF7EE")

    ws.merge_cells("A1:F1")
    _text(ws, 1, 1, title)
    ws["A1"].font = Font(size=14, bold=True)
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 28
    info = meta or {}
    ws.merge_cells("A2:F2")
    _text(ws, 2, 1, f"▶ 세분류명: {info.get('세분류명', '')}    ▶ 학습모듈명: {info.get('학습모듈명', '')}    ▶ 모듈 코드: {module_code}"
                + (f"    ▶ 검수 실행: {info['실행시각']}" if info.get("실행시각") else ""))
    ws["A2"].alignment = left
    ws.merge_cells("A3:F3")
    ws["A3"] = "자동 검수 결과입니다. ✓는 규칙이 확정한 판정, 비고의 [판단불가]는 사람이 확인해야 할 항목입니다. 최종 확인 후 제출하세요."
    ws["A3"].font = Font(size=9, color="666666")

    header_row = 5
    ws.merge_cells(start_row=header_row, start_column=1, end_row=header_row + 1, end_column=1)
    ws.merge_cells(start_row=header_row, start_column=2, end_row=header_row + 1, end_column=2)
    ws.merge_cells(start_row=header_row, start_column=3, end_row=header_row, end_column=5)
    ws.merge_cells(start_row=header_row, start_column=6, end_row=header_row + 1, end_column=6)
    for col, text in ((1, "학습모듈 구성요소"), (2, "체크 항목"), (3, "검수 결과"), (6, "비고")):
        ws.cell(header_row, col, text)
    for col, text in ((3, "적합"), (4, "부적합"), (5, "판단불가")):
        ws.cell(header_row + 1, col, text)
    for r in (header_row, header_row + 1):
        for c in range(1, 7):
            cell = ws.cell(r, c)
            cell.font = Font(bold=True)
            cell.alignment = center
            cell.fill = head_fill
            cell.border = border

    r = header_row + 2
    start = r
    for i, row in enumerate(rows):
        new_component = i == 0 or _key(row["구성요소"]) != _key(rows[i - 1]["구성요소"])
        if new_component:
            if i:
                ws.merge_cells(start_row=start, start_column=1, end_row=r - 1, end_column=1)
            start = r
            _text(ws, r, 1, row["구성요소"].replace("및판권", "및 판권"))
        _text(ws, r, 2, f"{row['번호']} {row['체크 항목']}")
        verdict = row["검수결과"]
        ws.cell(r, 3, MARK if verdict == PASS else "")
        ws.cell(r, 4, MARK if verdict == FAIL else "")
        ws.cell(r, 5, "△" if verdict == UNDECIDED else "")
        _text(ws, r, 6, _remark(row))
        for c in range(1, 7):
            cell = ws.cell(r, c)
            cell.border = border
            cell.alignment = center if c in (1, 3, 4, 5) else left
        ws.cell(r, 1).fill = comp_fill
        if verdict == FAIL:
            ws.cell(r, 4).font = Font(bold=True, color="C0392B")
        elif verdict == UNDECIDED:
            ws.cell(r, 5).font = Font(bold=True, color="B9770E")
        elif verdict == PASS:
            ws.cell(r, 3).font = Font(bold=True, color="1E8449")
        r += 1
    ws.merge_cells(start_row=start, start_column=1, end_row=r - 1, end_column=1)
    for col, width in ((1, 16), (2, 60), (3, 7), (4, 7), (5, 9), (6, 70)):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = ws.cell(header_row + 2, 1)
    ws.print_title_rows = f"{header_row}:{header_row + 1}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToHeight = 0

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _remark(row: dict) -> str:
    note = (row.get("비고") or "").strip()
    if row["검수결과"] == UNDECIDED:
        return "[판단불가] " + note if note else "[판단불가] 사람 확인 필요"
    return note


# ───────────────────────── hwpx(양식 채우기) ─────────────────────────

def _cell_text(cell: ET.Element) -> str:
    return " ".join("".join(t.text or "" for t in p.iter(HP + "t")) for p in cell.iter(HP + "p")).strip()


def _set_cell_text(cell: ET.Element, text: str) -> None:
    """셀의 첫 문단·첫 run에 글을 쓰고 나머지 글자(hp:t)는 지운다. 문단·글자 서식(charPrIDRef)은 양식 것을 그대로 쓴다."""
    paragraphs = list(cell.iter(HP + "p"))
    if not paragraphs:
        return
    first = paragraphs[0]
    for p in paragraphs:
        for run in p.findall(HP + "run"):
            for t in run.findall(HP + "t"):
                run.remove(t)
    # 첫 문단만 남긴다(여러 문단이던 셀은 하나로)
    sub = cell.find(HP + "subList")
    if sub is not None:
        for p in paragraphs[1:]:
            if p in list(sub):
                sub.remove(p)
    run = first.find(HP + "run")
    if run is None:
        run = ET.SubElement(first, HP + "run")
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if i:
            ET.SubElement(run, HP + "lineBreak")
        t = ET.SubElement(run, HP + "t")
        t.text = line
    # 저장된 배치 캐시는 글이 바뀌면 틀리므로 지운다(한글이 열 때 다시 계산)
    for p in (first,):
        seg = p.find(HP + "linesegarray")
        if seg is not None:
            p.remove(seg)


def build_hwpx(module_code: str, rows: list[dict], *, meta: dict | None = None) -> bytes:
    """양식 hwpx의 검수표를 채운 새 hwpx 바이트. 양식 표 구조(56행: 머리 2 + 항목 54)가 다르면 ValueError."""
    rows = full_sheet(rows)
    form = (files("ncs_core") / "data" / FORM_FILE).read_bytes()
    source = zipfile.ZipFile(io.BytesIO(form))
    section = ET.fromstring(source.read("Contents/section0.xml"))
    tables = list(section.iter(HP + "tbl"))
    sheet_table = next((t for t in tables if int(t.get("rowCnt") or 0) >= 50), None)
    if sheet_table is None:
        raise ValueError("양식에서 검수표(56행)를 찾지 못했습니다")

    # 머리 표(세분류명·학습모듈명)
    info = meta or {}
    head_table = next((t for t in tables if t is not sheet_table and int(t.get("rowCnt") or 0) == 1), None)
    if head_table is not None:
        cell = head_table.find(f"{HP}tr/{HP}tc")
        if cell is not None:
            _fill_head(cell, info.get("세분류명", ""), info.get("학습모듈명", ""), module_code)

    # 항목 행: 2열(체크 항목) 글의 첫 글자 ①~⑧와 현재 구성요소(1열 병합 셀)로 우리 행을 찾는다
    by_key = {(_key(r["구성요소"]), r["번호"]): r for r in rows}
    component = None
    filled = 0
    for tr in sheet_table.findall(HP + "tr"):
        cells = {int(tc.find(HP + "cellAddr").get("colAddr")): tc for tc in tr.findall(HP + "tc")}
        if 0 in cells and _cell_text(cells[0]) and 1 in cells and _cell_text(cells[1])[:1] in "①②③④⑤⑥⑦⑧":
            component = _cell_text(cells[0])
        if component is None or 1 not in cells:
            continue
        no = _cell_text(cells[1])[:1]
        row = by_key.get((_key(component), no))
        if row is None:
            continue
        verdict = row["검수결과"]
        if 2 in cells:
            _set_cell_text(cells[2], MARK if verdict == PASS else "")
        if 3 in cells:
            _set_cell_text(cells[3], MARK if verdict == FAIL else "")
        remark = _remark(row) if verdict in (FAIL, UNDECIDED) else (row.get("비고") or "").strip()
        if 4 in cells and (remark or verdict == NOT_CHECKED):
            _set_cell_text(cells[4], remark or "미검사")
        filled += 1
    if filled < 50:
        raise ValueError(f"양식 항목 행을 {filled}개만 채웠습니다(54개여야 함) — 양식 파일이 바뀌었는지 확인")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "Contents/section0.xml":
                data = ET.tostring(section, encoding="utf-8", xml_declaration=True)
            elif item.filename == "Preview/PrvText.txt":
                data = f"{module_code} 검수 확인서(자동 검수 결과)".encode("utf-8")
            # mimetype은 압축하지 않는다(HWPX/ODF 규약). 나머지는 원본 방식대로
            compress = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
            target.writestr(item, data, compress_type=compress)
    return out.getvalue()


def _fill_head(cell: ET.Element, subclass: str, module_name: str, module_code: str) -> None:
    """머리 셀의 '▶ 세분류명:' / '▶ 학습모듈명:' 문단 끝에 값을 붙인다. 문단 구조는 그대로 두고 글자만 더한다."""
    for p in cell.iter(HP + "p"):
        text = "".join(t.text or "" for t in p.iter(HP + "t"))
        value = None
        if "세분류명" in text and subclass:
            value = f" {subclass}"
        elif "학습모듈명" in text:
            value = f" {module_name} ({module_code})" if module_name else f" ({module_code})"
        if value is None:
            continue
        runs = p.findall(HP + "run")
        last_t = None
        for run in runs:
            for t in run.findall(HP + "t"):
                last_t = t
        if last_t is not None:
            last_t.text = (last_t.text or "") + value
        seg = p.find(HP + "linesegarray")
        if seg is not None:
            p.remove(seg)


def module_meta(module_code: str) -> dict:
    """NCS 목록에서 세분류명·학습모듈명(=능력단위명)을 찾는다. 없으면 빈 값."""
    try:
        from ncs_core.ncs_catalog import catalog

        cat = catalog()
        sub = cat.subclass(module_code)
        unit = cat.unit(module_code)
        return {"세분류명": sub.name if sub else "", "학습모듈명": unit.name if unit else ""}
    except Exception:  # 목록 파일이 없는 환경에서도 내보내기는 되어야 한다
        return {"세분류명": "", "학습모듈명": ""}
