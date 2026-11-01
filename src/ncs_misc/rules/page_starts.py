"""기타 ①: 학습모듈의 개요·내비게이터·교수·학습 방법·평가·참고 자료·활용 서식·부록이 새 쪽에서 시작하는가.

hwpx 문단의 '쪽 나누기' 표식(Document.page_breaks)을 본다. 머리 문단 자신 또는 그 앞의 빈 문단(표 틀 문단 포함)에
쪽 나누기가 있으면 O. 섹션 첫 문단은 당연히 새 쪽이다. hwp는 표식을 읽을 수 없어 △.
"""

import re

from ncs_core import O, TRI, X

from .common import row

HEADS = (  # (이름, 머리 문단을 찾는 정규식)
    ("교수·학습 방법", re.compile(r"^교수\s*\W{0,3}\s*학습\s*방법$")),
    ("평가", re.compile(r"^평\s*가$")),
)
OVERVIEW = re.compile(r"^학습\s*모듈의\s*개요$")


def starts_new_page(index: int, paragraphs: list[str], page_breaks: frozenset[int], table_paragraphs=frozenset()) -> bool:
    """머리 문단 index가 새 쪽에서 시작하는가 — 자신, 또는 앞의 빈 문단·같은 틀(표) 안 문단들 중에 쪽 나누기가 있으면 참.

    머리가 표 틀 안에 있으면('학습 1 | 교수·학습 방법' 꼴) 쪽 나누기는 틀을 담은 문단에 있으므로 틀 안 문단은 건너뛴다.
    """
    if index == 0:
        return True
    in_frame = index in table_paragraphs
    j = index
    while j >= 0:
        if j in page_breaks:
            return True
        if j < index and (paragraphs[j] or "").strip() and not (in_frame and j in table_paragraphs):
            return False
        if in_frame and j not in table_paragraphs and j < index:
            in_frame = False  # 틀을 담은 문단(표 밖)을 지나면 그 앞은 보통 문단
        j -= 1
    return True  # 섹션 맨 앞까지 빈 문단뿐


def check_page_starts(context) -> list[dict]:
    manuscript, config = context.manuscript, context.config
    body_section, front_section = config.body_section, config.front_section
    body = manuscript.sections[body_section]
    breaks = manuscript.section_page_breaks(body_section)
    targets = []  # (이름, 섹션, 문단 인덱스, 위치 표기)
    front = manuscript.sections[front_section]
    overview = next((i for i, t in enumerate(front) if OVERVIEW.match(t.strip())), None)
    if overview is not None:
        targets.append(("학습모듈의 개요", front_section, overview, ""))
    for lesson in context.body["lessons"]:
        start = lesson["raw_span"][0]
        targets.append((f"내비게이터(학습 {lesson['no']})", body_section, start, f"학습 {lesson['no']}"))
        a, b = lesson["raw_span"]
        for name, pattern in HEADS:
            hits = [i for i in range(a, b) if pattern.match((body[i] or "").strip())]
            for i in hits:
                targets.append((name, body_section, i, f"학습 {lesson['no']}"))
    for name in ("참고 자료", "활용 서식", "부록"):
        found = context.presence.get(name) or {}
        if found.get("있음") and found.get("k") is not None:
            targets.append((name, body_section, found["k"], ""))
    rows = []
    for name, section, index, where in targets:
        region = f"section{section} > {name}" + (f" ({where})" if where else "")
        checks, notes = {}, {}
        section_breaks = manuscript.section_page_breaks(section)
        if section_breaks is None:
            checks["새 쪽 시작"] = TRI
            notes["새 쪽 시작"] = "hwp는 쪽 나누기 표식을 읽을 수 없음 — hwpx로 확인"
        else:
            ok = starts_new_page(index, manuscript.sections[section], section_breaks, manuscript.section_table_paragraphs(section) or frozenset())
            checks["새 쪽 시작"] = O if ok else X
            if not ok:
                notes["새 쪽 시작"] = f"{name} 머리(p{index}) 앞에 쪽 나누기가 없음"
        rows.append(row("①", region, where, {"머리": name, "문단": index}, checks, notes, f"{name} 앞에 쪽 나누기 삽입"))
    if not rows:
        rows.append(row("①", "section1", "", None, {"새 쪽 시작": TRI}, {"새 쪽 시작": "검사할 머리(개요·내비게이터·교수·학습 방법·평가·참고 자료·활용 서식·부록)를 찾지 못함"}))
    return rows
