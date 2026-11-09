"""모듈 표 규칙 — ③ 학습모듈의 목표, ④ 학습명·요소 배정, ⑤ 요소 코드, ⑥ 학습 목표 = 수행준거, ⑦ 학습 내용명.

판정 기준(F04 NCS 준용 집필 기본 지침 2026.8.7, 양식 작성 안내):
- 학습명은 요소명 준용 '~하기'. 기호·띄어쓰기 차이는 같은 것으로 보고, 글자가 다르면 △(윤문 범위인지 직능연 협의 여부 확인).
- 학습 목표는 수행준거 문장 그대로. 누락·추가는 X. 띄어쓰기만 다른 것은 O(허용), 글자가 다르면 △(명백한 오타 정정인지 확인).
- 요소 통합은 같은 능력단위 안에서만. 요소가 어느 학습에도 없으면 X, 학습에 요소가 없으면 X.
"""

import difflib

from ncs_core import NA, O, TRI, X, visible
from ncs_core.goals import normalize
from ncs_core.lexicon import ActionNounLexicon

from ..patterns import DEFINITION_END, DEFINITION_SUBJECT, GOAL_END, LESSON_END, SEPARATOR, TRAILING_NOTE
from .common import compact, pair, row, same_loose, same_text, similarity

SIMILARITY_MIN = 0.85        # ③ 정의↔목표
NAME_SIMILARITY_MIN = 0.6    # ④ 요소명↔학습명: 이 이상이면 윤문(△), 미만이면 다른 이름(X)


def _region(module: dict, tail: str = "") -> str:
    base = f"개발계획서 > 모듈 표 {module['코드'] or '(코드 없음)'}"
    return f"{base} > {tail}" if tail else base


def _unreadable(no: str, name: str, module: dict) -> dict:
    label = f"{no} {name}"
    return row(no, _region(module), module["코드"], None, {label: TRI}, {label: "모듈 표의 머리 행(코드번호/수행준거/학습명/학습내용명/학습 목표)을 읽지 못함"})


# ── ③ 학습모듈의 목표 ────────────────────────────────────────────────────────────

def goal_from_definition(definition: str) -> tuple[str, str]:
    definition = definition.strip()
    m = DEFINITION_SUBJECT.match(definition)
    subject = m.group(0).strip() if m else ""
    body = definition[m.end():] if m else definition
    return subject, DEFINITION_END.sub("할 수 있다.", body).strip()


def check_goal(module: dict) -> list[dict]:
    label_end, label_subject, label_def = "③ '~할 수 있다.' 종결", "③ 주어 삭제", "③ 능력단위 정의와 대응"
    goal, definition = module["목표"], module["정의"]
    checks, notes = {}, {}
    if not goal:
        checks = {label_end: X, label_subject: NA, label_def: NA}
        notes[label_end] = "'학습모듈의 목표' 칸이 비어 있음"
        return [row("③", _region(module), module["코드"], None, checks, notes, "능력단위 정의에서 주어를 빼고 '~할 수 있다.'로 바꿔 적을 것")]
    checks[label_end] = O if GOAL_END.search(goal) else X
    if checks[label_end] == X:
        notes[label_end] = f"「{goal[-20:]}」 — '~할 수 있다.'로 끝나지 않음"
    subject, derived = goal_from_definition(definition) if definition else ("", "")
    if subject and compact(goal).startswith(compact(subject)):
        checks[label_subject] = X
        notes[label_subject] = f"정의의 주어 「{subject}」가 남아 있음"
    else:
        checks[label_subject] = O
    if not definition:
        checks[label_def] = TRI
        notes[label_def] = "'능력단위 정의' 칸이 비어 있어 대조하지 못함"
    else:
        ratio = difflib.SequenceMatcher(None, compact(derived), compact(goal), autojunk=False).ratio()
        if same_loose(derived, goal):
            checks[label_def] = O
        elif ratio >= SIMILARITY_MIN:
            checks[label_def] = O
            notes[label_def] = f"정의와 표현이 조금 다름(유사도 {ratio:.2f}) — 정의 기준 문장 「{derived}」"
        else:
            checks[label_def] = TRI
            notes[label_def] = f"정의와 내용이 다름(유사도 {ratio:.2f}) — 정의 기준 문장 「{derived}」"
    suggestion = f"정의 기준 문장: {derived}" if derived and X in checks.values() else None
    return [row("③", _region(module), module["코드"], visible(goal), checks, notes, suggestion)]


# ── ④ 학습명·요소 배정 ───────────────────────────────────────────────────────────

