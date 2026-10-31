"""차례 검수의 조정 가능한 양식 가정. 정규식 자체는 patterns.py에서 관리한다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0
    body_section: int = 1
    body_heading_max_length: int = 60
    eval_candidate_max_length: int = 30
    tail_min_paragraphs: int = 3
    reference_min_lines: int = 3
    ambiguous_tail_min_paragraphs: int = 10

    def __post_init__(self):
        if self.front_section < 0 or self.body_section < 0:
            raise ValueError("섹션 번호는 0 이상이어야 합니다")
        if self.front_section == self.body_section:
            raise ValueError("현재 파서는 차례·개요와 본문이 별도 섹션인 양식을 지원합니다")
        for name in ("body_heading_max_length", "eval_candidate_max_length",
                     "tail_min_paragraphs", "reference_min_lines",
                     "ambiguous_tail_min_paragraphs"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name}은 1 이상이어야 합니다")


DEFAULT_CONFIG = CheckConfig()
