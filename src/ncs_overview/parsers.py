"""학습모듈의 개요(목표·선수학습·내용체계·핵심 용어)와 개발계획서 모듈 블록을 추출한다.

내용체계는 표 셀(hwp·hwpx 모두 표 셀 텍스트가 있다)을 우선 읽고, 표를 못 찾으면 문단 줄로 읽는다.
차례 검수(ncs_toc.parsers)의 OV_LESSON/OV_SUB 규칙과 같은 정규식을 쓴다.
"""

import re

from ncs_core import Document, Table

from .patterns import (
    ELEMENT_CODE,
    HEAD_GOAL,
    HEAD_OVERVIEW,
    HEAD_PREREQ,
    HEAD_STRUCTURE,
    HEAD_TERMS,
    OV_LESSON,
    OV_SUB,
    PLAN_LESSON,
)
from .text import split_items

HEADINGS = (HEAD_GOAL, HEAD_PREREQ, HEAD_STRUCTURE, HEAD_TERMS)
STRUCTURE_HEADERS = ("학습", "학습 내용", "코드번호", "요소 명칭")


def _block(lines: list[tuple[int, str]], head, stop_heads) -> tuple[int | None, list[tuple[int, str]]]:
    """head 제목 다음부터 다음 제목(stop_heads) 전까지의 (문단 인덱스, 텍스트)."""
    start = next((k for k, (_, l) in enumerate(lines) if head.match(l)), None)
    if start is None:
        return None, []
    out = []
    for i, l in lines[start + 1 :]:
        if any(h.match(l) for h in stop_heads):
            break
        out.append((i, l))
    return lines[start][0], out


def _structure_from_table(table: Table) -> dict | None:
    cells = table["cells"]
    headers: dict[str, tuple[int, int]] = {}
    for (r, c), v in sorted(cells.items()):
        key = v.replace(" ", "")
        for name in STRUCTURE_HEADERS:
            if key == name.replace(" ", "") and name not in headers:
                headers[name] = (r, c)
    if not {"학습", "코드번호"} <= headers.keys():
        return None
    header_row = max(r for r, _ in headers.values())
    col = {name: c for name, (_, c) in headers.items()}
    content_col = col.get("학습 내용", col["학습"] + 1)
    name_col = col.get("요소 명칭", col["코드번호"] + 1)
    lessons, contents, elements = [], [], []
    rows = sorted({r for r, _ in cells if r > header_row})
    for r in rows:
        lesson, content = cells.get((r, col["학습"]), ""), cells.get((r, content_col), "")
        code, name = cells.get((r, col["코드번호"]), ""), cells.get((r, name_col), "")
        if m := OV_LESSON.match(lesson):
            lessons.append({"no": int(m.group(1)), "text": m.group(2).strip(), "row": r})
        if m := OV_SUB.match(content):
            contents.append({"no": int(m.group(1)), "sub": int(m.group(2)), "text": m.group(3).strip(), "row": r})
        for part in code.split():
            if ELEMENT_CODE.match(part) and not any(e["code"] == part for e in elements):
                elements.append({"code": part, "name": name, "row": r})
    return {"학습": lessons, "내용": contents, "요소": elements, "근거": f"표 (p{table['paragraph']})"}


def _structure_from_lines(block: list[tuple[int, str]]) -> dict:
    lessons, contents, elements = [], [], []
    for k, (i, l) in enumerate(block):
        if (m := OV_LESSON.match(l)) and int(m.group(1)) == len(lessons) + 1:
            lessons.append({"no": int(m.group(1)), "text": m.group(2).strip(), "row": i})
        elif m := OV_SUB.match(l):
            text = m.group(3).strip() or (block[k + 1][1] if k + 1 < len(block) else "")
            contents.append({"no": int(m.group(1)), "sub": int(m.group(2)), "text": text, "row": i})
        elif m := ELEMENT_CODE.match(l):
            # 요소 명칭은 다음 줄(셀 안에서 줄이 나뉘면 두 줄)
            name_parts = []
            for _, nxt in block[k + 1 : k + 3]:
                if OV_LESSON.match(nxt) or OV_SUB.match(nxt) or ELEMENT_CODE.match(nxt):
                    break
                name_parts.append(nxt)
            elements.append({"code": l, "name": " ".join(name_parts).strip(), "row": i})
    return {"학습": lessons, "내용": contents, "요소": elements, "근거": "문단 줄"}


