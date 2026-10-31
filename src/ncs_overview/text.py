"""개요 검수의 문자 비교 규칙. 머리 번호 '1. ' / '1-1. '만 지우고 그대로 비교한다.

공백 차이도 다른 글자로 본다: "객실·부대시설" ≠ "객실 · 부대시설", "예약현황" ≠ "예약 현황".
기호 글꼴(PUA) 문자는 가운뎃점으로 바꿔 비교하고(ncs_core.make_normalizer), 그 사실은 비고에 적는다.
차례·필요 지식이 쓰는 '학습 N.' 접두 제거 규칙(ncs_core.manuscript.names)과는 의도적으로 다르다.
"""

from ncs_core import make_normalizer

HEAD_NUMBER = r"^\d+(-\d+)?\.\s*"
norm, same = make_normalizer(HEAD_NUMBER)
