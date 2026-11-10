"""개발계획서 점검의 조정 가능한 양식 가정."""
from dataclasses import dataclass

STAGES = ("final", "draft")


@dataclass(frozen=True)
class CheckConfig:
    front_section: int = 0          # 공용 CLI가 넘기는 값. 계획서는 표로 읽으므로 섹션 번호는 쓰지 않는다
    use_catalog: bool = True        # NCS 목록(ncs_units.tsv) 대조 사용 여부
    # 점검 단계. 'final'(기본) = 개발기관 최종본: 모든 칸이 차 있어야 한다.
    # 'draft' = 직능연 1차본(T02 꼴·자동 입력 초안): 학습모듈명·영문 세분류명·개발기관명·집필진·검토진·개선 유형·학습 내용명은
    # 최종 단계에서 기관이 채우는 칸이므로 비어 있으면 X가 아니라 해당 없음(-)으로 둔다(F21 "학습모듈명은 추후 기관에서 기재").
    stage: str = "final"

    def __post_init__(self):
        if self.front_section < 0:
            raise ValueError("섹션 번호는 0 이상이어야 합니다")
        if self.stage not in STAGES:
            raise ValueError("stage는 'final'(최종) 또는 'draft'(1차) 중 하나여야 합니다")


DEFAULT_CONFIG = CheckConfig()
