"""규칙 모듈이 함께 쓰는 행 생성기."""

import re

from ncs_core import PASS, verdict

ITEM = "F02-필요지식-"


def row(no: str, region_path: str, source, checks: dict, notes: dict, suggestion=None, **extra) -> dict:
    result = verdict(checks)
    # 확인서 비고용 짧은 위치: region_path의 '1-1. 제목' 또는 '학습 2'. 없으면 빈 문자열(건수만 적힘)
    where = re.search(r"(\d+-\d+)\.", region_path) or re.search(r"(학습 \d+)", region_path)
    out = {
        "item_id": ITEM + no,
        "region_path": region_path,
        "위치": where.group(1) if where else "",
        "원고": source,
        "체크": checks,
        "판정": result,
        "비고": notes,
        "수정 제안": None if result == PASS else suggestion,
    }
    out.update(extra)
    return out
