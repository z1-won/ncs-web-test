"""F02 개요 ①: '학습모듈의 목표' — NCS 능력단위 정의에서 주어를 삭제한 후 '~할 수 있다.'로 종결하였는가.

형식 항목이다. 계획서 문장과 글자가 같은지를 묻지 않으므로
  - 종결어와 주어 삭제는 O/X로 판정하고,
  - 정의와의 관계는 내용이 대응하는지(공백·구두점을 뺀 유사도)만 보아 낮으면 △(사람 확인)로 둔다.
계획서의 '학습모듈의 목표' 줄은 판정에 쓰지 않고 참고로만 적는다.
"""

import difflib
import re

from ncs_core import NA, O, PASS, TRI, X, verdict

from ..patterns import DEFINITION_END, DEFINITION_SUBJECT, GOAL_END

ITEM_ID = "F02-개요-①"
SIMILARITY_MIN = 0.85  # 정의(주어 제거·서술어 변경 후)와 목표의 글자 유사도 하한. 이보다 낮으면 △
SUBJECT_HEAD = re.compile(r"^\S+(이란|란)\s")  # '객실 예약 접수란 ' 꼴 주어가 목표 머리에 남아 있음


def goal_from_definition(definition: str) -> tuple[str, str]:
    """'객실 예약 접수란 … 처리하는 능력이다.' → (주어 '객실 예약 접수란', '… 처리할 수 있다.')"""
    definition = definition.strip()
    m = DEFINITION_SUBJECT.match(definition)
    subject = m.group(0).strip() if m else ""
    body = definition[m.end():] if m else definition
    return subject, DEFINITION_END.sub("할 수 있다.", body).strip()


def _compact(text: str) -> str:
    """공백·구두점·기호 글꼴 가운뎃점을 뺀 글자열 (내용 대응 비교용)."""
    return re.sub(r"[\s·,.\-]", "", text)


def check_goal(overview: dict, plan: dict | None) -> list[dict]:
    goal = overview.get("목표")
    label_end = "① '~할 수 있다.' 종결"
    label_subject = "① 주어 삭제"
    label_def = "① 능력단위 정의 내용과 대응"
    notes: dict[str, str] = {}
    if not goal:
        checks = {label_end: X, label_subject: NA, label_def: NA}
        notes[label_end] = "'학습모듈의 목표' 제목 또는 내용을 찾지 못함"
        return [_row(None, None, checks, notes, "학습모듈의 목표를 작성할 것")]

    text = goal["text"].strip()
    definition = plan.get("정의") if plan else None
    subject, derived = goal_from_definition(definition) if definition else ("", "")

    checks = {label_end: O if GOAL_END.search(text) else X}
    if checks[label_end] == X:
        notes[label_end] = "'~할 수 있다.'로 종결되지 않음"

    # 주어 삭제: 정의의 주어가 목표 머리에 남아 있거나, '…란/이란' 꼴로 시작하면 X
    head = _compact(text)
    if subject and head.startswith(_compact(subject)):
        checks[label_subject] = X
        notes[label_subject] = f'정의의 주어 "{subject}" 가 남아 있음'
    elif SUBJECT_HEAD.match(text):
        checks[label_subject] = X
        notes[label_subject] = f'주어로 보이는 머리 "{SUBJECT_HEAD.match(text).group(0).strip()}" 가 남아 있음'
    else:
        checks[label_subject] = O

    # 정의와의 관계: 글자 일치가 아니라 내용 대응. 낮으면 △
    if definition:
        ratio = difflib.SequenceMatcher(None, _compact(derived), head, autojunk=False).ratio()
        if ratio >= SIMILARITY_MIN:
            checks[label_def] = O
            if _compact(derived) != head:
                notes[label_def] = f'정의와 표현이 조금 다름(유사도 {ratio:.2f}) — 정의 기준 문장: "{derived}"'
        else:
            checks[label_def] = TRI
            notes[label_def] = f'정의와 내용이 다름(유사도 {ratio:.2f}) — 사람 확인. 정의 기준 문장: "{derived}"'
    else:
        checks[label_def] = NA
        notes[label_def] = "개발계획서를 읽지 못해 대조 생략" if not plan else "개발계획서에 능력단위 정의가 없어 대조 생략"

    reference = {"능력단위 정의": definition, "개발계획서 목표(참고)": plan.get("목표")} if plan else None
    result = verdict(checks)
    if result == PASS:
        suggestion = None
    elif checks[label_end] == X or checks[label_subject] == X:
        parts = []
        if checks[label_subject] == X:
            parts.append("주어를 지우고")
        if checks[label_end] == X:
            parts.append("'~할 수 있다.'로 끝맺을 것")
        suggestion = "능력단위 정의에서 " + " ".join(parts)
    else:
        suggestion = "능력단위 정의의 내용과 대응하는지 확인"
    return [_row({"목표": text, "p": goal["p"]}, reference, checks, notes, suggestion)]


def _row(evidence, reference, checks, notes, suggestion) -> dict:
    return {
        "item_id": ITEM_ID,
        "region_path": "section0 > 학습모듈의 개요 > 학습모듈의 목표",
        "원고": evidence,
        "개발계획서": reference,
        "체크": checks,
        "판정": verdict(checks),
        "비고": notes,
        "수정 제안": suggestion,
    }
