"""학습별 '평가' 구역 읽기 — 평가 준거 표(학습 내용별 학습 목표), 평가 방법 목록, 방법 표 수.

구조(실데이터):
    평 가
      평가 준거      • 평가자는 … 평가해야 한다.
        [표] 학습 내용 | 학습 목표 | 성취수준(상·중·하)   ← 학습 내용 셀은 병합되어 첫 행에만, 목표는 행마다 "- …할 수 있다."
      평가 방법      • 서술형 시험 / • 평가자 질문 / • 역할 연기
        [표]×방법 수  학습 내용 | 평가 항목 | 성취수준
      피드백         [표] 1. 서술형 시험 / - 보충… / - 심화…  2. 평가자 질문 …   ← 방법마다 'N. 방법명' 블록
평가 구역의 시작은 parse_body의 lessons[*]["eval"](평가 머리), 끝은 raw_span 끝이다.
"""

import re

from ncs_core import Document

HEAD_CRITERIA = re.compile(r"^평가\s*준거$")
HEAD_METHOD = re.compile(r"^평가\s*방법$")
HEAD_FEEDBACK = re.compile(r"^피드백$")
BULLET = re.compile(r"^[•·▪ㆍ‧◦○∙●\-–]\s*")  # ∙(U+2219)·●도 실데이터(SW제품기획 최종본)의 글머리
MEMO = re.compile(r"^[★▶※]|要")
FEEDBACK_BLOCK = re.compile(r"(?:^|\s)(\d{1,2})\.\s*([^\d\-•·.]{1,30}?)\s*$")  # 'N. 방법명'(마침표 없는 짧은 이름; 앞에 변경추적 찌꺼기가 붙어도 찾음)


def _squash(text: str) -> str:
    return re.sub(r"\s", "", text or "")


def table_kind(table: dict):
    """표 머리로 종류를 정한다 → ('평가 준거'|'평가 방법', 머리 행, 학습 내용 열, 값 열) 또는 None."""
    cells = table["cells"]
    heads = [(r, c) for (r, c), v in cells.items() if _squash(v) == "학습내용"]
    if len(heads) != 1:
        return None
    header_row, name_col = heads[0]
    for (r, c), v in cells.items():
        if r != header_row:
            continue
        key = _squash(v)
        if key.startswith("학습목표"):
            return "평가 준거", header_row, name_col, c
        if key.startswith("평가항목"):
            return "평가 방법", header_row, name_col, c
    return None


def criteria_units(table: dict, header_row: int, name_col: int, value_col: int) -> list[dict]:
    """평가 준거 표 → [{'name': 학습 내용명, 'goals': [목표 문장…], 'row': 첫 행}]. 병합된 학습 내용 셀은 첫 행에만 있다."""
    units, current = [], None
    rows = sorted({r for (r, _) in table["cells"] if r > header_row})
    for r in rows:
        name = (table["cells"].get((r, name_col)) or "").strip()
        value = (table["cells"].get((r, value_col)) or "").strip()
        if name and not re.fullmatch(r"[상중하]", name):
            current = {"name": name, "goals": [], "row": r}
            units.append(current)
        if current is not None and value and not re.fullmatch(r"[상중하]", value):
            current["goals"].append(value)
    return units


HEAD_LOOKAHEAD = 40  # 평가 머리 뒤 이 범위 안에 '평가 준거'가 있어야 진짜 평가 구역 머리


def eval_head(lesson: dict, body: dict, paragraphs: list[str]) -> int | None:
    """학습의 평가 머리(body['lines'] 인덱스). 코어가 후보를 여럿 주면 바로 뒤에 '평가 준거'가 오는 하나를 고른다.

    한 학습 안에 '평가'만 적힌 문단이 둘 이상이면(표 머리 칸 등) 코어는 구역 시작을 정하지 못한다
    (SW제품기획 최종본 0402·0407). 진짜 평가 구역은 '평가 → 평가 준거 → 평가 방법 → 피드백' 순서라 '평가 준거'로 가린다.
    그래도 하나로 좁혀지지 않으면 None.
    """
    candidates = lesson["eval"]
    if len(candidates) == 1:
        return candidates[0]
    starts = [body["lines"][c][0] for c in candidates]
    real = []
    for n, (c, start) in enumerate(zip(candidates, starts)):
        # 다음 후보 전까지만 본다 — 앞의 가짜 머리가 뒤 진짜 머리의 '평가 준거'를 제 것으로 세지 않게
        stop = min([len(paragraphs), start + HEAD_LOOKAHEAD] + [s for s in starts[n + 1:] if s > start])
        if any(HEAD_CRITERIA.match((paragraphs[j] or "").strip()) for j in range(start + 1, stop)):
            real.append(c)
    return real[0] if len(real) == 1 else None


def eval_regions(manuscript: Document, body: dict, body_section: int) -> list[dict]:
    """학습마다 {'lesson', 'start', 'end', 'found': bool, 'criteria': [표별 units], 'criteria_tables': n,
    'methods': [방법 이름…], 'method_tables': n, 'feedback_found': bool, 'feedback': [{'no','name','idx','text'}], 'notes': [...]}."""
    paragraphs = manuscript.sections[body_section]
    table_paragraphs = manuscript.section_table_paragraphs(body_section) or frozenset()
    aside = manuscript.section_aside_paragraphs(body_section) or frozenset()
    numbers = manuscript.section_numbers(body_section)
    tables = manuscript.section_tables(body_section)
    out = []
    for lesson in body["lessons"]:
        info = {"lesson": lesson["no"], "found": False, "criteria": [], "criteria_tables": 0, "methods": [],
                "method_tables": 0, "feedback_found": False, "feedback": [], "notes": []}
        head = eval_head(lesson, body, paragraphs)
        if head is None:
            info["notes"].append("평가 구역의 시작을 유일하게 식별하지 못함" if lesson["eval"] else "평가 머리를 찾지 못함")
            out.append(info)
            continue
        start, end = body["lines"][head][0], lesson["raw_span"][1]
        info.update(found=True, start=start, end=end)
        for table in tables:
            if not start <= table["paragraph"] < end:
                continue
            kind = table_kind(table)
            if kind is None:
                continue
            name, header_row, name_col, value_col = kind
            if name == "평가 준거":
                info["criteria_tables"] += 1
                info["criteria"].append(criteria_units(table, header_row, name_col, value_col))
            else:
                info["method_tables"] += 1
        part, block = None, None
        for i in range(start, end):
            text = (paragraphs[i] or "").strip()
            if not text or i in aside:
                continue
            if HEAD_METHOD.match(text):
                part = "method"
                continue
            if HEAD_FEEDBACK.match(text):
                part, info["feedback_found"] = "feedback", True
                continue
            if HEAD_CRITERIA.match(text):
                part = None
                continue
            if part == "method" and i not in table_paragraphs and not MEMO.search(text):
                auto = numbers[i] if numbers is not None and i < len(numbers) else None
                if BULLET.match(text) or auto:
                    info["methods"].append({"idx": i, "name": BULLET.sub("", text).strip()})
            elif part == "feedback" and not MEMO.search(text):
                if not BULLET.match(text) and (m := FEEDBACK_BLOCK.search(text)):
                    block = {"no": int(m.group(1)), "name": m.group(2).strip(), "idx": i, "text": ""}
                    info["feedback"].append(block)
                elif block is not None:
                    block["text"] = (block["text"] + " " + text).strip()
        out.append(info)
    return out
