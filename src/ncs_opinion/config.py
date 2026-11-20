"""검토의견서 반영 여부 검토의 설정값과 그 근거 — 의견서 양식 가정, 원고에서 찾는 범위, 판정 문턱.

근거
- 의견서 양식: F23 원고 샘플(SW제품기획)의 1·2차 검토의견서 20개(hwp 12, PDF 8). 머리(세분류명·검토진·학습모듈명) 뒤
  표 `구분 | 쪽수 | 검토의견`, 구분은 학습모듈 개요 → 학습 N(필요지식·수행 내용·교수･학습 방법·평가) → 기타, 표 밖에 종합 의견.
  1차는 표 앞에 개발계획서 검토의견 칸이 더 있다. 쪽수는 '4', '3-6', '-' 꼴, 의견은 '-'로 시작하는 줄, '의견없음'·'-'는 의견 아님.
- 원고에서 찾는 범위: 의견이 <표 N-M>·[그림 N-M]을 가리키면 그 캡션부터 다음 캡션까지(표는 캡션 아래 최대 table_window 문단,
  그림은 캡션 앞뒤 figure_window 문단). 없으면 의견서의 학습·구성 구간, 그것도 못 정하면 원고 전체(→ 근거가 약하므로 '확인 필요').
- 출력본 PDF가 있으면 근거 문장이 실린 쪽을 찾아 붙인다. 의견서의 쪽수는 초고본·완성본 기준이라 최종본과 몇 쪽 어긋날 수 있어
  판정에는 쓰지 않고 위치 안내에만 쓴다.
- 판정 문턱: 핵심어가 범위 안에 모두 있으면 '반영 후보', 원고 어디에도 없으면 '미반영 후보', 그 사이는 '확인 필요'.
  긴 핵심어(문장 수정 의견의 새 문장)는 글자 일치율 fuzzy 이상이면 있는 것으로 본다(오탈자가 고쳐진 경우).
- 용어 변경 의견(A → B, 'A'를 'B'로, A는 B로 명칭 변경됨)은 반영 여부와 관계없이 '확인 필요'로 두고 집필자에게 물을 문장을 붙인다
  (요구사항정의서 V0.23 REQ-02-003: 용어 변경 의견은 즉시 반영으로 보지 않는다).
"""

from __future__ import annotations

from dataclasses import dataclass

# 판정 후보(사람이 확정한다 — Human-in-the-Loop)
REFLECTED = "반영 후보"
NOT_REFLECTED = "미반영 후보"
CHECK = "확인 필요"
NO_ACTION = "조치 불필요"
VERDICTS = (REFLECTED, NOT_REFLECTED, CHECK, NO_ACTION)

# 의견 유형
KIND_TERM = "용어"
KIND_CONTENT = "내용"
KIND_FORM = "형식"
KIND_FIGURE = "그림"
KIND_NONE = "의견 아님"

# 원고 구성 이름(원고 표기) — 의견서의 '필요지식'·'교수･학습 방법'은 이 이름으로 맞춘다
OVERVIEW = "학습모듈 개요"
PARTS = ("필요 지식", "수행 내용", "교수·학습 방법", "평가")
OTHER = "기타"
SUMMARY = "종합 의견"
PLAN = "개발계획서"

LLM_TASK = "opinion_reflection"   # ncs_core.llm.ALLOWED_TASKS에 아직 없음 — 추가되기 전에는 LLM 판정이 '판단불가'로 남는다


@dataclass(frozen=True)
class OpinionConfig:
    table_window: int = 60        # <표 N-M> 캡션 아래로 볼 최대 문단 수(다음 캡션이 먼저 나오면 거기까지)
    figure_window: int = 4        # [그림 N-M] 캡션 앞뒤로 볼 문단 수(그림 속 글은 원고 글에 없다)
    max_keys: int = 6             # 의견 하나에서 쓰는 핵심어 수
    long_key: int = 15            # 이보다 긴 핵심어는 글자 일치율로 찾는다
    fuzzy: float = 0.85           # 긴 핵심어 글자 일치율 문턱
    evidence_chars: int = 160     # 근거 문장 표시 길이
    llm_lines: int = 60           # LLM 한 번에 보내는 원고 문단 수 상한
    llm_per_opinion: int = 12     # 의견 하나를 위해 고르는 문단 수(범위가 이보다 작으면 범위 전체)
    llm_min_overlap: int = 2      # 의견과 겹치는 두 글자 조각이 이만큼은 있어야 고른다
    llm_batch: int = 10           # LLM 한 번에 묻는 의견 수(같은 범위를 가리키는 의견끼리)
    llm_para_chars: int = 300     # 보내는 문단 하나의 길이 상한


DEFAULT_CONFIG = OpinionConfig()
