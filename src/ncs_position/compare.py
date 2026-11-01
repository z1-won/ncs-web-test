"""목록 비교 도우미. 규칙 모듈이 함께 쓴다. 비교 정책은 v1.1을 유지한다."""

from collections.abc import Sequence

from ncs_core import NA, O, TRI, X, visible
from ncs_core.goals import explain_pair

from .text import norm

def list_check(name: str, expected: Sequence[str], actual: Sequence[str]) -> tuple[str, str, list[str]]:
    """목록 비교 → (내용 체크값, 순서 체크값, 비고 목록). 자세한 구조는 list_diff."""
    content, order, notes, _ = list_diff(name, expected, actual)
    return content, order, notes


def summarize_diff(name: str, info: dict, show: int = 3) -> str:
    """list_diff의 info → 확인서 비고용 한 줄: '세분류 원고 8 / 개발계획서 18 · 누락 10(SW아키텍처, … 외 7) · 추가 1(…)'."""
    def few(items, sep=", "):
        return sep.join(visible(x) for x in items[:show]) + (f" 외 {len(items) - show}" if len(items) > show else "")
    parts = []
    if info["expected"] != info["actual"]:
        parts.append(f"원고 {info['actual']} / 개발계획서 {info['expected']}")
    if info["changed"]:
        parts.append(f"다름 {len(info['changed'])}: " + few([explain_pair(e, a) for _, e, a in info["changed"]], sep="; "))
    if info["missing"]:
        parts.append(f"누락 {len(info['missing'])}(" + few(info["missing"]) + ")")
    if info["extra"]:
        parts.append(f"원고에만 {len(info['extra'])}(" + few(info["extra"]) + ")")
    if info["order"]:
        parts.append("순서 다름")
    return f"{name} " + " · ".join(parts) if parts else ""


def list_diff(name: str, expected: Sequence[str], actual: Sequence[str]) -> tuple[str, str, list[str], dict]:
    """목록 비교 → (내용 체크값, 순서 체크값, 비고 목록, info).

    내용 = 누락/추가/변경, 순서 = 공통 원소의 순서. 같은 자리의 바뀜은 누락+추가가 아니라 '다름'.
    info = {'expected': 개수, 'actual': 개수, 'missing': [...], 'extra': [...], 'changed': [(i, 기대, 실제)], 'order': bool, 'unreadable': bool}
    """
    info = {"expected": len(expected), "actual": len(actual), "missing": [], "extra": [], "changed": [], "order": False, "unreadable": False}
    if not expected:
        info["unreadable"] = True
        return TRI, NA, [f"{name}: 개발계획서에서 목록을 읽지 못함 — 개발계획서 표 구조 확인(검사 불가)"], info
    if not actual:
        return X, NA, [f"{name}: 원고 위치 표에 목록이 비어 있음 (개발계획서 {len(expected)}개)"], info
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
            notes.append(f"{name} {i + 1}번째 다름: {explain_pair(e, a)}")
            missing.remove(e)
            extra.remove(a)
            info["changed"].append((i, e, a))
    notes += [f"{name} 누락: 개발계획서에는 「{x}」가 있는데 원고에 없음" for x in missing]
    notes += [f"{name} 원고에만 있음: 「{visible(x)}」 (개발계획서에 없음)" for x in extra]
    if len(expected) != len(actual):
        notes.insert(0, f"{name} 개수: 원고 {len(actual)} / 개발계획서 {len(expected)}")
    content = O if not notes else X
    common_exp, common_act = [e for e in exp if e in act], [a for a in act if a in exp]
    order = O
    if common_exp != common_act:
        order = TRI
        info["order"] = True
        notes.append(f"{name} 순서 다름: 원고 {[visible(x) for x in actual]} / 개발계획서 {list(expected)}")
    info["missing"], info["extra"] = missing, extra
    return content, order, notes, info
