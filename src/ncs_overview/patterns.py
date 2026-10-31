"""개요 양식의 제목·내용 인식 패턴. 판정 정책은 rules/에 둔다."""
import re

HEAD_OVERVIEW = re.compile(r"학습모듈의\s*개요$")
HEAD_GOAL = re.compile(r"^학습모듈의\s*목표$")
HEAD_PREREQ = re.compile(r"^선수\s*학습$")
HEAD_STRUCTURE = re.compile(r"^학습모듈의\s*내용\s*체계$")
HEAD_TERMS = re.compile(r"^핵심\s*용어$")
OV_LESSON = re.compile(r"^(\d+)\.\s*(\S.*)$")           # 1. 명 (개요 표)
PLAN_LESSON = re.compile(r"^(\d+)\.\s+(\S.*)$")         # 계획서 학습명: 공백 필수 ("1.1 …" 수행준거와 구별)
OV_SUB = re.compile(r"^(\d+)-(\d+)\.\s*(.*)$")          # 1-1. 명 (명이 다음 줄에 올 수도 있음)
ELEMENT_CODE = re.compile(r"^(\d{10}_\d+v\d+)\.(\d+)$")  # 1203020201_24v3.1
GOAL_END = re.compile(r"할\s*수\s*있다\s*\.$")
# 능력단위 정의 → 학습모듈의 목표: 주어('…란/이란/은/는') 삭제, '~하는 능력이다' → '~할 수 있다'
DEFINITION_SUBJECT = re.compile(r"^.*?(?:이란|란|은|는)\s+")
DEFINITION_END = re.compile(r"(하|할 수 있)는\s*능력이다\s*\.?$")
# ⑧ 단어(명사형)가 아닐 가능성이 있는 종결
TERM_PREDICATE = re.compile(r"(다|하기|함|됨|하는|되는|할 것|것)$")
