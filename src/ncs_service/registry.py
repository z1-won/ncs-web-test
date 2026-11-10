"""검수 종류와 엔진·필수 입력의 연결. HTTP 계층에 의존하지 않는다."""

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType


@dataclass(frozen=True)
class Engine:
    package: str
    required: tuple[str, ...] = ("manuscript",)
    optional: tuple[str, ...] = ()      # 선택 입력 역할. 예: ("print",) 출력본 PDF → prepare_review(print_copy=…) (service.OPTIONAL_KWARGS)

    def load(self) -> ModuleType:
        return import_module(self.package)


# 순서 = F02 검수 확인서의 구성요소 순서. 화면·서버 목록도 이 순서를 따른다.
ENGINES = {
    "position": Engine("ncs_position", ("manuscript", "plan")),
    "toc": Engine("ncs_toc", optional=("print",)),
    "overview": Engine("ncs_overview"),
    "knowledge": Engine("ncs_knowledge"),
    "perform": Engine("ncs_perform"),
    "teaching": Engine("ncs_teaching"),
    "evaluation": Engine("ncs_evaluation"),
    "references": Engine("ncs_references"),
    "colophon": Engine("ncs_colophon"),
    "misc": Engine("ncs_misc"),
}


def get_engine(check: str) -> Engine:
    if check not in ENGINES:
        raise ValueError("check는 " + " / ".join(ENGINES) + " 중 하나여야 합니다")
    return ENGINES[check]


def describe_engines() -> list[dict]:
    """화면·API용 엔진 설명 — [{'check', 'component', 'items': ['①', …](구현된 확인서 항목), 'required', 'optional'}]. 확인서 순서."""
    out = []
    for check, engine in ENGINES.items():
        sheet = import_module(engine.package + ".sheet")
        out.append({
            "check": check,
            "component": sheet.COMPONENT,
            "items": [item.no for item in sheet.ITEMS if item.item_ids],
            "total": len(sheet.ITEMS),
            "required": list(engine.required),
            "optional": list(engine.optional),
        })
    return out