def check_lessons(module: dict) -> list[dict]:
    label_end, label_name, label_assign = "④ '~하기' 종결", "④ 요소명 준용", "④ 요소 배정"
    if module["머리행"] is None:
        return [_unreadable("④", "학습명", module)]
    elements = {e["코드"]: e for e in module["요소"]}
    rows, assigned = [], set()
    for lesson in module["학습"]:
        checks, notes = {}, {}
        name = lesson["명칭"]
        checks[label_end] = O if LESSON_END.search(TRAILING_NOTE.sub("", name).strip()) else X
        if checks[label_end] == X:
            notes[label_end] = f"「{name}」 — '~하기'로 끝나지 않음" if name else "학습명이 비어 있음"
        own = [elements[c] for c in lesson["요소"] if c in elements]
        assigned.update(lesson["요소"])
        if not own:
            checks[label_assign] = X
            notes[label_assign] = "이 학습에 배정된 능력단위요소가 없음(NCS에 없는 학습은 추가할 수 없음)"
            checks[label_name] = NA
        else:
            foreign = [e["코드"] for e in own if e["능력단위"] != module["코드"]]
            checks[label_assign] = X if foreign else O
            if foreign:
                notes[label_assign] = "다른 능력단위의 요소가 섞여 있음: " + ", ".join(foreign)
            if len(own) == 1:
                element_name = own[0]["명칭"]
                if same_loose(element_name, name):
                    checks[label_name] = O
                elif not name:
                    checks[label_name] = X
                    notes[label_name] = f"학습명이 비어 있음 — 능력단위요소명 「{element_name}」 준용"
                elif similarity(element_name, name) >= NAME_SIMILARITY_MIN:
                    checks[label_name] = TRI   # 용어·표기 윤문(F04 2-1·2-4 허용 범위) — 협의 여부는 사람이 확인
                    notes[label_name] = pair(element_name, name, "학습명", "능력단위요소명") + " — 윤문 범위인지, 직능연과 협의했는지 확인"
                else:
                    checks[label_name] = X
                    notes[label_name] = pair(element_name, name, "학습명", "능력단위요소명")
            else:
                checks[label_name] = TRI
                notes[label_name] = f"요소 {len(own)}개를 통합한 학습 — 학습명이 요소명(" + " / ".join(e["명칭"] for e in own) + ")을 아우르는지 확인"
        rows.append(row("④", _region(module, f"학습 {lesson['번호']}"), f"학습 {lesson['번호']}", visible(name), checks, notes,
                        "학습명은 능력단위요소명을 준용해 '~하기'로 적고 요소를 하나 이상 배정할 것" if X in checks.values() else None,
                        요소=[e["명칭"] for e in own]))
    unassigned = [e for e in module["요소"] if e["코드"] not in assigned]
    if unassigned:
        rows.append(row("④", _region(module), module["코드"], None, {label_assign: X},
                        {label_assign: "어느 학습에도 배정되지 않은 능력단위요소: " + ", ".join(f"{e['코드']} {e['명칭']}" for e in unassigned)},
                        "모든 능력단위요소를 학습에 배정할 것"))
    if not rows:
        rows.append(row("④", _region(module), module["코드"], None, {label_assign: X}, {label_assign: "학습(N. 학습명) 행을 읽지 못함"}, "학습명을 기재할 것"))
    return rows


# ── ⑤ 요소 코드 ─────────────────────────────────────────────────────────────────

def check_element_codes(module: dict) -> list[dict]:
    label = "⑤ 요소 코드 연번"
    if module["머리행"] is None:
        return [_unreadable("⑤", "요소 코드", module)]
    problems = []
    for i, element in enumerate(module["요소"], 1):
        if module["코드"] and element["능력단위"] != module["코드"]:
            problems.append(f"「{element['코드']}」 — 능력단위 코드 「{module['코드']}」와 다름")
        if element["번호"] != i:
            problems.append(f"「{element['코드']}」 — {i}번째인데 번호가 {element['번호']}")
    if not module["요소"]:
        problems.append("능력단위요소 행(코드.N 요소명)을 읽지 못함")
    checks = {label: X if problems else O}
    return [row("⑤", _region(module), module["코드"], f"요소 {len(module['요소'])}개", checks, {label: "\n".join(problems)},
                "요소 코드를 '능력단위 코드.1, .2 …' 연번으로 적을 것" if problems else None)]


# ── ⑥ 학습 목표 = 수행준거 ────────────────────────────────────────────────────────

def _match(sentence: str, pool: list[str]) -> tuple[str | None, str]:
    """pool에서 sentence와 같은 문장을 찾는다 → (짝, 'same'|'space'|'punct'|'near'|'none')."""
    target = normalize(sentence)
    for p in pool:
        if normalize(p) == target:
            return p, "same"
    for p in pool:
        if compact(normalize(p)) == compact(target):
            return p, "space"
    for p in pool:
        if same_loose(p, sentence):
            return p, "punct"
    best, score = None, 0.0
    for p in pool:
        ratio = difflib.SequenceMatcher(None, compact(normalize(p)), compact(target), autojunk=False).ratio()
        if ratio > score:
            best, score = p, ratio
    return (best, "near") if best is not None and score >= 0.8 else (None, "none")


