"""수행 내용 검수의 조정 가능한 양식 가정."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0  # 차례·개요 섹션(다른 엔진과 같은 인자 모양을 위해 둔다. 수행 내용 검수는 본문만 본다)
    body_section: int = 1  # 본문 섹션

    def __post_init__(self):
        if self.front_section < 0 or self.body_section < 0:
            raise ValueError("섹션 번호는 0 이상이어야 합니다")
        if self.front_section == self.body_section:
            raise ValueError("차례·개요와 본문은 별도 섹션이어야 합니다")


DEFAULT_CONFIG = CheckConfig()
