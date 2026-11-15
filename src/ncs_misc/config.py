"""기타 검수의 조정 가능한 양식 가정."""
from dataclasses import dataclass

from ncs_core.pictures import DEFAULT_TARGET_DPI


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0
    body_section: int = 1
    knowledge_max_share: float = 0.5   # ⑥ 필요 지식 글자 비율 상한(F02: 최소한 5:5). 넘으면 X
    knowledge_target_share: float = 0.3  # ⑥ 권장 비율(3:7). 상한 이하이지만 이보다 크면 비고에 적는다
    figure_lookback: int = 10          # ② 캡션 위 몇 문단 안의 표·텍스트를 '표로 그린 양식'으로 볼지
    figure_window: int = 40            # ② 캡션 위 몇 문단 안에서 짝지을 그림을 찾는가
    target_dpi: int = DEFAULT_TARGET_DPI  # ⑤⑧ 이미지 해상도 기준(실효 DPI). 미만이면 △ — 화면에서 150/300 중 고른다(ncs_core.pictures.DPI_CHOICES)

    def __post_init__(self):
        if self.front_section < 0 or self.body_section < 0 or self.front_section == self.body_section:
            raise ValueError("차례와 본문 섹션은 서로 다른 0 이상의 번호여야 합니다")
        if not 0 < self.knowledge_target_share <= self.knowledge_max_share < 1:
            raise ValueError("비율은 0 < 권장 ≤ 상한 < 1 이어야 합니다")
        if self.figure_lookback < 1 or self.figure_window < self.figure_lookback:
            raise ValueError("figure_lookback은 1 이상이어야 합니다")
        if not 50 <= self.target_dpi <= 1200:
            raise ValueError("이미지 해상도 기준(target_dpi)은 50~1200 DPI여야 합니다")


DEFAULT_CONFIG = CheckConfig()
