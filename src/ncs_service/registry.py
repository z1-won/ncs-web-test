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


ENGINES = {
    "position": Engine("ncs_position", ("manuscript", "plan")),
    "toc": Engine("ncs_toc"),
    "overview": Engine("ncs_overview"),
    "knowledge": Engine("ncs_knowledge"),
}


def get_engine(check: str) -> Engine:
    if check not in ENGINES:
        raise ValueError("check는 " + " / ".join(ENGINES) + " 중 하나여야 합니다")
    return ENGINES[check]
