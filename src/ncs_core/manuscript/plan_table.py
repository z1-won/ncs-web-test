"""개발계획서 모듈 블록을 표(셀) 단위로 읽는다.

기존 파서(parse_plan·parse_plan_toc·parse_plan_goals)는 문단을 한 줄로 늘어놓고 패턴으로 골라 읽었다.
그런데 변경승인 계획서는 표 오른쪽에 '비고' 열이 있고 그 안에 "변경 사유: … 1-1. 학습내용명 변경(기존 A → B)" 같은
문장이 들어 있어, 줄 단위로 읽으면 비고의 문장이 학습 내용명·학습 목표로 섞여 들어간다.
표를 열 이름(학습명 / 학습내용명 / 학습 목표)으로 읽으면 비고 열은 자연히 제외된다.

표를 못 찾으면 None을 돌려주고, 각 파서는 기존 줄 단위 읽기로 돌아간다.
"""

import re

from ..documents import Document
from .patterns import PLAN_LESSON, PLAN_SUB

ELEMENT_IN_CELL = re.compile(r"^(\d{10}_\d+v\d+)\.(\d+)\s*(.*)$")  # '1203020401_23v3.1 연회 행사 고객사 분류'
GOAL_SPLIT = re.compile(r"\s+(?=\d+\.\d+\s)")                     # '1.1 … 있다. 1.2 …' → 문장별
HEAD_LESSON = re.compile(r"^학\s*습\s*명$")
HEAD_SUB = re.compile(r"^학\s*습\s*내\s*용\s*명$")
HEAD_GOAL = re.compile(r"^학\s*습\s*목\s*표$")


def _header_columns(cells: dict, rows: int, cols: int) -> tuple[int, dict[str, int]] | None:
    """(머리 행 번호, {'학습명': 열, '내용명': 열, '목표': 열}) — 머리 행을 못 찾으면 None."""
    for r in range(rows):
        found = {}
        for c in range(cols):
            text = cells.get((r, c), "")
            if HEAD_LESSON.match(text):
                found["학습명"] = c
            elif HEAD_SUB.match(text):
                found["내용명"] = c
            elif HEAD_GOAL.match(text):
                found["목표"] = c
        if "학습명" in found and "내용명" in found:
            return r, found
    return None


def find_module_table(document: Document, module_code: str) -> dict | None:
    """'능력단위 코드번호' 칸 옆에 이 모듈의 코드가 적힌 표."""
    code = module_code.replace("LM", "")
    for table in document.tables:
        cells = table["cells"]
        for (r, c), text in cells.items():
            if text.startswith("능력단위 코드번호") and cells.get((r, c + 1), "") == code:
                return table
    return None


def _labelled(cells: dict, label: re.Pattern) -> str | None:
    for (r, c), text in cells.items():
        if label.fullmatch(text):
            return cells.get((r, c + 1)) or None
    return None


def read_module_table(document: Document, module_code: str) -> dict | None:
    """모듈 표 → {'정의','목표','학습명':[...],'내용명':[{no,sub,text}],'요소':[{code,name}],'요소명':[...],
    '내용':{(no,sub):{'text','goals':[...]}}}. 표 또는 머리 행을 못 찾으면 None."""
    table = find_module_table(document, module_code)
    if table is None:
        return None
    cells, rows, cols = table["cells"], table["rows"], table["cols"]
    header = _header_columns(cells, rows, cols)
    if header is None:
        return None
    head_row, col = header
    plan = {
        "정의": _labelled(cells, re.compile(r"능력단위\s*정의")),
        "목표": _labelled(cells, re.compile(r"학습모듈의\s*목표")),
        "학습명": [], "내용명": [], "요소": [], "요소명": [], "내용": {},
    }
    code = module_code.replace("LM", "")
    for r in range(head_row + 1, rows):
        element = cells.get((r, 0), "")
        if (m := ELEMENT_IN_CELL.match(element)) and m.group(1) == code:
            plan["요소"].append({"code": f"{m.group(1)}.{m.group(2)}", "name": m.group(3).strip()})
            plan["요소명"].append(m.group(3).strip())
        lesson = cells.get((r, col["학습명"]), "")
        if m := PLAN_LESSON.match(lesson):
            plan["학습명"].append(m.group(2).strip())
        sub = cells.get((r, col["내용명"]), "")
        if m := PLAN_SUB.match(sub):
            no, sub_no, text = int(m.group(1)), int(m.group(2)), (m.group(3) or "").strip()
            plan["내용명"].append({"no": no, "sub": sub_no, "text": text})
            goals_text = cells.get((r, col["목표"]), "") if "목표" in col else ""
            goals = [g.strip() for g in GOAL_SPLIT.split(goals_text) if g.strip()] if goals_text else []
            plan["내용"][(no, sub_no)] = {"text": text, "goals": goals}
    if not plan["학습명"] and not plan["내용명"]:
        return None
    return plan
