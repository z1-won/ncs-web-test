"""개요 검수의 문자 비교 규칙. 머리 번호 '1. ' / '1-1. '만 지우고 그대로 비교한다.

공백 차이도 다른 글자로 본다: "객실·부대시설" ≠ "객실 · 부대시설", "예약현황" ≠ "예약 현황".
기호 글꼴(PUA) 문자는 가운뎃점으로 바꿔 비교하고(ncs_core.make_normalizer), 그 사실은 비고에 적는다.
"""

from ncs_core import make_normalizer

HEAD_NUMBER = r"^\d+(-\d+)?\.\s*"
norm, same = make_normalizer(HEAD_NUMBER)


def split_items(text: str) -> list[str]:
    """쉼표로 나눈 항목 목록. 괄호 안의 쉼표(예: '체크 인(Check In, 투숙)')는 나누지 않는다."""
    items, depth, current = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(depth - 1, 0)
        if ch in ",，、" and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return [item.strip() for item in items if item.strip()]
