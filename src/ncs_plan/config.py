"""개발계획서 점검의 조정 가능한 양식 가정."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0          # 공용 CLI가 넘기는 값. 계획서는 표로 읽으므로 섹션 번호는 쓰지 않는다
    use_catalog: bool = True        # NCS 목록(ncs_units.tsv) 대조 사용 여부

    def __post_init__(self):
        if self.front_section < 0:
            raise ValueError("섹션 번호는 0 이상이어야 합니다")


DEFAULT_CONFIG = CheckConfig()