def check_targets(module: dict) -> list[dict]:
    label_cover, label_extra, label_text = "⑥ 수행준거 누락 없음", "⑥ 수행준거 외 문장 없음", "⑥ 문장 수정 없음"
    if module["머리행"] is None:
        return [_unreadable("⑥", "학습 목표", module)]
    rows = []
    for lesson in module["학습"]:
        criteria = [c for code in lesson["요소"] for e in module["요소"] if e["코드"] == code for c in e["수행준거"]]
        goals = [g for sub in lesson["내용"] for g in sub["목표"]]
        checks, notes = {}, {}
        if not criteria:
            checks = {label_cover: NA, label_extra: NA, label_text: NA}
            notes[label_cover] = "배정된 요소가 없거나 수행준거가 비어 있어 대조 생략(④ 참조)"
            rows.append(row("⑥", _region(module, f"학습 {lesson['번호']}"), f"학습 {lesson['번호']}", None, checks, notes))
            continue
        remaining = list(goals)
        missing, changed = [], []
        for criterion in criteria:
            match, how = _match(criterion, remaining)
            if match is None:
                missing.append(normalize(criterion))
                continue
            remaining.remove(match)
            if how == "near":
                changed.append(pair(criterion, match, "학습 목표", "수행준거"))
        checks[label_cover] = X if missing else O
        if missing:
            notes[label_cover] = "학습 목표에 없는 수행준거: " + " / ".join(f"「{m}」" for m in missing[:3]) + (f" 외 {len(missing) - 3}건" if len(missing) > 3 else "")
        checks[label_extra] = X if remaining else O
        if remaining:
            notes[label_extra] = "수행준거에 없는 학습 목표: " + " / ".join(f"「{normalize(g)}」" for g in remaining[:3]) + (f" 외 {len(remaining) - 3}건" if len(remaining) > 3 else "")
        checks[label_text] = TRI if changed else O
        if changed:
            notes[label_text] = "\n".join(changed) + "\n— 명백한 오타·띄어쓰기 정정인지, 직능연과 협의한 변경인지 확인"
        rows.append(row("⑥", _region(module, f"학습 {lesson['번호']}"), f"학습 {lesson['번호']}", f"수행준거 {len(criteria)}개 / 학습 목표 {len(goals)}개", checks, notes,
                        "수행준거 문장을 빠짐없이, 고치지 않고 학습 목표에 나누어 담을 것" if X in checks.values() else None))
    if not rows:
        rows.append(row("⑥", _region(module), module["코드"], None, {label_cover: TRI}, {label_cover: "학습 행을 읽지 못해 대조할 수 없음"}))
    return rows


# ── ⑦ 학습 내용명 ───────────────────────────────────────────────────────────────

def head_word(name: str) -> str:
    text = TRAILING_NOTE.sub("", name).strip().rstrip(".。,")
    pieces = [p for p in SEPARATOR.split(text) if p]
    return pieces[-1] if pieces else text


def check_subs(module: dict, lexicon: ActionNounLexicon) -> list[dict]:
    label_seq, label_noun = "⑦ N-M 연번·기재", "⑦ 행동명사 종결"
    if module["머리행"] is None:
        return [_unreadable("⑦", "학습 내용명", module)]
    rows = []
    for lesson in module["학습"]:
        subs = lesson["내용"]
        seq_problems = []
        if not subs:
            seq_problems.append("학습 내용(N-M.) 행이 없음")
        for i, sub in enumerate(subs, 1):
            if sub["소번호"] is None:
                seq_problems.append(f"{i}번째 학습 내용의 번호가 'N-M.' 꼴이 아님: 「{sub['명칭'][:40]}」")
                continue
            if sub["소번호"] != i:
                seq_problems.append(f"{i}번째 학습 내용의 번호가 {sub['번호']}-{sub['소번호']}")
            if not sub["명칭"]:
                seq_problems.append(f"{sub['번호']}-{sub['소번호']} 학습 내용명이 비어 있음")
        noun_notes, noun_value = [], O
        for sub in subs:
            if not sub["명칭"] or sub["소번호"] is None:
                continue
            value, note = lexicon.judge(head_word(sub["명칭"]))
            if value == X or (value == TRI and noun_value != X):
                noun_value = value
            if note:
                noun_notes.append(f"{sub['번호']}-{sub['소번호']} 「{sub['명칭']}」: {note}")
        checks = {label_seq: X if seq_problems else O, label_noun: noun_value if subs else NA}
        notes = {label_seq: "\n".join(seq_problems), label_noun: "\n".join(noun_notes)}
        rows.append(row("⑦", _region(module, f"학습 {lesson['번호']}"), f"학습 {lesson['번호']}", " / ".join(f"{s['번호']}-{s['소번호']}. {s['명칭']}" if s["소번호"] is not None else f"(번호 오류) {s['명칭']}" for s in subs) or None,
                        checks, notes, "학습 내용명을 N-M 연번으로 채우고 행동명사로 끝낼 것" if X in checks.values() else None))
    if not rows:
        rows.append(row("⑦", _region(module), module["코드"], None, {label_seq: TRI}, {label_seq: "학습 행을 읽지 못해 판단할 수 없음"}))
    return rows
