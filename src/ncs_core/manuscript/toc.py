"""차례 면·개요 내용체계(문단 기준)·개발계획서 명칭을 문단 줄에서 추출한다.

sections는 [차례·개요 문단, 본문 문단]의 두 섹션 목록이다(각 pipeline이 실제 섹션을 연결한다).
"""

import re

from .patterns import OV_LESSON, OV_SUB_BARE, OV_SUB_NAMED, TOC_LESSON, TOC_LINE, TOC_SUB, TOC_TAIL

TAIL_NAMES = {"참고자료": "참고 자료", "활용서식": "활용 서식", "부록": "부록"}


def parse_toc(sections) -> dict | None:
    """차례 블록 → {'학습': [{'no','text'}], '내용': [{'no','sub','text','page'}],
    '줄': [{'lesson','kind','page','after'}], '꼬리': {참고 자료: 쪽, ...}, 'span': (s, e)}"""
    lines = [l for l in sections[0] if l] if sections else []
    start = next((i for i, l in enumerate(lines) if re.fullmatch(r"차\s*례", l)), None)
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
    toc = {"학습": [], "내용": [], "줄": [], "꼬리": {}, "span": (start, end)}
    for line in lines[start + 1 : end]:
        if (m := TOC_LESSON.match(line)) and int(m.group(1)) == len(toc["학습"]) + 1:
            toc["학습"].append({"no": int(m.group(1)), "text": m.group(2).strip()})
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


def parse_overview_lines(sections) -> dict | None:
    """학습모듈의 개요 > 내용체계를 문단 줄로 읽는다 → {'학습': [{'no','text'}], '내용': [{'no','sub','text'}]}.

    표 셀 우선으로 읽는 overview.parse_overview와 달리 문단 순서만 본다(차례 검수 ③의 기준).
    """
    lines = [l for l in sections[0] if l] if sections else []
    start = next((i for i, l in enumerate(lines) if re.fullmatch(r"학습모듈의\s*내용\s*체계", l)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if re.fullmatch(r"핵심\s*용어", lines[i])), len(lines))
    overview = {"학습": [], "내용": []}
    for line in lines[start + 1 : end]:
        if m := OV_SUB_NAMED.match(line):
            overview["내용"].append({"no": int(m.group(1)), "sub": int(m.group(2)), "text": m.group(3).strip()})
        elif (m := OV_LESSON.match(line)) and int(m.group(1)) == len(overview["학습"]) + 1:
            overview["학습"].append({"no": int(m.group(1)), "text": m.group(2).strip()})
    return overview


def parse_plan_toc(sections, module_code: str) -> dict | None:
    """개발계획서 → {'학습명': [...], '요소명': [...], '내용명': [{'no','sub','text'}]} (블록을 못 찾으면 None)"""
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
        if m := OV_SUB_NAMED.match(line):
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
