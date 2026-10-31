"""원고·개발계획서 양식의 제목·내용 인식 패턴. 판정 정책(무엇을 X로 볼지)은 각 검수 패키지 rules/에 둔다."""

import re

# 차례 면
TOC_LESSON = re.compile(r"^학습\s*(\d+)\.\s*(.+?)(?:\s+\d+)?$")  # 학습 1. 명 [쪽]
TOC_SUB = re.compile(r"^(\d+)-(\d+)\.\s*(.+?)(?:\s*(\d+))?$")  # 1-1. 명 [쪽]  ('• 평가52' 처럼 붙은 쪽수도)
TOC_LINE = re.compile(r"^[•·]\s*(교수\s*\W{0,3}\s*학습\s*방법|평가)\s*(\d+)?$")
TOC_TAIL = re.compile(r"^(참고\s*자료|활용\s*서식|부록)\s*(\d+)?$")

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

# 본문
NAV_HEAD = re.compile(r"^학습\s*(\d+)$")
BODY_SUB = re.compile(r"^(\d+)-(\d+)\.\s*(.*)$")
HEAD_TEACH = re.compile(r"^교수\s*\W{0,3}\s*학습\s*방법$")
HEAD_EVAL = re.compile(r"^평\s*가$")
REF_LINE = re.compile(r"^[•·]?\s*\S.{0,80}?\(\d{4}[a-z]?\)\s*[.,]")  # • 저자(연도).
EVAL_LABELS = {"평가 준거", "학습 내용", "학습 목표", "성취수준", "상", "중", "하", "평가 방법", "평가 항목", "피드백", "학습내용"}
EVAL_ITEM_END = re.compile(r"(여부|능력|수준|정도|가능)\s*$")  # 평가 항목 줄 종결어 (학습 내용명 후보에서 제외)
