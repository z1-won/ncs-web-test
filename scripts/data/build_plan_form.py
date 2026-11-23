"""개선용 개발계획서 빈 양식(src/ncs_core/data/T01_개발계획서_양식_개선.hwpx) 만들기 — 작성된 개선 계획서에서 내용을 비워 틀만 남긴다.

  python scripts/data/build_plan_form.py --from "samples/plan/T02_초기결과_개발계획서_….hwpx"

직능연의 개선 양식 빈 파일이 따로 없어, 직능연 1차본(개선 양식으로 작성된 계획서)을 받아 다음을 비운다:
  기본 정보(세분류명·영문·개발기관명 — 신규/개선은 '개선') · NCS 변경 전·후 대조표(머리 + 빈 행 하나) · 총괄표(머리 + 빈 행 하나) ·
  위치 표의 값 · 모듈 표(첫 표만 남겨 칸을 비우고 나머지는 지운다) · 미리 보기(신규 양식의 것으로 바꾼다)
작성 안내 글과 작성 예시 표는 그대로 둔다. 만든 뒤 원래 계획서의 능력단위 코드·명칭이 남아 있지 않은지 확인하고, 남아 있으면 쓰지 않는다.
직능연의 빈 양식을 받으면 이 파일을 그것으로 바꾼다(표의 머리 글이 같으면 ncs_plan.fill은 그대로 돈다).
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ncs_core import load_document  # noqa: E402
from ncs_plan import fill  # noqa: E402
from ncs_plan.fill import HP, cell_text, cells_by_col, find_table, set_addr, set_cell, squash  # noqa: E402
from ncs_plan.parsers import read_plan  # noqa: E402

DATA = ROOT / "src" / "ncs_core" / "data"
OUT = DATA / fill.IMPROVE_FORM_FILE


def _keep_one_blank_row(table: ET.Element, head_label: str) -> None:
    """머리(첫 칸이 head_label인 행까지)와 그 아래 빈 행 하나만 남긴다."""
    trs = table.findall(HP + "tr")
    head = next(i for i, tr in enumerate(trs) if squash(cell_text(cells_by_col(tr).get(0, tr))) == head_label)
    for tr in trs[head + 2:]:
        table.remove(tr)
    for tc in trs[head + 1].findall(HP + "tc"):
        set_cell(tc, "")
        set_addr(tc, head + 1, row_span=1)
    table.set("rowCnt", str(head + 2))


def _blank_modules(section: ET.Element) -> int:
    """모듈 표(NCS(수정 금지) ⇰ NCS학습모듈) 가운데 첫 표만 남겨 칸을 비우고 나머지 문단은 지운다. → 지운 표 수."""
    found = []
    for p in section.findall(HP + "p"):
        for table in p.findall(f"{HP}run/{HP}tbl"):
            trs = table.findall(HP + "tr")
            if len(trs) >= 5 and squash(cell_text(trs[0].find(HP + "tc"))).startswith("NCS(수정금지)"):
                found.append((p, table))
    if not found:
        raise SystemExit("모듈 표를 찾지 못했습니다")
    for p, _ in found[1:]:
        section.remove(p)
    table = found[0][1]
    trs = table.findall(HP + "tr")
    row1, row2 = cells_by_col(trs[1]), cells_by_col(trs[2])
    for cell in (row1[1], row1[3], row1[6], row2[1], row2[6]):
        set_cell(cell, "")
    head = next(i for i, tr in enumerate(trs) if squash(cell_text(cells_by_col(tr).get(5, tr))) == "학습명")
    body = next(tr for tr in trs[head + 1:] if {0, 1, 5, 6, 7} <= set(cells_by_col(tr)))
    for tr in trs[head + 1:]:
        if tr is not body:
            table.remove(tr)
    for tc in body.findall(HP + "tc"):
        set_cell(tc, "")
        set_addr(tc, head + 1, row_span=1)
    arrow = cells_by_col(trs[head]).get(4)
    if arrow is not None:
        arrow.find(HP + "cellSpan").set("rowSpan", "2")
    table.set("rowCnt", str(head + 2))
    return len(found) - 1


def build(source: Path) -> bytes:
    filled = read_plan(load_document(source).tables)
    if filled.get("대조표") is None or all(e["개선 유형"] is None for e in filled.get("총괄표") or [{"개선 유형": None}]):
        raise SystemExit("개선 양식으로 작성된 계획서가 아닙니다(NCS 변경 전·후 대조표와 총괄표의 개선 유형 열이 있어야 합니다)")
    archive = zipfile.ZipFile(source)
    sections = {name: ET.fromstring(archive.read(name)) for name in archive.namelist() if name.startswith("Contents/section")}
    front = next(root for name, root in sorted(sections.items()) if find_table(root, "(한글)세분류명") is not None)
    fill.fill_basic(front, {"신규/개선": "개선"})
    _keep_one_blank_row(find_table(front, *fill.CHANGE_LABELS), "능력단위번호")
    _keep_one_blank_row(find_table(front, "능력단위번호", "NCS학습모듈코드번호"), "능력단위번호")
    fill.fill_position(front, {"대분류": " ", "중분류": " ", "소분류": " ", "세분류": [], "모듈": []})
    removed = next(count for count in (_try(_blank_modules, root) for _, root in sorted(sections.items())) if count is not None)
    plain = zipfile.ZipFile(io.BytesIO((DATA / fill.FORM_FILE).read_bytes()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for item in archive.infolist():
            data = archive.read(item.filename)
            if item.filename in sections:
                data = ET.tostring(sections[item.filename], encoding="utf-8", xml_declaration=True)
            elif item.filename.startswith("Preview/") and item.filename in plain.namelist():
                data = plain.read(item.filename)          # 원래 계획서의 미리 보기(첫 쪽 그림·글)를 남기지 않는다
            target.writestr(item.filename, data, compress_type=zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    content = out.getvalue()
    # 원래 계획서의 능력단위 번호·이름, 세분류명, 기관명이 남아 있으면 쓰지 않는다
    left = zipfile.ZipFile(io.BytesIO(content))
    text = "".join("".join(t.text or "" for t in ET.fromstring(left.read(name)).iter(HP + "t")) for name in sections)
    words = {e["코드"] for e in filled["총괄표"]} | {e["명칭"] for e in filled["총괄표"] if e["명칭"]} | {v for v in (filled["기본"].get("세분류명"), filled["기본"].get("개발기관명")) if v}
    remaining = sorted(word for word in words if word and squash(word) in squash(text))
    if remaining:
        raise SystemExit("비운 양식에 원래 계획서의 글이 남아 있습니다: " + ", ".join(remaining))
    print(f"모듈 표 {removed}개를 지우고 하나를 비웠습니다. 남은 글자 {len(text):,}자, {len(content) // 1024}KB")
    return content


def _try(action, root):
    try:
        return action(root)
    except SystemExit:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="source", required=True, help="개선 양식으로 작성된 개발계획서(hwpx)")
    parser.add_argument("--out", default=str(OUT), help=f"만들 양식 파일(기본 {OUT.relative_to(ROOT)})")
    args = parser.parse_args()
    content = build(Path(args.source))
    Path(args.out).write_bytes(content)
    print(f"저장: {args.out}")


if __name__ == "__main__":
    main()
