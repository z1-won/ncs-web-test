"""개요 검수의 조정 가능한 양식 가정."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0          # 학습모듈의 개요가 있는 섹션
    max_prerequisites: int = 5      # ② 선수학습 최대 개수
    max_terms: int = 10             # ⑧ 핵심 용어 최대 개수
    term_max_length: int = 25       # ⑧ 이보다 긴 항목은 단어가 아닐 가능성 → △

    def __post_init__(self):
        if self.front_section < 0:
            raise ValueError("섹션 번호는 0 이상이어야 합니다")
        for name in ("max_prerequisites", "max_terms", "term_max_length"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name}은 1 이상이어야 합니다")


DEFAULT_CONFIG = CheckConfig()
