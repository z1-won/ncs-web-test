"""목록 비교 도우미. ncs_toc.compare.diff_list와 같은 정책(difflib, 누락/추가/변경/순서 구분)을 개요 정규화 규칙으로 쓴다."""

import difflib
from collections.abc import Sequence

from ncs_core import O, X, visible

from .text import norm


def diff_list(label: str, expected: Sequence[str], actual: Sequence[str]) -> tuple[str, list[str]]:
    exp, act = [norm(x) for x in expected], [norm(x) for x in actual]
    notes: list[str] = []
    if len(expected) != len(actual):
        notes.append(f"{label} 개수: 원고 {len(actual)} / 개발계획서 {len(expected)}")
    if exp != act and sorted(exp) == sorted(act):
        notes.append(f"{label} 순서 다름: 원고 {[visible(x) for x in actual]} / 개발계획서 {list(expected)}")
        return X, notes
    matcher = difflib.SequenceMatcher(None, exp, act, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                notes.append(f'{label} {i1 + k + 1}번째 다름: "{visible(actual[j1 + k])}" / 개발계획서 "{expected[i1 + k]}"')
        else:
            for k in range(i1, i2):
                notes.append(f'{label} {k + 1}번째 누락: "{expected[k]}"')
            for k in range(j1, j2):
                notes.append(f'{label} 원고 {k + 1}번째가 개발계획서에 없음: "{visible(actual[k])}"')
    return (O if not notes else X), notes
