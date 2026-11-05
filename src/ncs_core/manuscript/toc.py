"""차례 면과 개발계획서 명칭을 문단 줄에서 추출한다. 개요 내용체계는 overview.parse_overview가 읽는다.

sections는 [차례·개요 문단, 본문 문단]의 두 섹션 목록이다(각 pipeline이 실제 섹션을 연결한다).
"""

import re

from .patterns import PLAN_SUB, OV_SUB_BARE, OV_SUB_NAMED, TOC_LESSON, TOC_LINE, TOC_SUB, TOC_TAIL

TAIL_NAMES = {"참고자료": "참고 자료", "활용서식": "활용 서식", "부록": "부록"}


def parse_toc(sections) -> dict | None:
    """차례 블록 → {'학습': [{'no','text'}], '내용': [{'no','sub','text','page'}],
    '줄': [{'lesson','kind','page','after'}], '꼬리': {참고 자료: 쪽, ...}, 'span': (s, e),
    '건너뜀': [{'no','text','기대'}] — 번호가 이어지지 않아 학습으로 받지 않은 '학습 N.' 줄}"""
    from .structure import toc_title_index

    lines = [l for l in sections[0] if l] if sections else []
    # '차례' 제목이 둘일 때(앞에 깨진 자동 차례가 남은 원고) 학습 줄이 따르는 쪽을 고른다
    start = toc_title_index(lines)
    if start is None:
        return None
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if re.search(r"학습모듈의\s*개요$", lines[i]) and not re.search(r"\d+$", lines[i])
        ),
        len(lines),
    )
    toc = {"학습": [], "내용": [], "줄": [], "꼬리": {}, "span": (start, end), "건너뜀": []}
    for line in lines[start + 1 : end]:
        if m := TOC_LESSON.match(line):
            if int(m.group(1)) == len(toc["학습"]) + 1:
                toc["학습"].append({"no": int(m.group(1)), "text": m.group(2).strip()})
            else:
                # 번호가 이어지지 않는 '학습 N.' 줄. 학습으로 받지 않되 진단에서 알릴 수 있게 남긴다.
                toc["건너뜀"].append({"no": int(m.group(1)), "text": m.group(2).strip(), "기대": len(toc["학습"]) + 1})
        elif m := TOC_SUB.match(line):
            toc["내용"].append(
                {"no": int(m.group(1)), "sub": int(m.group(2)), "text": m.group(3).strip(), "page": m.group(4)}
            )
        elif m := TOC_LINE.match(line):
            kind = "교수·학습 방법" if "교수" in m.group(1) else "평가"
            lesson_no = len(toc["학습"])
            # after: 이 줄까지 읽은 해당 학습의 내용(N-M.) 줄 수. ④가 '블록 끝에 있는가'를 판단할 때 쓴다.
            after = sum(1 for s in toc["내용"] if s["no"] == lesson_no)
            toc["줄"].append({"lesson": lesson_no, "kind": kind, "page": m.group(2), "after": after})
        elif m := TOC_TAIL.match(line):
            toc["꼬리"][TAIL_NAMES[re.sub(r"\s+", "", m.group(1))]] = m.group(2)
    return toc


def parse_plan_toc(sections, module_code: str) -> dict | None:
    """개발계획서 → {'학습명': [...], '요소명': [...], '내용명': [{'no','sub','text'}]} (블록을 못 찾으면 None)

    sections에 Document를 주면 표를 셀 단위로 읽는다(변경승인 계획서의 '비고' 열 배제). 문단 목록이면 줄 단위로 읽는다.
    """
    if hasattr(sections, "tables"):
        from .plan_table import read_module_table

        if (table := read_module_table(sections, module_code)) is not None:
            return {"학습명": [f"{i}. {name}" for i, name in enumerate(table["학습명"], 1)],
                    "요소명": table["요소명"], "내용명": table["내용명"]}
        sections = sections.sections
    lines = [l for section in sections for l in section]
    code = module_code.replace("LM", "")
    start = next(
        (i for i, l in enumerate(lines) if l == code and i > 0 and lines[i - 1].startswith("능력단위 코드번호")),
        None,
    )
    if start is None:
        return None
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("NCS (수정 금지)")), len(lines))
    block = lines[start:end]
    plan = {"학습명": [], "요소명": [], "내용명": []}
    for i, line in enumerate(block):
        if re.fullmatch(rf"{re.escape(code)}\.\d+", line) and i + 1 < len(block):
            plan["요소명"].append(block[i + 1])
        if (m := PLAN_SUB.match(line)) and m.group(3):
            plan["내용명"].append({"no": int(m.group(1)), "sub": int(m.group(2)), "text": m.group(3).strip()})
        elif (m := OV_SUB_BARE.fullmatch(line)) and (text := _next_nonempty(block, i + 1)):
            # 실제 개발계획서(HWP)는 '1-1.'과 내용명이 한 셀 안의 두 문단으로 나뉜 경우가 있다.
            plan["내용명"].append({"no": int(m.group(1)), "sub": int(m.group(2)), "text": text})
        elif re.fullmatch(r"\d+\.\s+\S.*", line):
            plan["학습명"].append(line)
    return plan


def _next_nonempty(lines, start: int) -> str:
    """start 이후 첫 비어 있지 않은 줄. 번호·학습명 줄이면 내용명이 아니므로 빈 문자열."""
    for line in lines[start:]:
        if not line.strip():
            continue
        if OV_SUB_BARE.fullmatch(line) or OV_SUB_NAMED.match(line) or re.fullmatch(r"\d+\.\s+\S.*", line):
            return ""
        return line.strip()
    return ""
