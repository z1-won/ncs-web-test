"""개발계획서 자동 입력(REQ-02-001 '작성') — T01 양식 hwpx에 NCS 정보를 채워 초안 hwpx를 만든다.

입력 `spec`(dict):
  기본: {세분류명, 영문 세분류명, 신규/개선, 개발기관명}
  총괄표: [{코드, 명칭, LM 코드, LM 명칭, 집필진, 검토진}]           # 비우면 모듈에서 만든다
  위치:   {대분류, 중분류, 소분류, 세분류: [...], 모듈: [{능력단위, 학습모듈명}]}
  모듈:   [{코드, 명칭, 정의, 요소: [{코드, 명칭, 수행준거: [...]}]}]
NCS 쪽(왼쪽)은 spec 그대로, 학습모듈 쪽(오른쪽)은 양식 작성 안내대로 초안을 만든다:
  학습모듈명 = 능력단위명 · 학습모듈의 목표 = 정의에서 주어 삭제 + '~할 수 있다.' · 학습 N = 요소 N(명칭 그대로) ·
  학습 내용 N-1 = 빈 칸(집필자 작성) · 학습 목표 = 수행준거 그대로.
양식 파일은 ncs_core/data/T01_개발계획서_양식.hwpx(신규 개발 양식). 저장 규칙은 ncs_service.export.build_hwpx와 같다
(mimetype 무압축, 네임스페이스 접두사 유지, 배치 캐시 linesegarray 제거).
"""

from __future__ import annotations

import copy
import io
import re
import zipfile
from importlib.resources import files
from xml.etree import ElementTree as ET

from .rules.module import goal_from_definition

FORM_FILE = "T01_개발계획서_양식.hwpx"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
WRITER_NOTE = "(집필자 작성)"
for _prefix, _uri in (("hp", HP[1:-1]), ("hs", "http://www.hancom.co.kr/hwpml/2011/section"), ("hc", "http://www.hancom.co.kr/hwpml/2011/core"),
                      ("ha", "http://www.hancom.co.kr/hwpml/2011/app"), ("hh", "http://www.hancom.co.kr/hwpml/2011/head"),
                      ("hhs", "http://www.hancom.co.kr/hwpml/2011/history"), ("hm", "http://www.hancom.co.kr/hwpml/2011/master-page"),
                      ("hpf", "http://www.hancom.co.kr/schema/2011/hpf"), ("dc", "http://purl.org/dc/elements/1.1/"),
                      ("opf", "http://www.idpf.org/2007/opf/"), ("ooxmlchart", "http://www.hancom.co.kr/hwpml/2016/ooxmlchart"),
                      ("hwpunitchar", "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"), ("epub", "http://www.idpf.org/2007/ops"),
                      ("config", "urn:oasis:names:tc:opendocument:xmlns:config:1.0")):
    ET.register_namespace(_prefix, _uri)


# ── 셀 도우미 ─────────────────────────────────────────────────────────────────

def cell_text(cell: ET.Element) -> str:
    return " ".join("".join(t.text or "" for t in p.iter(HP + "t")) for p in cell.iter(HP + "p")).strip()


def squash(text: str) -> str:
    return "".join(text.split())


def set_cell(cell: ET.Element, lines: list[str] | str) -> None:
    """셀 글을 문단 목록으로 바꾼다. 첫 문단의 서식(paraPr·charPr)을 모든 문단에 쓴다."""
    lines = [lines] if isinstance(lines, str) else list(lines) or [""]
    sub = cell.find(HP + "subList")
    paragraphs = sub.findall(HP + "p")
    proto = copy.deepcopy(paragraphs[0])
    for p in paragraphs:
        sub.remove(p)
    run_proto = proto.find(HP + "run")
    for child in list(proto):
        if child.tag != HP + "run":
            proto.remove(child)          # linesegarray 등 배치 캐시
    for run in proto.findall(HP + "run")[1:]:
        proto.remove(run)
    if run_proto is None:
        run_proto = ET.SubElement(proto, HP + "run")
    for child in list(run_proto):
        run_proto.remove(child)
    for line in lines:
        p = copy.deepcopy(proto)
        t = ET.SubElement(p.find(HP + "run"), HP + "t")
        t.text = line
        sub.append(p)


def cells_by_col(tr: ET.Element) -> dict[int, ET.Element]:
    return {int(tc.find(HP + "cellAddr").get("colAddr")): tc for tc in tr.findall(HP + "tc")}


