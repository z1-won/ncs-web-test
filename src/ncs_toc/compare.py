"""목록 비교 도우미. 규칙 모듈이 함께 쓴다. 비교 정책은 v1.1을 유지한다."""

import difflib
from collections.abc import Iterable, Sequence

from ncs_core import O, PUA, X, visible

from .text import norm


def diff_list(label: str, expected: Sequence[str], actual: Sequence[str]) -> tuple[str, list[str]]:
    """difflib로 누락/추가/변경/순서를 구분한다 → (체크값, 비고 목록).

    중간에 하나가 빠져도 뒤가 연쇄로 '다름'이 되지 않는다.
    """
    exp, act = [norm(x) for x in expected], [norm(x) for x in actual]
    notes: list[str] = []
    if len(expected) != len(actual):
        notes.append(f"{label} 개수: 이 자리 {len(actual)} / 기준 {len(expected)}")
    if exp != act and sorted(exp) == sorted(act):
        notes.append(f"{label} 순서 다름: 이 자리 {[visible(x) for x in actual]} / 기준 {list(expected)}")
        return X, notes
    matcher = difflib.SequenceMatcher(None, exp, act, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                notes.append(
                    f'{label} {i1 + k + 1}번째 다름: "{visible(actual[j1 + k])}" / 기준 "{expected[i1 + k]}"'
                )
        else:
            for k in range(i1, i2):
                notes.append(f'{label} {k + 1}번째 누락: "{expected[k]}"')
            for k in range(j1, j2):
                notes.append(f'{label} 이 자리 {k + 1}번째가 기준에 없음: "{visible(actual[k])}"')
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
