"""학습 목표 문장 목록 비교 — 동일 여부만 본다(O/X).
필요 지식 ⑤(본문)와 평가 ②(평가 준거)가 함께 사용

띄어쓰기·대소문자·부호 차이도 모두 다름이고, 문장 순서만 다른 것은 같은 것으로 봄 (집합 비교)
글머리·계획서 번호 같은 표식만 비교 전에 걷어냄
"""

import difflib
import re
import unicodedata

from .text import PUA

MARKER = re.compile(r"^\s*(\d+\.\d+|[•·▪ㆍ‧◦○\-])\s*")  # 계획서 '1.1 ' / 원고 글머리 '•'
SPACES = re.compile(r"[\s 　]+")                 # 줄바꿈·고정 공백·전각 공백 → 보통 공백 하나


def normalize(text: str) -> str:
    """내용이 아닌 표식만 걷어낸다. 띄어쓰기·대소문자·부호·마침표는 그대로 남겨 비교 대상이 된다."""
    text = unicodedata.normalize("NFC", text or "")
    text = MARKER.sub("", text, count=1)
    text = PUA.sub("·", text)
    return SPACES.sub(" ", text).strip()


PUNCT_ONLY = re.compile(r"[\s·ㆍ‧∙•\-–—/,.()\[\]〈〉<>]")


def difference(expected: str, actual: str, where: str = "본문", basis: str = "계획서", names: bool = True) -> str:
    """두 문장에서 다른 어절만 뽑는다. 검수자가 어디를 고칠지 바로 보게 하는 용도. 항상 한 줄.

    글자 단위가 아니라 어절(띄어쓰기) 단위로 비교해 '본문 「안내문을 작성할」, 계획서 「안내할」'처럼 읽히게 한다.
    names=False면 문서 이름 없이 '「안내문을 작성할」→「안내할」' — 감싸는 문장(explain_pair)이 이름을 이미 적었을 때.
    긴 문장(학습 목표·평가 준거)은 전체를 다시 적지 않고 이 결과만 쓴다. 띄어쓰기만 다르면 그렇다고 적는다.
    """
    e_words, a_words = expected.split(" "), actual.split(" ")
    matcher = difflib.SequenceMatcher(None, e_words, a_words, autojunk=False)
    parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        a, e = " ".join(a_words[j1:j2]) or "∅", " ".join(e_words[i1:i2]) or "∅"
        parts.append(f"{where} 「{a}」, {basis} 「{e}」" if names else f"「{a}」→「{e}」")
    text = ("; " if names else ", ").join(parts[:3]) + (f" 외 {len(parts) - 3}곳" if len(parts) > 3 else "")
    if parts and re.sub(r"\s", "", expected) == re.sub(r"\s", "", actual):
        text += " (띄어쓰기만 다름)"
    return text


def explain_pair(expected: str, actual: str, where: str = "원고", basis: str = "개발계획서") -> str:
    """같은 자리의 두 이름을 문서 이름을 붙여 나란히: '{where} 「…」, {basis} 「…」 (띄어쓰기만 다름)'.

    "A→B"만 적으면 어느 쪽이 어느 문서인지, 띄어쓰기 하나 차이가 어디인지 보이지 않는다. 글자가 다르면 다른 어절만 한 번 더 뽑는다.
    항상 한 줄이다 — 이 문장은 목록 비고 안에 번호 붙여 끼워지거나 다른 문장 뒤에 이어지므로, 줄바꿈은 확인서 쪽(sheet.summarize_remarks)이 넣는다.
    """
    if re.sub(r"\s", "", expected) == re.sub(r"\s", "", actual):
        why = "띄어쓰기만 다름"
    elif PUNCT_ONLY.sub("", expected) == PUNCT_ONLY.sub("", actual):
        why = "기호, 띄어쓰기만 다름"
    elif not (set(expected.split()) & set(actual.split())):
        why = "글자가 다름"  # 공통 어절이 없으면 전체가 다른 것 — 다시 뽑아 봐야 같은 문구
    else:
        why = "다른 곳: " + difference(expected, actual, where, basis, names=False)
    return f"{where} 「{actual}」, {basis} 「{expected}」 ({why})"


MARK, WORDING, OTHER, COUNT, MISSING, EXTRA = "표기", "변경", "다른 문장", "개수", "누락", "추가"
WORDING_RATIO = 0.7      # 이만큼 닮았으면 같은 문장의 낱말이 바뀐 것으로 본다(그 아래는 딴 문장). 판정은 규칙이 정한다


def _marks_only(expected: str, actual: str) -> bool:
    """띄어쓰기·부호·영문 대소문자만 다른가."""
    return PUNCT_ONLY.sub("", expected).casefold() == PUNCT_ONLY.sub("", actual).casefold()