def set_addr(tc: ET.Element, row: int, *, row_span: int | None = None) -> None:
    tc.find(HP + "cellAddr").set("rowAddr", str(row))
    if row_span is not None:
        tc.find(HP + "cellSpan").set("rowSpan", str(row_span))


def find_table(root: ET.Element, *labels: str) -> ET.Element | None:
    """앞쪽 셀들의 글(공백 제거)에 labels가 모두 들어 있는 표. 양식의 '작성필요' 같은 덧말이 라벨 앞뒤에 붙어 있어도 찾는다."""
    for table in root.iter(HP + "tbl"):
        texts = [squash(cell_text(tc)) for tc in table.iter(HP + "tc")][:12]
        if all(any(squash(label) in t for t in texts) for label in labels):
            return table
    return None


def resize_rows(table: ET.Element, keep: int) -> None:
    """표의 행을 keep개만 남긴다(뒤에서 자른다)."""
    rows = table.findall(HP + "tr")
    for tr in rows[keep:]:
        table.remove(tr)
    table.set("rowCnt", str(min(keep, len(rows))))


# ── 1쪽 ───────────────────────────────────────────────────────────────────────

def fill_basic(root: ET.Element, basic: dict) -> None:
    table = find_table(root, "(한글)세분류명")
    if table is None:
        raise ValueError("양식에서 기본 정보 표를 찾지 못했습니다")
    for tr in table.findall(HP + "tr"):
        cells = cells_by_col(tr)
        if 0 not in cells or 1 not in cells:
            continue
        label = squash(cell_text(cells[0]))
        if "(한글)세분류명" in label:
            set_cell(cells[1], basic.get("세분류명") or "")
        elif "(영문)세분류명" in label:
            set_cell(cells[1], basic.get("영문 세분류명") or "")
        elif label.startswith("신규/개선"):
            set_cell(cells[1], basic.get("신규/개선") or "신규")
        elif label.startswith("개발기관명"):
            set_cell(cells[1], basic.get("개발기관명") or "")


def fill_summary(root: ET.Element, rows: list[dict]) -> None:
    table = find_table(root, "능력단위번호", "NCS학습모듈코드번호")
    if table is None:
        raise ValueError("양식에서 총괄표를 찾지 못했습니다")
    trs = table.findall(HP + "tr")
    head = next(i for i, tr in enumerate(trs) if squash(cell_text(cells_by_col(tr).get(0, tr))) == "능력단위번호")
    body = trs[head + 1:]
    proto = copy.deepcopy(body[0])
    for tr in body:
        table.remove(tr)
    for i, entry in enumerate(rows):
        tr = copy.deepcopy(proto)
        cells = cells_by_col(tr)
        values = [entry.get("코드", ""), entry.get("명칭", ""), entry.get("LM 코드") or f"LM{entry.get('코드', '')}",
                  entry.get("LM 명칭") or entry.get("명칭", ""), entry.get("집필진", ""), entry.get("검토진", "")]
        for col, value in enumerate(values):
            if col in cells:
                set_cell(cells[col], value)
        for tc in tr.findall(HP + "tc"):
            set_addr(tc, head + 1 + i)
        table.append(tr)
    table.set("rowCnt", str(head + 1 + len(rows)))
    fit_row_heights(table)


def fill_position(root: ET.Element, position: dict) -> None:
    table = find_table(root, "대분류", "중분류", "소분류")
    if table is not None:
        for tr in table.findall(HP + "tr"):
            cells = cells_by_col(tr)
            label = squash(cell_text(cells[min(cells)]))
            value_cell = cells[max(cells)]
            if label in ("대분류", "중분류", "소분류") and position.get(label):
                set_cell(value_cell, position[label])
    table = find_table(root, "세분류", "능력단위", "학습모듈명")
    if table is None:
        return
    trs = table.findall(HP + "tr")
    subclasses, modules = list(position.get("세분류") or []), list(position.get("모듈") or [])
    head = next((i for i, tr in enumerate(trs) if squash(cell_text(cells_by_col(tr).get(3, tr))) == "능력단위"), 0)
    sub_i = mod_i = 0
    for i, tr in enumerate(trs):
        cells = cells_by_col(tr)
        if 0 in cells and squash(cell_text(cells[0])) != "세분류":
            set_cell(cells[0], subclasses[sub_i] if sub_i < len(subclasses) else "")
            sub_i += 1
        if i > head and 3 in cells and 4 in cells:
            if mod_i < len(modules):
                set_cell(cells[3], modules[mod_i].get("능력단위", ""))
                set_cell(cells[4], modules[mod_i].get("학습모듈명", ""))
            else:
                set_cell(cells[3], "")
                set_cell(cells[4], "")
            mod_i += 1


