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


NAV_CURRENT_STYLE = re.compile(r"^큰학습-(제목|숫자)$")  # 내비게이터 묶음에서 '지금 학습'만 쓰는 스타일(나머지는 큰학습-네비게이터)


def _run_lessons(nav_runs: list[list[dict]], lines, styles) -> list[int]:
    """묶음마다 '이 묶음이 몇 번째 학습인가'.

    원고에 학습 1 본문이 없고 학습 2부터 시작하는 경우가 있어(연회 행사 진행), 묶음 순서 = 학습 번호로 두면 전체가 한 칸씩
    어긋난다. hwpx는 묶음 안에서 강조된 항목(큰학습-제목/숫자 스타일)이 지금 학습이므로 그것으로 읽고, 스타일이 없거나
    읽은 번호가 순서대로가 아니면 묶음 순서로 돌아간다.
    """
    ordinal = list(range(1, len(nav_runs) + 1))
    if styles:
        found = []
        for run in nav_runs:
            current = [item["no"] for item in run
                       if any(NAV_CURRENT_STYLE.match(styles[lines[k][0]] or "") for k in (item["k"], item["k"] + 1) if k < len(lines))]
            if len(current) != 1:
                break
            found.append(current[0])
        else:
            if found == sorted(set(found)):
                return found
    # 스타일이 없으면(hwp) 묶음 뒤 첫 'N-M.' 제목의 N으로 읽는다
    starts = [run[0]["k"] for run in nav_runs] + [len(lines)]
    found = []
    for a, b in zip(starts, starts[1:]):
        head = next((int(m.group(1)) for _, line in lines[a:b] if (m := BODY_SUB.match(line)) and not re.search(r"\s\d+$", line)), None)
        if head is None:
            return ordinal
        found.append(head)
    return found if found == sorted(set(found)) else ordinal


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
    sections,
    n_lessons: int,
    cutoff: int | None = None,
    config: ParseConfig = DEFAULT_PARSE_CONFIG,
    table_paragraphs: frozenset[int] | set[int] | None = None,
    aside_paragraphs: frozenset[int] | set[int] | None = None,
    styles: list[str] | None = None,
) -> dict:
    """본문 → 내비게이터 묶음 / 학습 구간 / 필요지식 N-M. 제목 / 학습별 교수·평가 제목 위치와 평가 후보.

    styles: 본문 섹션 문단별 스타일 이름(raw 인덱스). 있으면 내비게이터 묶음의 강조 항목으로 학습 번호를 읽는다(_run_lessons).

    cutoff: 참고 자료 시작 인덱스(raw) — 마지막 학습 구간을 여기서 끊는다.
    aside_paragraphs: 본문 밖 문단(메모·머리말·꼬리말·각주) 인덱스(raw). 구조 읽기에서 제외한다 — 에디터 메모가
        '학습 목표' 줄 바로 아래에 끼어 있으면 목표 문장을 못 읽는 식의 오류를 막는다.
    table_paragraphs: 본문 섹션에서 표 셀 안에 든 문단 인덱스(raw). 같은 N-M 번호가 여러 번 나오면
        표 밖 문단을 제목으로 우선하고, 없으면 처음 나온 것을 쓴다(평가·수행 내용 표의 "1-1. 명" 셀이
        본문 제목을 덮어쓰지 않게). None이면 처음 나온 것만 쓴다.
    """
    raw = sections[1] if len(sections) > 1 else []
    aside = aside_paragraphs or frozenset()
    lines = [(i, l) for i, l in enumerate(raw) if l and i not in aside]  # (원래 인덱스, 텍스트)
    nav_runs = _navigator_runs(lines, n_lessons)
    starts = [run[0]["k"] for run in nav_runs]
    last = next((k for k, (i, _) in enumerate(lines) if cutoff is not None and i >= cutoff), len(lines))
    numbers = _run_lessons(nav_runs, lines, styles)
    spans = [(numbers[i], starts[i], starts[i + 1] if i + 1 < len(starts) else last) for i in range(len(starts))]

    # 필요지식 N-M. 제목 (같은 줄 또는 다음 줄). 같은 번호가 여러 번이면 표 밖 문단 → 먼저 나온 것 순으로 하나만.
    in_table = table_paragraphs or frozenset()
    candidates: dict[tuple[int, int], list[dict]] = {}
    for k, (raw_index, line) in enumerate(lines):
        if (m := BODY_SUB.match(line)) and len(line) < config.body_heading_max_length:
            text = m.group(3).strip() or (lines[k + 1][1] if k + 1 < len(lines) else "")
            if not re.search(r"\s\d+$", line):  # 차례 줄(끝 쪽수) 제외
                key = (int(m.group(1)), int(m.group(2)))
                candidates.setdefault(key, []).append(
                    {"no": key[0], "sub": key[1], "text": text, "k": k, "in_table": raw_index in in_table}
                )
    subs = []
    for found in candidates.values():
        chosen = next((c for c in found if not c["in_table"]), found[0])
        subs.append({"no": chosen["no"], "sub": chosen["sub"], "text": chosen["text"], "k": chosen["k"]})
    subs.sort(key=lambda s: s["k"])

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
