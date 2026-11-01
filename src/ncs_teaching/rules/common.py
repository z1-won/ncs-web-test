"""규칙 모듈이 함께 쓰는 행 생성기."""

from ncs_core import PASS, verdict

ITEM = "F02-교수학습-"
PART_LABEL = {"교수": "교수 방법", "학습": "학습 방법"}


def row(no: str, block: dict, source, checks: dict, notes: dict, suggestion=None, **extra) -> dict:
    result = verdict(checks)
    out = {
        "item_id": ITEM + no,
        "region_path": f"section1 > {block['block_id']}",
        "위치": f"학습 {block['lesson']}" if block.get("lesson") else block["block_id"],
        "원고": source,
        "개발계획서": None,
        "체크": checks,
        "판정": result,
        "비고": notes,
        "수정 제안": None if result == PASS else suggestion,
    }
    out.update(extra)
    return out


def no_block_row(no: str, check_name: str) -> dict:
    from ncs_core import TRI

    checks = {check_name: TRI}
    return {
        "item_id": ITEM + no, "region_path": "section1", "위치": "", "원고": None, "개발계획서": None,
        "체크": checks, "판정": verdict(checks),
        "비고": {check_name: "본문에서 '교수·학습 방법' 머리를 찾지 못해 판단할 수 없음"}, "수정 제안": None,
    }