# ── 모듈 표 ─────────────────────────────────────────────────────────────────────

def module_table_paragraph(section: ET.Element) -> ET.Element:
    """빈 모듈 표(NCS 수정 금지 ⇰ NCS학습모듈, 머리 아래 빈 행)가 든 문단."""
    for p in section.findall(HP + "p"):
        for table in p.findall(f"{HP}run/{HP}tbl"):      # 최상위 표만(작성 예시 표 안의 중첩 표 제외)
            trs = table.findall(HP + "tr")
            if len(trs) < 5:
                continue
            first = squash(cell_text(trs[0].find(HP + "tc")))
            row1 = cells_by_col(trs[1])
            if first.startswith("NCS(수정금지)") and 1 in row1 and squash(cell_text(row1[0])) == "능력단위코드번호" and not cell_text(row1[1]):
                return p
    raise ValueError("양식에서 빈 모듈 표를 찾지 못했습니다")


NOUN_END = re.compile(r"(\S+?)(을|를)?\s*능력이다\s*\.?$")   # '… 관리 능력이다.' 꼴(정의 끝이 '~하는 능력이다'가 아닐 때)


def draft_goal(definition: str) -> str:
    """정의 → 학습모듈의 목표 초안. '~하는 능력이다' → '~할 수 있다.', '… 관리 능력이다' → '… 관리를 할 수 있다.'"""
    subject, goal = goal_from_definition(definition or "")
    if goal and not goal.endswith("할 수 있다."):
        m = NOUN_END.search(goal)
        if m:
            noun = m.group(1)
            particle = "을" if (ord(noun[-1]) - 0xAC00) % 28 and "가" <= noun[-1] <= "힣" else "를"
            goal = goal[: m.start()] + f"{noun}{particle} 할 수 있다."
    return goal


def draft_module(module: dict) -> dict:
    """NCS 쪽(spec)에서 학습모듈 쪽 초안을 만든다. 돌려주는 값은 ncs_plan.parsers.read_module과 같은 열쇠를 쓴다."""
    goal = draft_goal(module.get("정의") or "")
    lessons = []
    for i, element in enumerate(module.get("요소") or [], 1):
        lessons.append({"번호": i, "명칭": element["명칭"], "요소": [element["코드"]],
                        "내용": [{"번호": i, "소번호": 1, "명칭": WRITER_NOTE, "목표": list(element.get("수행준거") or [])}]})
    return {"코드": module["코드"], "명칭": module["명칭"], "학습모듈명": module.get("학습모듈명") or module["명칭"],
            "정의": module.get("정의") or "", "목표": module.get("목표") or goal, "요소": module.get("요소") or [], "학습": lessons}


def fill_module_table(table: ET.Element, module: dict) -> None:
    trs = table.findall(HP + "tr")
    # 머리 4행: 코드·명칭·학습모듈명 / 정의·목표
    row1, row2 = cells_by_col(trs[1]), cells_by_col(trs[2])
    set_cell(row1[1], module["코드"])
    set_cell(row1[3], module["명칭"])
    set_cell(row1[6], module["학습모듈명"])
    set_cell(row2[1], module["정의"])
    set_cell(row2[6], module["목표"])
    head_row = next(i for i, tr in enumerate(trs) if squash(cell_text(cells_by_col(tr).get(5, tr))) == "학습명")
    body_proto = copy.deepcopy(trs[head_row + 1])
    for tr in trs[head_row + 1:]:
        table.remove(tr)
    arrow = cells_by_col(trs[head_row]).get(4)
    elements = {e["코드"]: e for e in module["요소"]}
    r = head_row + 1
    for lesson in module["학습"]:
        own = [elements[c] for c in lesson["요소"] if c in elements]
        subs = lesson["내용"] or [{"번호": lesson["번호"], "소번호": 1, "명칭": WRITER_NOTE, "목표": []}]
        span = max(len(subs), len(own), 1)
        for k in range(span):
            tr = copy.deepcopy(body_proto)
            cells = cells_by_col(tr)
            if k < len(own):
                element = own[k]
                set_cell(cells[0], [element["코드"], element["명칭"]])
                set_cell(cells[1], list(element.get("수행준거") or []))
                if len(own) == 1 and span > 1:
                    set_addr(cells[0], r + k, row_span=span)
                    set_addr(cells[1], r + k, row_span=span)
            else:
                tr.remove(cells[0])
                tr.remove(cells[1])
            if k == 0:
                set_cell(cells[5], f"{lesson['번호']}. {lesson['명칭']}")
                set_addr(cells[5], r, row_span=span)
            else:
                tr.remove(cells[5])
            if k < len(subs):
                sub = subs[k]
                set_cell(cells[6], [f"{sub['번호']}-{sub['소번호']}.", sub["명칭"]])
                set_cell(cells[7], list(sub["목표"]))
            else:
                tr.remove(cells[6])
                tr.remove(cells[7])
            for tc in tr.findall(HP + "tc"):
                if tc.find(HP + "cellSpan").get("rowSpan") == "1" or tc not in (cells[0], cells[1], cells[5]):
                    set_addr(tc, r + k)
            table.append(tr)
        r += span
    if arrow is not None:
        arrow.find(HP + "cellSpan").set("rowSpan", str(r - head_row))
    table.set("rowCnt", str(r))


