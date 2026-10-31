"""위치 양식의 라벨·제목 인식 패턴. 판정 정책은 rules/에 둔다."""

import re

RP = "section0 > NCS-학습모듈의 위치"
POSITION_ANCHOR = "[NCS-학습모듈의 위치]"
LABELS3 = ("대분류", "중분류", "소분류")
TABLE_HEADERS = ("세분류", "능력단위", "학습모듈명")
MODULE_CODE_PARTS = re.compile(r"LM(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})")
PLAN_NAME_LABEL = re.compile(r"(①\s*-\s*b\s*)?학습\s*모듈\s*명")
PLAN_NAME_INLINE = re.compile(r"(?:①\s*-\s*b\s*)?학습\s*모듈\s*명\s+(\S.+)$")
KOPUB_DOTUM = "KoPub돋움체"
