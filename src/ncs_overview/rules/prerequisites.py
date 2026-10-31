"""F02 개요 ②: '선수학습' 항목 수가 최대 개수(기본 5) 이내인가. '구체적인'은 사람 판단."""

from ncs_core import O, PASS, X, verdict

ITEM_ID = "F02-개요-②"


def check_prerequisites(overview: dict, max_items: int) -> list[dict]:
    block = overview.get("선수학습")
    label = f"② 선수학습 {max_items}개 이내"
    notes: dict[str, str] = {}
    if not block or not block["items"]:
        checks = {label: X}
        notes[label] = "'선수학습' 제목 또는 내용을 찾지 못함"
        evidence = None
    else:
        n = len(block["items"])
        checks = {label: O if n <= max_items else X}
        if n > max_items:
            notes[label] = f"선수학습 {n}개 — {max_items}개 이내로 줄일 것"
        evidence = {"항목": block["items"], "개수": n, "p": block["p"]}
    result = verdict(checks)
    return [
        {
            "item_id": ITEM_ID,
            "region_path": "section0 > 학습모듈의 개요 > 선수학습",
            "원고": evidence,
            "체크": checks,
            "판정": result,
            "비고": notes,
            "수정 제안": None if result == PASS else f"구체적인 과목명·학습모듈명(또는 NCS 능력단위)을 {max_items}개 이내로 제시",
        }
    ]
