"""개발계획서 모듈 블록에서 학습 내용별 학습 목표(수행 준거) 문장을 읽는다.

블록 기준은 ncs_overview.parsers.parse_plan과 같다. 그 파서는 학습명·내용명·요소만 읽으므로 여기서는 목표 문장을 더 읽는다.
"""

import re

from ncs_core import Document
from ncs_overview.patterns import ELEMENT_CODE, OV_SUB, PLAN_LESSON

GOAL_SENTENCE = re.compile(r"^\d+\.\d+\s+\S")  # '1.1 호텔의 …할 수 있다.'


def parse_plan_goals(document: Document, module_code: str) -> dict | None:
    """→ {'학습명': [...], '요소명': [...], '내용': {(N, M): {'text', 'goals': [...]}}}. 블록을 못 찾으면 None."""
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
        if m := OV_SUB.match(line):
            text = m.group(3).strip()
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