def parse_overview(document: Document, section: int) -> dict:
    """→ {'목표': {'text','p'}|None, '선수학습': {'items','text','p'}|None,
         '내용체계': {...}|None, '핵심 용어': {'items','text','p'}|None, '개요 제목 p': int|None}"""
    raw = document.sections[section] if section < len(document.sections) else []
    lines = [(i, l) for i, l in enumerate(raw) if l]
    head = next((i for i, l in lines if HEAD_OVERVIEW.search(l) and not re.search(r"\d+$", l)), None)
    if head is not None:
        lines = [(i, l) for i, l in lines if i > head]

    out: dict = {"개요 제목 p": head}
    p, block = _block(lines, HEAD_GOAL, HEADINGS)
    out["목표"] = {"text": " ".join(l for _, l in block), "p": block[0][0]} if block else None
    p, block = _block(lines, HEAD_PREREQ, HEADINGS)
    if block:
        text = " ".join(l for _, l in block)
        out["선수학습"] = {"items": split_items(text), "text": text, "p": block[0][0]}
    else:
        out["선수학습"] = None
    p, block = _block(lines, HEAD_STRUCTURE, HEADINGS)
    structure = None
    if p is not None:
        tables = [t for t in document.section_tables(section) if t["paragraph"] >= p]
        structure = next((s for t in tables if (s := _structure_from_table(t))), None)
        if structure is None and block:
            structure = _structure_from_lines(block)
    out["내용체계"] = structure
    p, block = _block(lines, HEAD_TERMS, HEADINGS)
    if block:
        text = " ".join(l for _, l in block)
        out["핵심 용어"] = {"items": split_items(text), "text": text, "p": block[0][0]}
    else:
        out["핵심 용어"] = None
    return out


def parse_plan(document: Document, module_code: str) -> dict | None:
    """개발계획서 모듈 블록 → {'정의','목표','학습명':[...],'내용명':[{no,sub,text}],'요소':[{code,name}]}.

    블록은 '능력단위 코드번호' 다음 줄의 코드부터 'NCS (수정 금지)' 전까지 (ncs_toc.parsers.parse_plan_toc와 같은 기준).
    """
    lines = [l for section in document.sections for l in section]
    code = module_code.replace("LM", "")
    start = next(
        (i for i, l in enumerate(lines) if l == code and i > 0 and lines[i - 1].startswith("능력단위 코드번호")),
        None,
    )
    if start is None:
        return None
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("NCS (수정 금지)")), len(lines))
    block = [l for l in lines[start:end] if l]
    plan = {"정의": None, "목표": None, "학습명": [], "내용명": [], "요소": []}
    for i, line in enumerate(block):
        nxt = block[i + 1] if i + 1 < len(block) else ""
        if re.fullmatch(r"능력단위\s*정의", line) and plan["정의"] is None:
            plan["정의"] = nxt
        elif re.fullmatch(r"학습모듈의\s*목표", line) and plan["목표"] is None:
            plan["목표"] = nxt
        elif (m := ELEMENT_CODE.match(line)) and m.group(1) == code:
            plan["요소"].append({"code": line, "name": nxt})
        elif m := OV_SUB.match(line):
            text = m.group(3).strip() or nxt
            plan["내용명"].append({"no": int(m.group(1)), "sub": int(m.group(2)), "text": text})
        elif (m := PLAN_LESSON.match(line)) and int(m.group(1)) == len(plan["학습명"]) + 1:
            plan["학습명"].append(m.group(2).strip())
    return plan
