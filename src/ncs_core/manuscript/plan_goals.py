"""개발계획서 모듈 블록에서 학습 내용별 학습 목표(수행 준거) 문장을 읽는다.

블록 기준은 parse_plan과 같다. 그 파서는 학습명·내용명·요소만 읽으므로 여기서는 목표 문장을 더 읽는다.
필요 지식 ⑤(본문 학습 목표)와 평가 ②(평가 준거 학습 목표)가 함께 쓴다.
"""

import re

from ..documents import Document
from .patterns import ELEMENT_CODE, PLAN_LESSON, PLAN_SUB

GOAL_SENTENCE = re.compile(r"^\d+\.\d+\s+\S")  # '1.1 호텔의 …할 수 있다.'


def parse_plan_goals(document: Document, module_code: str) -> dict | None:
    """→ {'학습명': [...], '요소명': [...], '내용': {(N, M): {'text', 'goals': [...]}}}. 블록을 못 찾으면 None.

    표를 셀 단위로 읽을 수 있으면 그것을 쓴다(변경승인 계획서의 '비고' 열 배제). 못 읽으면 줄 단위로 읽는다.
    """
    from .plan_table import read_module_table

    if (table := read_module_table(document, module_code)) is not None:
        return {"학습명": [f"{i}. {name}" for i, name in enumerate(table["학습명"], 1)], "요소명": table["요소명"], "내용": table["내용"]}
    lines = [l for section in document.sections for l in section]
    code = module_code.replace("LM", "")
    start = next(
        (i for i, l in enumerate(lines) if l == code and i > 0 and lines[i - 1].startswith("능력단위 코드번호")),
        None,
    )
    if start is None:
        return None
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("NCS (수정 금지)") or lines[i].startswith("능력단위 코드번호")),
        len(lines),
    )
    block = [l for l in lines[start:end] if l]
    plan, current, i = {"학습명": [], "요소명": [], "내용": {}}, None, 0
    while i < len(block):
        line = block[i]
        if (m := ELEMENT_CODE.match(line)) and m.group(1) == code and i + 1 < len(block):
            plan["요소명"].append(block[i + 1])
            current = None
            i += 2
            continue
        if m := PLAN_SUB.match(line):
            text = (m.group(3) or "").strip()
            if not text and i + 1 < len(block):
                text = block[i + 1]
                i += 1
            current = (int(m.group(1)), int(m.group(2)))
            plan["내용"][current] = {"text": text, "goals": []}
        elif PLAN_LESSON.match(line):
            plan["학습명"].append(line)
            current = None
        elif current and GOAL_SENTENCE.match(line):
            plan["내용"][current]["goals"].append(line)
        i += 1
    return plan
