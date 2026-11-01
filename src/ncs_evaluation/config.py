"""평가 검수 대상 섹션 설정."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0
    body_section: int = 1
    min_methods: int = 2   # ③ 평가 방법 최소 개수(F02: 2개 이상)

    def __post_init__(self):
        if min(self.front_section, self.body_section) < 0 or self.front_section == self.body_section:
            raise ValueError("차례와 본문 섹션은 서로 다른 0 이상의 번호여야 합니다")
        if self.min_methods < 1:
            raise ValueError("min_methods는 1 이상이어야 합니다")


DEFAULT_CONFIG = CheckConfig()
