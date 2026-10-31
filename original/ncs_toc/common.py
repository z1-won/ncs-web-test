"""문자 정규화와 비교. 원본 v1.1의 비교 정책을 유지한다."""
import re

PUA = re.compile(r"[-]")
O, X, TRI, NA = "O", "X", "△", "-"

def norm(s):
    s = PUA.sub('·', s or '').strip()
    s = re.sub(r'^(학습\s*)?\d+(-\d+)?\.\s*', '', s)      # '학습 1. ' / '1. ' / '1-1. ' 제거
    return re.sub(r'\s+', ' ', s)


def same(a, b): return norm(a) == norm(b)


def visible(s): return PUA.sub(lambda m: f'⟨U+{ord(m.group()):04X}⟩', s or '')


def _verdict(checks):
    vals = [v for v in checks.values() if v != NA]
    if X in vals: return '미반영'
    if TRI in vals: return '판단불가'
    return '반영'


def _diff_list(label, exp, act):
    """difflib 로 누락/추가/변경/순서를 구분 (중간에 하나 빠져도 뒤가 연쇄로 '다름' 이 되지 않음) → (체크값, 비고 목록)"""
    import difflib
    E, A = [norm(x) for x in exp], [norm(x) for x in act]
    notes = []
    if len(exp) != len(act): notes.append(f'{label} 개수: 이 자리 {len(act)} / 기준 {len(exp)}')
    if E != A and sorted(E) == sorted(A):
        notes.append(f'{label} 순서 다름: 이 자리 {[visible(x) for x in act]} / 기준 {exp}')
        return X, notes
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, E, A, autojunk=False).get_opcodes():
        if op == 'equal': continue
        if op == 'replace' and i2 - i1 == j2 - j1:
            for k in range(i2 - i1): notes.append(f'{label} {i1+k+1}번째 다름: "{visible(act[j1+k])}" / 기준 "{exp[i1+k]}"')
        else:
            for k in range(i1, i2): notes.append(f'{label} {k+1}번째 누락: "{exp[k]}"')
            for k in range(j1, j2): notes.append(f'{label} 이 자리 {k+1}번째가 기준에 없음: "{visible(act[k])}"')
    return (O if not notes else X), notes


def _pua_note(texts, already=()):
    """already: 차례(①)에서 이미 보고된 문자열(PUA→· 치환형). 같은 원인이면 X 대신 비고만"""
    bad = [t for t in texts if PUA.search(t)]
    new = [t for t in bad if PUA.sub('·', t) not in already]
    notes = [f'기호 글꼴 문자: {visible(t)}' for t in new]
    if bad and not new: notes.append('기호 글꼴 문자가 있으나 차례와 같은 원인 (①에서 보고됨)')
    return (X if new else O), notes

