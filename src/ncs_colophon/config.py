"""판권 검수의 조정 가능한 양식 가정."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0
    body_section: int = 1
    copyright_holder: str = "교육부"
    agency: str = "한국직업능력연구원"   # 현재 연구사업기관 명칭(F14). 개선 양식의 '이전 이력' 블록에서는 구 명칭을 허용한다

    def __post_init__(self):
        if self.front_section < 0 or self.body_section < 0 or self.front_section == self.body_section:
            raise ValueError("차례와 본문 섹션은 서로 다른 0 이상의 번호여야 합니다")


DEFAULT_CONFIG = CheckConfig()
