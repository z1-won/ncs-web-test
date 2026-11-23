"""검토의견서 반영 여부 검토의 설정값과 그 근거 — 의견서 양식 가정, 원고에서 LLM에 보낼 범위, 판정 정책.

근거
- 의견서 양식: F23 원고 샘플(SW제품기획)의 1·2차 검토의견서 20개(hwp 12, PDF 8). 머리(세분류명·검토진·학습모듈명) 뒤
  표 `구분 | 쪽수 | 검토의견`, 구분은 학습모듈 개요 → 학습 N(필요지식·수행 내용·교수･학습 방법·평가) → 기타, 표 밖에 종합 의견.
  1차는 표 앞에 개발계획서 검토의견 칸이 더 있다. 쪽수는 '4', '3-6', '-' 꼴, 의견은 '-'로 시작하는 줄, '의견없음'·'-'는 의견 아님.
  표에 'N차 검토' 표기가 있으면 그 표기가 화면·CLI의 지정 차수보다 앞선다(2차 파일 안에 1차 표가 함께 든다).
- 심의의견서: F25 기본양식(소위원회 심의의견서) 빈 양식만 있다. 표 `심의 항목 | 세분류 | 심의 의견`, 항목 ①~⑤, 쪽수 칸 없음 →
  차수 '심의', 구분은 항목 이름, 자리는 의견 글의 표·그림 참조로만(없으면 확인 필요). 채워진 실물로는 확인하지 못했다.
- 판정은 LLM(Claude, ncs_llmreview.claude — 작업 이름 opinion_reflection)이 한다. 규칙 코드는 문서 읽기, 보낼 범위 고르기,
  LLM 출력 검증과 정책만 맡는다. 고른 문단 전부를 원고 블록 하나(프롬프트 캐시)로, 의견 전부를 요청 블록 하나로 한 번에 묻는다.
  LLM 설정·승인이 없거나 호출이 실패하면 규칙으로 대신 판정하지 않고 모든 의견을 '확인 필요'와 이유로 둔다(CONVENTIONS 판정 원칙 3).
- 보낼 범위: 의견이 <표 N-M>·[그림 N-M]을 가리키면 그 캡션부터 다음 캡션까지(표는 캡션 아래 최대 table_window 문단,
  그림은 캡션 앞뒤 figure_window 문단). 없으면 의견서의 학습·구성 구간, 그것도 못 정하면 원고 전체에서 의견과 글자가 겹치는 문단만
  (→ 근거가 약하므로 '확인 필요'). 범위가 llm_per_opinion 문단보다 크면 의견과 겹치는 두 글자 조각 점수로 고른다. 원고 전문은 보내지 않는다.
- 출력본 PDF가 있으면 근거 문단이 실린 쪽을 찾아 붙인다. 의견서의 쪽수는 초고본·완성본 기준이라 최종본과 몇 쪽 어긋날 수 있어
  판정에는 쓰지 않고 위치 안내에만 쓴다.
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

# 의견 유형 — LLM이 이 다섯 가지 중 하나로 분류한다. LLM이 답하지 않았거나 부르지 못했으면 '미분류'.
KIND_NONE = "조치 불필요"
KIND_TERM = "용어 변경"
KIND_FORM = "형식"
KIND_FIGURE = "그림"
KIND_CONTENT = "내용"
KIND_UNKNOWN = "미분류"
KINDS = (KIND_NONE, KIND_TERM, KIND_FORM, KIND_FIGURE, KIND_CONTENT)

# LLM이 내는 판정(원래 말) → 판정 후보
LLM_REFLECTED, LLM_MISSING, LLM_CHECK = "반영", "미반영", "확인 필요"

# 원고 구성 이름(원고 표기) — 의견서의 '필요지식'·'교수･학습 방법'은 이 이름으로 맞춘다
OVERVIEW = "학습모듈 개요"
PARTS = ("필요 지식", "수행 내용", "교수·학습 방법", "평가")
OTHER = "기타"
SUMMARY = "종합 의견"
PLAN = "개발계획서"

LLM_TASK = "opinion_reflection"   # Claude 호출의 작업 이름(디스크 캐시 폴더 .llm_cache/llmreview/opinion_reflection/)
WHOLE = "원고 전체"               # 범위를 정하지 못한 의견의 '찾은 범위'
NO_PLACE = "가리키는 자리 없음"    # 개발계획서·종합 의견 — 원고 문단 없이 유형만 묻는다


@dataclass(frozen=True)
class OpinionConfig:
    table_window: int = 60        # <표 N-M> 캡션 아래로 볼 최대 문단 수(다음 캡션이 먼저 나오면 거기까지)
    figure_window: int = 4        # [그림 N-M] 캡션 앞뒤로 볼 문단 수(그림 속 글은 원고 글에 없다)
    evidence_chars: int = 160     # 근거 문단 표시 길이
    llm_lines: int = 400          # 원고 블록에 넣는 최종 원고 문단 수 상한(반영 전 원고 문단도 같은 상한) — 의견 전부가 한 블록을 함께 쓴다
    llm_per_opinion: int = 12     # 의견 하나를 위해 고르는 문단 수(범위가 이보다 작으면 범위 전체)
    llm_min_overlap: float = 0.5  # 고를 문단의 최소 겹침 점수(두 글자 조각마다 1/그 조각이 든 범위 문단 수를 더한 값)
    llm_para_chars: int = 300     # 보내는 문단 하나의 길이 상한


DEFAULT_CONFIG = OpinionConfig()
