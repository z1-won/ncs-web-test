"""필요 지식 검수의 조정 가능한 양식 가정. 공통 본문 파서(ncs_core.manuscript)는 기본 임계값으로 쓴다."""
from dataclasses import dataclass

from ncs_core.manuscript import DEFAULT_PARSE_CONFIG, ParseConfig


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0            # 차례·개요 섹션
    body_section: int = 1             # 본문 섹션
    goal_lookahead: int = 8           # ⑤ N-M. 제목 뒤 몇 줄 안에서 '학습 목표' 줄을 찾는가
    figtab_min_agreement: float = 0.5 # ⑦ 캡션 앞 번호와 학습 경계 일치율이 이 미만이면 '-위치' 검사 생략
    source_lookback: int = 3          # ⑧ 그림 캡션 위 몇 줄 안에서 출처 줄을 찾는가
    source_lookahead: int = 80        # ⑧ 표 캡션 아래 몇 줄 안에서 출처 줄을 찾는가

    def __post_init__(self):
        if self.front_section < 0 or self.body_section < 0:
            raise ValueError("섹션 번호는 0 이상이어야 합니다")
        if self.front_section == self.body_section:
            raise ValueError("현재 파서는 차례·개요와 본문이 별도 섹션인 양식을 지원합니다")
        if not 0 <= self.figtab_min_agreement <= 1:
            raise ValueError("일치율은 0~1 사이여야 합니다")
        for name in ("goal_lookahead", "source_lookback", "source_lookahead"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name}은 1 이상이어야 합니다")

    def parse_config(self) -> ParseConfig:
        return DEFAULT_PARSE_CONFIG


DEFAULT_CONFIG = CheckConfig()
