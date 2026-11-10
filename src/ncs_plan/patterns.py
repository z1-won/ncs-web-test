"""개발계획서 판정에만 쓰는 정규식·라벨."""

import re

GOAL_END = re.compile(r"할\s*수\s*있다\s*\.$")
DEFINITION_SUBJECT = re.compile(r"^.*?(?:이란|란|은|는)\s+")        # '객실 예약 접수란 '
DEFINITION_END = re.compile(r"(하|할 수 있)는\s*능력이다\s*\.?$")
LESSON_END = re.compile(r"하기$")
IMPROVE_TYPES = ("신규 개발", "기존 개선", "양식 편집", "최소개선", "최소 개선")
PLACEHOLDER = re.compile(r"0000000000|(?<![A-Za-z])[oO]{2,3}(?![A-Za-z])|○{2,3}|OOO|000\(|학습모듈명\d|능력단위명\d|세분류명\d")
TRAILING_NOTE = re.compile(r"\s*[\(（][^)）]*[\)）]\s*$")
SEPARATOR = re.compile(r"[\s·ㆍ・/,，]+|(?<=\S)(?:\s*및\s*)(?=\S)")
