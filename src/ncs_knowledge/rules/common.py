"""규칙 모듈이 함께 쓰는 행 생성기."""

from ncs_core import PASS, verdict

ITEM = "F02-필요지식-"


def row(no: str, region_path: str, source, checks: dict, notes: dict, suggestion=None, **extra) -> dict:
    result = verdict(checks)
    out = {
        "item_id": ITEM + no,
        "region_path": region_path,
        "원고": source,
        "체크": checks,
        "판정": result,
        "비고": notes,
        "수정 제안": None if result == PASS else suggestion,
    }
    out.update(extra)
    return out
