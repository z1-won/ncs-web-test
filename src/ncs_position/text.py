"""위치 검수의 문자 비교 규칙. 머리 번호 '1. '만 지우고 비교한다."""

from ncs_core import make_normalizer

HEAD_NUMBER = r"^\d+\.\s*"
norm, same = make_normalizer(HEAD_NUMBER)
