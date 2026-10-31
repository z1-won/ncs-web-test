"""위치 검수의 조정 가능한 양식 가정. 정규식과 라벨은 patterns.py에서 관리한다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0  # 'NCS-학습모듈의 위치'가 있는 원고 섹션

    def __post_init__(self):
        if self.front_section < 0:
            raise ValueError("섹션 번호는 0 이상이어야 합니다")


DEFAULT_CONFIG = CheckConfig()
