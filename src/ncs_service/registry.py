"""검수 종류와 엔진·필수 입력의 연결. HTTP 계층에 의존하지 않는다."""

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType


@dataclass(frozen=True)
class Engine:
    package: str
    required: tuple[str, ...] = ("manuscript",)

    def load(self) -> ModuleType:
        return import_module(self.package)


# 순서 = F02 검수 확인서의 구성요소 순서. 화면·서버 목록도 이 순서를 따른다.
ENGINES = {
    "position": Engine("ncs_position", ("manuscript", "plan")),
    "toc": Engine("ncs_toc"),
    "overview": Engine("ncs_overview"),
    "knowledge": Engine("ncs_knowledge"),
    "perform": Engine("ncs_perform"),
    "teaching": Engine("ncs_teaching"),
    "evaluation": Engine("ncs_evaluation"),
    "misc": Engine("ncs_misc"),
}


def get_engine(check: str) -> Engine:
    if check not in ENGINES:
        raise ValueError("check는 " + " / ".join(ENGINES) + " 중 하나여야 합니다")
    return ENGINES[check]