# ── 행 높이 추정 ──────────────────────────────────────────────────────────────
# HWPUNIT(1/7200인치). 양식 본문 글자 8pt(charPr height 800) 기준. 실제 계획서 셀(10줄·6문단 → 15,425)에서 역산한 값:
# 한 줄 1,250, 문단 사이 150, 셀 안쪽 여백 위아래 합 560. 글자 너비는 숫자·영문·공백·자간(-3%)이 섞여 글자 크기의 0.62 정도.
# 한글은 내용이 셀보다 크면 행을 스스로 키우므로 추정은 조금 모자란 쪽이 낫다(남으면 빈 여백이 남는다).
LINE_HEIGHT = 1150
PARA_GAP = 120
CELL_PADDING = 560
CHAR_WIDTH = 800 * 0.55
MIN_ROW_HEIGHT = 2348


def estimate_cell_height(cell: ET.Element) -> int:
    width = int(cell.find(HP + "cellSz").get("width")) - CELL_PADDING
    per_line = max(1, int(width // CHAR_WIDTH))
    lines, paragraphs = 0, 0
    for p in cell.iter(HP + "p"):
        text = "".join(t.text or "" for t in p.iter(HP + "t"))
        lines += max(1, -(-len(text) // per_line))
        paragraphs += 1
    return lines * LINE_HEIGHT + max(0, paragraphs - 1) * PARA_GAP + CELL_PADDING


def fit_row_heights(table: ET.Element) -> None:
    """각 행 높이 = 그 행에서 시작하는 rowSpan=1 셀들의 필요 높이 최대값. 여러 행에 걸친 셀은 걸친 행 높이의 합을 받고,
    그 셀이 더 필요하면 걸친 행들에 나눠 더한다. 표 높이는 행 높이의 합."""
    trs = table.findall(HP + "tr")
    heights = [MIN_ROW_HEIGHT] * len(trs)
    spanning: list[tuple[int, int, ET.Element]] = []
    for r, tr in enumerate(trs):
        for tc in tr.findall(HP + "tc"):
            span = int(tc.find(HP + "cellSpan").get("rowSpan"))
            need = estimate_cell_height(tc)
            if span <= 1:
                heights[r] = max(heights[r], need)
            else:
                spanning.append((r, span, tc))
    for r, span, tc in spanning:
        covered = heights[r:r + span]
        shortfall = estimate_cell_height(tc) - sum(covered)
        if shortfall > 0:
            extra = -(-shortfall // span)
            for i in range(r, min(r + span, len(heights))):
                heights[i] += extra
    for r, tr in enumerate(trs):
        for tc in tr.findall(HP + "tc"):
            span = int(tc.find(HP + "cellSpan").get("rowSpan"))
            tc.find(HP + "cellSz").set("height", str(sum(heights[r:r + span])))
    size = table.find(HP + "sz")
    if size is not None:
        size.set("height", str(sum(heights)))


def fill_modules(section: ET.Element, modules: list[dict]) -> None:
    proto_p = module_table_paragraph(section)
    index = list(section).index(proto_p)
    section.remove(proto_p)
    # 양식 문단에 붙은 '작성필요' 메모 필드와 배치 캐시는 복제하지 않는다(메모 id가 겹치고, 캐시는 빈 쪽을 만든다)
    for run in proto_p.findall(HP + "run"):
        for ctrl in run.findall(HP + "ctrl"):
            if ctrl.find(HP + "fieldBegin") is not None or ctrl.find(HP + "fieldEnd") is not None:
                run.remove(ctrl)
    for seg in proto_p.findall(HP + "linesegarray"):
        proto_p.remove(seg)
    base_id = int(next(proto_p.iter(HP + "tbl")).get("id") or "1000000")
    for i, module in enumerate(modules):
        p = copy.deepcopy(proto_p)
        table = next(p.iter(HP + "tbl"))
        table.set("id", str(base_id + i))     # 복제한 표마다 다른 id
        fill_module_table(table, module)
        fit_row_heights(table)
        # 양식의 빈 모듈 표는 '글자처럼 취급'(treatAsChar=1)이라 한 쪽을 넘는 표가 쪽 경계에서 나뉘지 않고 아래로 밀려 나간다.
        # 실제 계획서처럼 0으로 두어 셀 단위(pageBreak=CELL)로 다음 쪽에 이어지게 한다.
        pos = table.find(HP + "pos")
        if pos is not None:
            pos.set("treatAsChar", "0")
        section.insert(index + i, p)


# ── 전체 ──────────────────────────────────────────────────────────────────────

def summary_from_modules(modules: list[dict]) -> list[dict]:
    return [{"코드": m["코드"], "명칭": m["명칭"], "LM 코드": f"LM{m['코드']}", "LM 명칭": m.get("학습모듈명") or m["명칭"], "집필진": "", "검토진": ""}
            for m in modules]


def build_plan(spec: dict, *, form: bytes | None = None) -> bytes:
    """spec → 채운 개발계획서 hwpx 바이트."""
    modules = [draft_module(m) for m in spec.get("모듈") or []]
    if not modules:
        raise ValueError("spec에 모듈(능력단위)이 하나는 있어야 합니다")
    summary = spec.get("총괄표") or summary_from_modules(modules)
    position = dict(spec.get("위치") or {})
    position.setdefault("모듈", [{"능력단위": m["명칭"], "학습모듈명": m["학습모듈명"]} for m in modules])
    if spec.get("기본", {}).get("세분류명") and not position.get("세분류"):
        position["세분류"] = [spec["기본"]["세분류명"]]
    form = form if form is not None else (files("ncs_core") / "data" / FORM_FILE).read_bytes()
    source = zipfile.ZipFile(io.BytesIO(form))
    sections = {name: ET.fromstring(source.read(name)) for name in source.namelist() if name.startswith("Contents/section")}
    front = next(root for name, root in sorted(sections.items()) if find_table(root, "(한글)세분류명") is not None)
    fill_basic(front, spec.get("기본") or {})
    fill_summary(front, summary)
    fill_position(front, position)
    for name in sorted(sections):
        try:
            module_table_paragraph(sections[name])
        except ValueError:
            continue
        fill_modules(sections[name], modules)
        break
    else:
        raise ValueError("양식에서 빈 모듈 표를 찾지 못했습니다")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename in sections:
                data = ET.tostring(sections[item.filename], encoding="utf-8", xml_declaration=True)
            elif item.filename == "Preview/PrvText.txt":
                data = f"NCS 학습모듈 개발계획서 초안 — {spec.get('기본', {}).get('세분류명', '')}".encode("utf-8")
            compress = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
            target.writestr(item, data, compress_type=compress)
    return out.getvalue()


def spec_from_plan(data: dict) -> dict:
    """ncs_plan.parsers.read_plan 결과(기존 계획서)에서 NCS 쪽만 뽑아 spec으로. 초안 생성 → 점검 왕복 테스트와 양식 이관에 쓴다."""
    return {
        "기본": data.get("기본") or {},
        "총괄표": [{k: (v or "") for k, v in e.items() if k != "행"} for e in (data.get("총괄표") or [])],
        "위치": {k: v for k, v in (data.get("위치") or {}).items() if k != "모듈"} | {"모듈": (data.get("위치") or {}).get("모듈") or []},
        "모듈": [{"코드": m["코드"], "명칭": m["명칭"], "정의": m["정의"],
                 "요소": [{"코드": e["코드"], "명칭": e["명칭"], "수행준거": e["수행준거"]} for e in m["요소"]]} for m in data.get("모듈") or []],
    }
