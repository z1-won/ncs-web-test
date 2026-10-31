"""차례 검수의 문자 비교 규칙. 머리 번호 '학습 1. ' / '1. ' / '1-1. '을 지우고 비교한다."""

from ncs_core import make_normalizer

HEAD_NUMBER = r"^(학습\s*)?\d+(-\d+)?\.\s*"
norm, same = make_normalizer(HEAD_NUMBER)
