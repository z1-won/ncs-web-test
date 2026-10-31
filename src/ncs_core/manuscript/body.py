"""본문 섹션의 구조를 읽는다: 내비게이터 묶음, 학습 구간, 필요 지식 N-M. 제목, 학습별 교수·평가 제목 위치."""

import re

from .config import DEFAULT_PARSE_CONFIG, ParseConfig
from .patterns import BODY_SUB, EVAL_ITEM_END, EVAL_LABELS, HEAD_EVAL, HEAD_TEACH, NAV_HEAD


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


def _eval_candidates(lines, start: int, end: int, config: ParseConfig) -> list[str]:
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


def parse_body(
    sections, n_lessons: int, cutoff: int | None = None, config: ParseConfig = DEFAULT_PARSE_CONFIG
) -> dict:
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
