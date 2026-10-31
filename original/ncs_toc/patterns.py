"""양식별 제목·내용 인식 패턴. 판정 정책은 rules/에 둔다."""
import re

TOC_LESSON = re.compile(r'^학습\s*(\d+)\.\s*(.+?)(?:\s+\d+)?$')                 # 학습 1. 명 [쪽]
TOC_SUB    = re.compile(r'^(\d+)-(\d+)\.\s*(.+?)(?:\s*(\d+))?$')                 # 1-1. 명 [쪽]  ('• 평가52' 처럼 붙은 쪽수도)
TOC_LINE   = re.compile(r'^[•·]\s*(교수\s*\W{0,3}\s*학습\s*방법|평가)\s*(\d+)?$')
TOC_TAIL   = re.compile(r'^(참고\s*자료|활용\s*서식|부록)\s*(\d+)?$')
OV_LESSON  = re.compile(r'^(\d+)\.\s*(\S.*)$')                                   # 개요 내용체계: 1. 명
OV_SUB     = re.compile(r'^(\d+)-(\d+)\.\s*(\S.*)$')
NAV_HEAD   = re.compile(r'^학습\s*(\d+)$')
BODY_SUB   = re.compile(r'^(\d+)-(\d+)\.\s*(.*)$')
HEAD_TEACH = re.compile(r'^교수\s*\W{0,3}\s*학습\s*방법$')
HEAD_EVAL  = re.compile(r'^평\s*가$')
REF_LINE   = re.compile(r'^[•·]?\s*\S.{0,80}?\(\d{4}[a-z]?\)\s*[.,]')          # • 저자(연도).
EVAL_LABELS = {'평가 준거', '학습 내용', '학습 목표', '성취수준', '상', '중', '하', '평가 방법', '평가 항목', '피드백', '학습내용'}
EVAL_ITEM_END = re.compile(r'(여부|능력|수준|정도|가능)\s*$')     # 평가 항목 줄 종결어 (학습 내용명 후보에서 제외)
