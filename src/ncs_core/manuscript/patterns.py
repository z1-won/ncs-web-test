"""원고·개발계획서 양식의 제목·내용 인식 패턴. 판정 정책(무엇을 X로 볼지)은 각 검수 패키지 rules/에 둔다."""

import re

# 차례 면
# 쪽 칸은 숫자이거나, 상호 참조 필드가 갱신되지 않아 한글이 '?'로 표시한 줄 끝의 단독 '?'다.
# 점선 탭은 글자를 내지 않으므로 '?'가 내용명에 공백 없이 붙어 읽히기도 한다('명?'). '??'는 쪽 칸으로 보지 않는다.
TOC_BROKEN_PAGE = "?"
_BROKEN = r"(?<!\?)\?"
TOC_LESSON = re.compile(rf"^학습\s*(\d+)\.\s*(.+?)(?:\s+(\d+)|\s*({_BROKEN}))?$")  # 학습 1. 명 [쪽]
TOC_SUB = re.compile(rf"^(\d+)-(\d+)\.\s*(.+?)(?:\s*(\d+|{_BROKEN}))?$")  # 1-1. 명 [쪽]  ('• 평가52' 처럼 붙은 쪽수도)
TOC_LINE = re.compile(rf"^[•·]\s*(교수\s*\W{{0,3}}\s*학습\s*방법|평가)\s*(\d+|{_BROKEN})?$")
TOC_TAIL = re.compile(rf"^(참고\s*자료|활용\s*서식|부\s*록)\s*(?:[.·ㆍ…⋯‥．。]\s*)*(\d+|{_BROKEN})?$")

# 학습모듈의 개요
HEAD_OVERVIEW = re.compile(r"학습모듈의\s*개요$")
HEAD_GOAL = re.compile(r"^학습모듈의\s*목표$")
HEAD_PREREQ = re.compile(r"^선수\s*학습$")
HEAD_STRUCTURE = re.compile(r"^학습모듈의\s*내용\s*체계$")
HEAD_TERMS = re.compile(r"^핵심\s*용어$")
OV_LESSON = re.compile(r"^(\d+)\.\s*(\S.*)$")  # 1. 명 (내용체계)
OV_SUB = re.compile(r"^(\d+)-(\d+)\.\s*(.*)$")  # 1-1. 명 (명이 다음 줄에 올 수도 있음)
OV_SUB_NAMED = re.compile(r"^(\d+)-(\d+)\.\s*(\S.*)$")  # 1-1. 명 (명이 같은 줄에 있는 것만)
OV_SUB_BARE = re.compile(r"(\d+)-(\d+)\.")  # '1-1.' 만 있고 명칭은 다음 문단
ELEMENT_CODE = re.compile(r"^(\d{10}_\d+v\d+)\.(\d+)$")  # 1203020201_24v3.1

# 개발계획서
PLAN_LESSON = re.compile(r"^(\d+)\.\s+(\S.*)$")  # 계획서 학습명: 공백 필수 ("1.1 …" 수행준거와 구별)
# 계획서의 학습 내용명: '1-1. 명' 외에 '1-1 명'(마침표 없음, AIoT 계획서)도 쓰인다. 원고 쪽(OV_SUB)은 마침표를 요구한다
PLAN_SUB = re.compile(r"^(\d+)-(\d+)(?:\.\s*|\s+)(\S.*)?$")

# 본문
NAV_HEAD = re.compile(r"^학습\s*(\d+)$")
BODY_SUB = re.compile(r"^(\d+)-(\d+)\.\s*(.*)$")
HEAD_TEACH = re.compile(r"^교수\s*\W{0,3}\s*학습\s*방법$")
HEAD_EVAL = re.compile(r"^평\s*가$")
REF_LINE = re.compile(r"^[•·]?\s*\S.{0,80}?\(\d{4}[a-z]?\)\s*[.,]")  # • 저자(연도).
EVAL_LABELS = {"평가 준거", "학습 내용", "학습 목표", "성취수준", "상", "중", "하", "평가 방법", "평가 항목", "피드백", "학습내용"}
EVAL_ITEM_END = re.compile(r"(여부|능력|수준|정도|가능)\s*$")  # 평가 항목 줄 종결어 (학습 내용명 후보에서 제외)
