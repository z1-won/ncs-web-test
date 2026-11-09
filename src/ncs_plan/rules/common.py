"""규칙이 공유하는 행 만들기·비교 도우미. 판정 정책은 각 규칙 파일에."""

import re

from ncs_core import verdict
from ncs_core.goals import PUNCT_ONLY, explain_pair, normalize

ITEM = "PLAN-{}"


def item_id(no: str) -> str:
    return ITEM.format(no)


def row(no: str, region: str, where: str, text, checks: dict, notes: dict, suggestion: str | None = None, **extra) -> dict:
    return {"item_id": item_id(no), "region_path": region, "위치": where, "원고": text, "체크": checks, "판정": verdict(checks),
            "비고": {k: v for k, v in notes.items() if v}, "수정 제안": suggestion, **extra}


def compact(text: str | None) -> str:
    return re.sub(r"\s", "", text or "")


def same_text(a: str | None, b: str | None) -> bool:
    return compact(a) == compact(b)


def same_loose(a: str | None, b: str | None) -> bool:
    """기호·띄어쓰기만 다른 것은 같은 것으로 본다(가운뎃점 앞뒤 공백 등 글꼴·입력 차이)."""
    return PUNCT_ONLY.sub("", normalize(a or "")) == PUNCT_ONLY.sub("", normalize(b or ""))


def pair(expected: str, actual: str, where: str, basis: str) -> str:
    return explain_pair(normalize(expected), normalize(actual), where=where, basis=basis)
