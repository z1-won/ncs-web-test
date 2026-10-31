"""목록 비교 도우미. 규칙 모듈이 함께 쓴다. 비교 정책은 v1.1을 유지한다."""

from collections.abc import Sequence

from ncs_core import NA, O, TRI, X, visible

from .text import norm


def list_check(name: str, expected: Sequence[str], actual: Sequence[str]) -> tuple[str, str, list[str]]:
    """목록 비교 → (내용 체크값, 순서 체크값, 비고).

    내용 = 누락/추가/변경, 순서 = 공통 원소의 순서. 같은 자리의 바뀜은 누락+추가가 아니라 '다름'.
    """
    if not expected:
        return TRI, NA, [f"{name}: 개발계획서에서 목록을 읽지 못함 — 개발계획서 표 구조 확인(검사 불가)"]
    if not actual:
        return X, NA, [f"{name}: 원고 위치 표에 목록이 비어 있음 (개발계획서 {len(expected)}개)"]
    exp, act = [norm(x) for x in expected], [norm(x) for x in actual]
    notes: list[str] = []
    missing = [expected[i] for i, e in enumerate(exp) if e not in act]
    extra = [actual[j] for j, a in enumerate(act) if a not in exp]
    if len(exp) == len(act) and len(missing) == len(extra):
        pairs = [
            (i, expected[i], actual[i])
            for i in range(len(exp))
            if exp[i] != act[i] and exp[i] not in act and act[i] not in exp
        ]
        for i, e, a in pairs:
            notes.append(f'{name} {i + 1}번째 다름: 원고 "{visible(a)}" / 개발계획서 "{e}"')
            missing.remove(e)
            extra.remove(a)
    notes += [f'{name} 누락: "{x}"' for x in missing]
    notes += [f'{name} 원고에 추가: "{visible(x)}"' for x in extra]
    if len(expected) != len(actual):
        notes.insert(0, f"{name} 개수: 원고 {len(actual)} / 개발계획서 {len(expected)}")
    content = O if not notes else X
    common_exp, common_act = [e for e in exp if e in act], [a for a in act if a in exp]
    order = O
    if common_exp != common_act:
        order = TRI
        notes.append(f"{name} 순서 다름: 원고 {[visible(x) for x in actual]} / 개발계획서 {list(expected)}")
    return content, order, notes
