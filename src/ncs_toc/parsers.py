"""문단에서 차례, 개요, 본문 구조, 개발계획서 명칭을 추출한다.

sections는 [차례·개요 문단, 본문 문단]의 두 섹션 목록이다(pipeline이 실제 섹션을 연결한다).
"""

import re

from .config import DEFAULT_CONFIG, CheckConfig
from .patterns import (
    OV_SUB_BARE,
    BODY_SUB,
    EVAL_ITEM_END,
    EVAL_LABELS,
    HEAD_EVAL,
    HEAD_TEACH,
    NAV_HEAD,
    OV_LESSON,
    OV_SUB,
    TOC_LESSON,
    TOC_LINE,
    TOC_SUB,
    TOC_TAIL,
)

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


def parse_overview(sections) -> dict | None:
    """학습모듈의 개요 > 내용체계 → {'학습': [{'no','text'}], '내용': [{'no','sub','text'}]}"""
    lines = [l for l in sections[0] if l] if sections else []
    start = next((i for i, l in enumerate(lines) if re.fullmatch(r"학습모듈의\s*내용\s*체계", l)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if re.fullmatch(r"핵심\s*용어", lines[i])), len(lines))
    overview = {"학습": [], "내용": []}
    for line in lines[start + 1 : end]:
        if m := OV_SUB.match(line):
            overview["내용"].append({"no": int(m.group(1)), "sub": int(m.group(2)), "text": m.group(3).strip()})
        elif (m := OV_LESSON.match(line)) and int(m.group(1)) == len(overview["학습"]) + 1:
            overview["학습"].append({"no": int(m.group(1)), "text": m.group(2).strip()})
    return overview


def _navigator_runs(lines, n_lessons: int) -> list[list[dict]]:
    """내비게이터: '학습 1' 다음 줄이 이름, 이어서 '학습 2' …가 한 묶음(run)."""
    runs, k = [], 0
    while k < len(lines):
        head = NAV_HEAD.match(lines[k][1])
        if head and int(head.group(1)) == 1:
            run, no, j = [], 1, k
            while j + 1 < len(lines):
                nav = NAV_HEAD.match(lines[j][1])
                if not (nav and int(nav.group(1)) == no):
                    break
                run.append({"no": no, "text": lines[j + 1][1], "k": j})
                no += 1
                j += 2
            # 개수 차이는 ③ 내비게이터 항목의 비고로 보고한다.
            if len(run) >= (1 if n_lessons == 1 else 2):
                runs.append(run)
                k = j
                continue
        k += 1
    return runs


def _eval_candidates(lines, start: int, end: int, config: CheckConfig) -> list[str]:
    """평가 블록 안의 짧은 줄 = '학습 내용' 후보 (표를 못 읽을 때의 휴리스틱)."""
    out = []
    for _, line in lines[start:end]:
        if (
            len(line) <= config.eval_candidate_max_length
            and not re.match(r"^[-•·※\d(\[]", line)
            and line not in EVAL_LABELS
            and not NAV_HEAD.match(line)
            and not HEAD_EVAL.match(line)
            and not re.search(r"[.?!]$", line)
            and not EVAL_ITEM_END.search(line)
        ):
            out.append(line)
    return out


def parse_body(sections, n_lessons: int, cutoff: int | None = None, config: CheckConfig = DEFAULT_CONFIG) -> dict:
    """본문 → 내비게이터 묶음 / 학습 구간 / 필요지식 N-M. 제목 / 학습별 교수·평가 제목 위치와 평가 후보.

    cutoff: 참고 자료 시작 인덱스(raw) — 마지막 학습 구간을 여기서 끊는다.
    """
    raw = sections[1] if len(sections) > 1 else []
    lines = [(i, l) for i, l in enumerate(raw) if l]  # (원래 인덱스, 텍스트)
    nav_runs = _navigator_runs(lines, n_lessons)
    starts = [run[0]["k"] for run in nav_runs]
    last = next((k for k, (i, _) in enumerate(lines) if cutoff is not None and i >= cutoff), len(lines))
    spans = [(i + 1, starts[i], starts[i + 1] if i + 1 < len(starts) else last) for i in range(len(starts))]

    subs = []  # 필요지식 N-M. 제목 (같은 줄 또는 다음 줄)
    for k, (_, line) in enumerate(lines):
        if (m := BODY_SUB.match(line)) and len(line) < config.body_heading_max_length:
            text = m.group(3).strip() or (lines[k + 1][1] if k + 1 < len(lines) else "")
            if not re.search(r"\s\d+$", line):  # 차례 줄(끝 쪽수) 제외
                subs.append({"no": int(m.group(1)), "sub": int(m.group(2)), "text": text, "k": k})

    lessons = []
    for no, a, b in spans:
        segment = lines[a:b]
        teach = [a + j for j, (_, l) in enumerate(segment) if HEAD_TEACH.match(l)]
        evals = [a + j for j, (_, l) in enumerate(segment) if HEAD_EVAL.match(l)]
        candidates = _eval_candidates(lines, evals[0], b, config) if evals else []
        own_subs = [s for s in subs if a <= s["k"] < b and s["no"] == no]
        raw_end = lines[b][0] if b < len(lines) else (lines[-1][0] + 1 if lines else 0)
        lessons.append(
            {
                "no": no,
                "span": (a, b),
                "raw_span": (lines[a][0], raw_end),
                "teach": teach,
                "eval": evals,
                "eval_cands": candidates,
                "subs": own_subs,
            }
        )
    return {"lines": lines, "nav_runs": nav_runs, "spans": spans, "subs": subs, "lessons": lessons}


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
        if m := OV_SUB.match(line):
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
        if OV_SUB_BARE.fullmatch(line) or OV_SUB.match(line) or re.fullmatch(r"\d+\.\s+\S.*", line):
            return ""
        return line.strip()
    return ""
