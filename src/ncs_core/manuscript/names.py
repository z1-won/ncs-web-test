"""학습명·학습 내용명 비교 도우미. 차례·필요 지식 검수가 같은 규칙으로 명칭을 맞춘다.

머리 번호 '학습 1. ' / '1. ' / '1-1. '을 지우고 비교한다. 개요 검수는 자체 규칙(ncs_overview.text)을 쓴다.
"""

import difflib
from collections.abc import Iterable, Sequence

from ..goals import explain_pair
from ..text import O, PUA, X, make_normalizer, visible

HEAD_NUMBER = r"^(학습\s*)?\d+(-\d+)?\.\s*"
norm, same = make_normalizer(HEAD_NUMBER)


def diff_list(label: str, expected: Sequence[str], actual: Sequence[str], where: str = "이 자리", basis: str = "기준") -> tuple[str, list[str]]:
    """difflib로 누락/추가/변경/순서를 구분한다 → (체크값, 비고 목록).

    중간에 하나가 빠져도 뒤가 연쇄로 '다름'이 되지 않는다.
    where/basis: 비고에 적는 두 문서(자리)의 이름 — 예: where='내용체계 표', basis='개발계획서'. 부적합 비고는 항상
    어느 문서에 어떤 문구가 있는지 양쪽을 다 적는다.
    """
    exp, act = [norm(x) for x in expected], [norm(x) for x in actual]
    notes: list[str] = []
    if len(expected) != len(actual):
        notes.append(f"{label} 개수: {where} {len(actual)} / {basis} {len(expected)}")
    if exp != act and sorted(exp) == sorted(act):
        notes.append(f"{label} 순서 다름: {where} {[visible(x) for x in actual]} / {basis} {list(expected)}")
        return X, notes
    matcher = difflib.SequenceMatcher(None, exp, act, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                notes.append(f"{label} {i1 + k + 1}번째 다름: " + explain_pair(expected[i1 + k], visible(actual[j1 + k]), where, basis))
        else:
            for k in range(i1, i2):
                notes.append(f"{label} {k + 1}번째 누락: {basis}에는 「{expected[k]}」가 있는데 {where}에 없음")
            for k in range(j1, j2):
                notes.append(f"{label} {where} {k + 1}번째가 {basis}에 없음: 「{visible(actual[k])}」")
    return (O if not notes else X), notes


def pua_note(texts: Iterable[str], already: Iterable[str] = ()) -> tuple[str, list[str]]:
    """already: 차례(①)에서 이미 보고된 문자열(PUA→· 치환형). 같은 원인이면 X 대신 비고만."""
    already = set(already)
    bad = [t for t in texts if PUA.search(t)]
    new = [t for t in bad if PUA.sub("·", t) not in already]
    notes = [f"기호 글꼴 문자: {visible(t)}" for t in new]
    if bad and not new:
        notes.append("기호 글꼴 문자가 있으나 차례와 같은 원인 (①에서 보고됨)")
    return (X if new else O), notes
