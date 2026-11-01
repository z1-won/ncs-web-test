"""F02 필요지식 ⑤: 각 학습 내용의 '학습 목표' = 개발계획서 학습 목표(수행 준거).

판정은 동일 여부만 본다(O/X). 띄어쓰기·대소문자·부호 차이도 모두 X이고, 윤문(△)은 없다.
문장 순서만 다른 것은 같은 것으로 본다(집합 비교). 비교 전에 걷어내는 것은 글머리·계획서 번호 같은 표식만이다.

구조: normalize(문장) → compare_lists(기대 목록, 실제 목록) → check_goals(행 생성). compare_lists는 문자열 목록만 받는
순수 함수라 단위 테스트가 쉽고, 같은 "기대 목록 vs 실제 목록" 비교가 필요한 다른 항목에서도 쓸 수 있다.
"""

import difflib
import re
import unicodedata

from ncs_core import NA, O, PUA, X, visible

from .common import row

MARKER = re.compile(r"^\s*(\d+\.\d+|[•·▪ㆍ‧◦○\-])\s*")  # 계획서 '1.1 ' / 원고 글머리 '•'
SPACES = re.compile(r"[\s 　]+")                 # 줄바꿈·고정 공백·전각 공백 → 보통 공백 하나


def normalize(text: str) -> str:
    """내용이 아닌 표식만 걷어낸다. 띄어쓰기·대소문자·부호·마침표는 그대로 남겨 비교 대상이 된다."""
    text = unicodedata.normalize("NFC", text or "")
    text = MARKER.sub("", text, count=1)
    text = PUA.sub("·", text)
    return SPACES.sub(" ", text).strip()


def difference(expected: str, actual: str) -> str:
    """두 문장에서 다른 어절만 「본문」↔「계획서」 꼴로 뽑는다. 검수자가 어디를 고칠지 바로 보게 하는 용도.

    글자 단위가 아니라 어절(띄어쓰기) 단위로 비교해 '「안내문을 작성할」↔「안내할」'처럼 읽히게 한다.
    """
    e_words, a_words = expected.split(" "), actual.split(" ")
    matcher = difflib.SequenceMatcher(None, e_words, a_words, autojunk=False)
    parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        parts.append(f"「{' '.join(a_words[j1:j2]) or '∅'}」↔「{' '.join(e_words[i1:i2]) or '∅'}」")
    return " ".join(parts[:3]) + (" …" if len(parts) > 3 else "")


def compare_lists(expected: list[str], actual: list[str]) -> list[str]:
    """정규화된 두 문장 목록을 비교해 문제 설명 목록을 돌려준다. 빈 목록이면 일치(순서 차이는 문제로 보지 않는다).

    설명은 '2번째 「본문」↔「계획서」', '2번째 누락 …', '본문에만 있음 …', '개수 본문 1 / 계획서 2' 꼴이다.
    """
    problems = []
    if len(expected) != len(actual):
        problems.append(f"개수 본문 {len(actual)} / 계획서 {len(expected)}")
    remaining = list(actual)
    unmatched = []
    for i, e in enumerate(expected):
        if e in remaining:
            remaining.remove(e)
        else:
            unmatched.append((i, e))
    for i, e in unmatched:
        # 판정은 이미 X. 가장 비슷한 본문 문장을 짝지어 어디가 다른지만 보여준다(유사도는 짝 고르기에만 쓴다).
        best = max(((difflib.SequenceMatcher(None, e, a, autojunk=False).ratio(), j) for j, a in enumerate(remaining)), default=(0, None))
        if best[1] is not None and best[0] >= 0.5:
            a = remaining.pop(best[1])
            problems.append(f"{i + 1}번째 {difference(e, a)}")
        else:
            problems.append(f"{i + 1}번째 누락 「{e}」")
    for a in remaining:
        problems.append(f"본문에만 있음 「{a}」")
    return problems


def check_goals(plan: dict | None, units: list[dict]) -> list[dict]:
    rows = []
    for unit in units:
        key = f"{unit['no']}-{unit['sub']}"
        region = f"section1 > 학습 {unit['lesson']} > {key}. {visible(unit['text'])} > 학습 목표"
        actual = unit["goal"]
        shown = [visible(a) for a in actual]
        if not plan:
            rows.append(row("⑤", region, shown, {"개발계획서 학습 목표 일치": NA}, {"개발계획서": "개발계획서를 읽지 못해 대조 생략"}))
            continue
        checks, notes = {}, {}
        if unit["goal_k"] is None:
            checks["학습 목표 블록"], notes["학습 목표 블록"] = X, f"{key} 제목 아래 '학습 목표' 줄을 찾지 못함"
        expected_unit = plan["내용"].get((unit["no"], unit["sub"]))
        if expected_unit is None:
            checks["개발계획서 학습 목표 일치"] = X
            notes["개발계획서 학습 목표 일치"] = f"{key} 개발계획서에 없음 (계획서 목록: {sorted(plan['내용'])})"
            rows.append(row("⑤", region, shown, checks, notes))
            continue
        expected = expected_unit["goals"]
        problems = compare_lists([normalize(e) for e in expected], [visible(normalize(a)) for a in actual])
        checks["개발계획서 학습 목표 일치"] = X if problems else O
        if problems:
            notes["개발계획서 학습 목표 일치"] = f"{key} " + " · ".join(problems)
        rows.append(row("⑤", region, shown, checks, notes, "개발계획서 학습 목표 문장으로 통일", 개발계획서=expected))
    return rows
