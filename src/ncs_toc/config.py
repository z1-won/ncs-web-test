"""차례 검수의 조정 가능한 양식 가정. 섹션 선택과 공통 파서(ncs_core.manuscript)의 임계값을 함께 둔다."""
from dataclasses import dataclass

from ncs_core.manuscript import ParseConfig


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

    def parse_config(self) -> ParseConfig:
        """공통 본문·꼬리 섹션 파서에 넘길 임계값."""
        return ParseConfig(
            body_heading_max_length=self.body_heading_max_length,
            eval_candidate_max_length=self.eval_candidate_max_length,
            tail_min_paragraphs=self.tail_min_paragraphs,
            reference_min_lines=self.reference_min_lines,
            ambiguous_tail_min_paragraphs=self.ambiguous_tail_min_paragraphs,
        )


DEFAULT_CONFIG = CheckConfig()
