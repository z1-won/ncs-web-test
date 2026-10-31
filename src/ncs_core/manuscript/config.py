"""공통 구조 파서의 조정 가능한 양식 가정. 섹션 선택은 각 검수 패키지의 CheckConfig가 맡는다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParseConfig:
    """parse_body·section_presence가 쓰는 임계값. 판정 정책이 아니라 '무엇을 제목·내용으로 볼지'의 길이 기준이다."""

    body_heading_max_length: int = 60  # 본문 N-M. 제목으로 볼 최대 길이
    eval_candidate_max_length: int = 30  # 평가 블록의 '학습 내용' 후보로 볼 최대 길이
    tail_min_paragraphs: int = 3  # 활용 서식·부록 제목 뒤 내용 문단이 이 미만이면 '배너만'
    reference_min_lines: int = 3  # 참고문헌 꼴 줄이 이 이상 연속이면 참고 자료 존재
    ambiguous_tail_min_paragraphs: int = 10  # 참고 자료 뒤 문단이 이 이상이면 활용 서식 가능성

    def __post_init__(self):
        for name in (
            "body_heading_max_length",
            "eval_candidate_max_length",
            "tail_min_paragraphs",
            "reference_min_lines",
            "ambiguous_tail_min_paragraphs",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name}은 1 이상이어야 합니다")


DEFAULT_PARSE_CONFIG = ParseConfig()