def compare_kinds(expected: list[str], actual: list[str], where: str = "본문", basis: str = "계획서") -> list[tuple[str, str]]:
    """정규화된 두 문장 목록을 비교해 (종류, 설명) 목록을 돌려준다. 빈 목록이면 일치(순서 차이는 문제로 보지 않는다).

    종류: '개수' / '표기'(짝은 있는데 띄어쓰기·부호·대소문자만 다름) / '변경'(짝은 있는데 낱말이 다름 — 유사도 WORDING_RATIO 이상) /
          '다른 문장'(가장 비슷한 문장과도 많이 다름) / '누락'(기준에만 있음) / '추가'(원고에만 있음).
    여기서는 가르기만 한다 — 무엇을 부적합으로 볼지는 규칙이 정한다(필요 지식 ⑤, 평가 ②).
    설명은 '2번째 본문 「다른 어절」, 계획서 「다른 어절」', '2번째 누락: 계획서에는 「…」가 있는데 본문에 없음', '본문에만 있음 「…」 (계획서에 없음)',
    '개수: 본문 1개, 계획서 2개' 꼴이다. 한 항목 = 한 줄. where/basis로 문서 이름을 바꾼다(평가 ②는 '평가 준거').
    """
    problems = []
    if len(expected) != len(actual):
        problems.append((COUNT, f"개수: {where} {len(actual)}개, {basis} {len(expected)}개"))
    remaining = list(actual)
    unmatched = []
    for i, e in enumerate(expected):
        if e in remaining:
            remaining.remove(e)
        else:
            unmatched.append((i, e))
    for i, e in unmatched:
        # 가장 비슷한 본문 문장을 짝지어 어디가 다른지 보여준다
        best = max(((difflib.SequenceMatcher(None, e, a, autojunk=False).ratio(), j) for j, a in enumerate(remaining)), default=(0, None))
        if best[1] is not None and best[0] >= 0.5:
            a = remaining.pop(best[1])
            kind = MARK if _marks_only(e, a) else WORDING if best[0] >= WORDING_RATIO else OTHER
            problems.append((kind, f"{i + 1}번째 {difference(e, a, where, basis)}"))
        else:
            problems.append((MISSING, f"{i + 1}번째 누락: {basis}에는 「{e}」가 있는데 {where}에 없음"))
    for a in remaining:
        problems.append((EXTRA, f"{where}에만 있음 「{a}」 ({basis}에 없음)"))
    return problems


def compare_lists(expected: list[str], actual: list[str], where: str = "본문", basis: str = "계획서") -> list[str]:
    """compare_kinds의 설명만 — 종류를 가리지 않는 호출처용."""
    return [text for _, text in compare_kinds(expected, actual, where, basis)]


def compare_to_pool(actual: list[str], pool: list[str], where: str = "본문", basis: str = "NCS 기준정보") -> list[tuple[str, str]]:
    """정규화된 문장들이 문장 묶음(pool — 능력단위의 수행준거 전부) 안에 있는가. 어느 학습 내용에 어느 문장이 가는지는 모를 때 쓴다.
    → (종류, 설명): '표기'(띄어쓰기·부호·대소문자만 다른 문장이 있음) / '변경'(닮은 문장이 있음) / '추가'(묶음에 없는 문장). 빈 목록이면 모두 있다."""
    problems = []
    for i, a in enumerate(actual):
        if a in pool:
            continue
        best = max(((difflib.SequenceMatcher(None, e, a, autojunk=False).ratio(), e) for e in pool), default=(0, ""))
        if best[1] and _marks_only(best[1], a):
            problems.append((MARK, f"{i + 1}번째 {difference(best[1], a, where, basis)}"))
        elif best[0] >= WORDING_RATIO:
            problems.append((WORDING, f"{i + 1}번째 {difference(best[1], a, where, basis)}"))
        else:
            problems.append((EXTRA, f"{i + 1}번째 {where} 「{a}」 — {basis}의 수행준거에 없는 문장"))
    return problems


CHANGE_NOTE = "변경 확인: 용어·법령 사유의 허용 변경인지 확인(F04 준용 집필 기준 2-1·2-2)"


def describe_kinds(problems: list[tuple[str, str]]) -> tuple[bool, str]:
    """(낱말만 바뀐 문장뿐인가, 비고 문장). 낱말이 바뀐 문장에는 '변경 확인' 표시를 단다 — 섞여 있으면 문장마다, 그것뿐이면 끝에 한 번."""
    only_wording = bool(problems) and all(kind == WORDING for kind, _ in problems)
    if only_wording:
        return True, " · ".join(text for _, text in problems) + f" — {CHANGE_NOTE}"
    return False, " · ".join(text + (" (변경 확인 후보)" if kind == WORDING else "") for kind, text in problems)


