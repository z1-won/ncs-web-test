"""원고 분량 산정의 설정값과 그 근거 — 편집 체계(용지·여백), 쪽당 행 수, 권고 분량, 산정 대상 구성.

근거
- 용지·여백: F07 계약서 붙임1 과업지시서 「학습모듈 집필료 산정 기준」 = A4 297㎜, 위 20·아래 13·머리말 10·꼬리말 12㎜
  (ncs_core.layout과 같은 값). 본문이 놓이는 높이 = 297 − 20 − 13 − 10 − 12 = 242㎜ = 68,598 HWPUNIT(1/7200인치).
  실제 원고(LM2001021701_25v1 hwp)의 줄 배치에서도 쪽 맨 아래 줄이 vertpos 67,440 + 줄 높이 1,100 ≈ 68,540으로 이 값과 맞는다.
- 쪽당 행 수: 본문 한 줄의 줄 간격(글자 높이 + 줄 사이) 1,980 HWPUNIT(같은 원고의 본문 줄 대부분)으로 242㎜를 나눈 34행.
  줄 배치를 읽은 원고는 그 원고에서 가장 많은 줄 간격으로 다시 계산한다(설정값은 배치 정보가 없을 때만 쓴다).
- 한 줄 글자 수(추정용): 같은 원고에서 줄이 꽉 찬(문단 마지막이 아닌) 줄의 평균 폭 — 한글 1, 영문·숫자·기호 0.55로 세어 평균 41.6(1,067줄, 중앙값 41.65) → 41.5.
- 권고 분량 75~85쪽: 3차 멘토 미팅 답변(분야·모듈과 관계없이 권고). 계약 조건이 아니라 참고 표시다.
- 산정 대상: 계약서 제13조 4항 ① — 표지(앞뒤)·NCS학습모듈의 이해·개발진을 뺀 위치·차례·개요·학습·교수·학습 방법·평가·참고 자료·활용 서식·부록.
  제2조 5항 — 사진·삽화·도면·차트·그래프 등 시각 자료는 뺀다(표는 넣는다).
  요구사항정의서 V0.23 요약은 부록을 미반영으로 적고 있어 계약서와 다르다 → include_appendix로 고를 수 있게 하고 기본은 계약서(포함)를 따른다.
"""

from __future__ import annotations

from dataclasses import dataclass

MM_PER_UNIT = 25.4 / 7200

# (구성 이름, 산정 대상인가) — 원고에 나오는 순서. '학습'은 필요 지식·수행 내용으로 나눠 보여 준다.
SEGMENTS = (
    ("표지", False),
    ("NCS학습모듈의 이해", False),
    ("NCS-학습모듈의 위치", True),
    ("차례", True),
    ("학습모듈의 개요", True),
    ("학습 — 필요 지식", True),
    ("학습 — 수행 내용", True),
    ("교수·학습 방법", True),
    ("평가", True),
    ("참고 자료", True),
    ("활용 서식", True),
    ("부록", True),
    ("개발진(개발 이력·판권)", False),
)
APPENDIX = "부록"


@dataclass(frozen=True)
class VolumeConfig:
    body_height: int = 68598          # 본문 높이(HWPUNIT) = 242㎜
    line_pitch: int = 1980            # 본문 한 줄 간격(HWPUNIT) — 배치 정보가 없을 때 쪽당 행 수 계산에 쓴다
    chars_per_line: float = 41.5      # 추정용 한 줄 폭(한글 글자 수 기준)
    half_page: float = 0.5            # ½쪽 이상이면 1쪽(계약서 제13조 4항 ②)
    recommended: tuple[int, int] = (75, 85)
    include_appendix: bool = True     # 계약서 제13조 4항 ①은 부록을 산정 대상에 넣는다
    tolerance_percent: float = 0.5    # 수작업 산정 대비 허용 오차율(요구사항 검증 기준)

    @property
    def lines_per_page(self) -> int:
        return max(1, self.body_height // self.line_pitch)

    def counted(self, segment: str) -> bool:
        if segment == APPENDIX:
            return self.include_appendix
        return dict(SEGMENTS).get(segment, False)


DEFAULT_CONFIG = VolumeConfig()
