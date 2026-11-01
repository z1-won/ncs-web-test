"""참고 자료 검수의 조정 가능한 양식 가정."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0
    body_section: int = 1

    def __post_init__(self):
        if self.front_section < 0 or self.body_section < 0 or self.front_section == self.body_section:
            raise ValueError("차례와 본문 섹션은 서로 다른 0 이상의 번호여야 합니다")


DEFAULT_CONFIG = CheckConfig()
