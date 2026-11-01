"""F02 수행 내용 ①: 수행 내용의 제목은 ‘~하기’로 종결하였는가? — 블록당 1행."""

import re

from ncs_core import NA, O, PASS, TRI, X, verdict, visible

ITEM_ID = "F02-수행-①"
HAGI_END = re.compile(r"하기\s*$")
TRAILING_PUNCT = re.compile(r"[.。,)\]」』]\s*$")


def check_perform_title(blocks: list[dict]) -> list[dict]:
    rows = []
    if not blocks:
        return [{
            "item_id": ITEM_ID, "region_path": "section1", "원고": None, "개발계획서": None,
            "체크": {"① 제목 '~하기' 종결": TRI}, "판정": verdict({"① 제목 '~하기' 종결": TRI}),
            "비고": {"① 제목 '~하기' 종결": "본문에서 '수행 내용' 머리를 찾지 못해 판단할 수 없음"}, "수정 제안": None,
        }]
    # 같은 학습 내용 안에서 수행 내용 번호가 1, 2, 3… 이어지는가
    by_unit: dict[str | None, list[dict]] = {}
    for block in blocks:
        by_unit.setdefault(block["unit"], []).append(block)
    for block in blocks:
        title = block["title"]
        checks = {"① 제목 '~하기' 종결": NA, "제목 존재": O, "수행 내용 번호 연번": NA}
        notes: dict[str, str] = {}
        if not title:
            checks["제목 존재"] = X
            notes["제목 존재"] = "수행 내용 머리 다음에 제목 문단이 없음"
        else:
            if HAGI_END.search(title):
                checks["① 제목 '~하기' 종결"] = O
            else:
                checks["① 제목 '~하기' 종결"] = X
                notes["① 제목 '~하기' 종결"] = (
                    "제목 끝에 문장부호가 붙어 있음" if TRAILING_PUNCT.search(title) and HAGI_END.search(TRAILING_PUNCT.sub("", title))
                    else "'~하기'로 종결되지 않음"
                )
        siblings = by_unit[block["unit"]]
        numbers = [b["perform_no"] for b in siblings]
        if len(siblings) > 1 and all(n is not None for n in numbers):
            expected = list(range(1, len(siblings) + 1))
            checks["수행 내용 번호 연번"] = O if numbers == expected else X
            if numbers != expected:
                notes["수행 내용 번호 연번"] = f"학습 내용 {block['unit']}의 수행 내용 번호 {numbers} — 기대 {expected}"
        elif len(siblings) > 1:
            checks["수행 내용 번호 연번"] = X
            notes["수행 내용 번호 연번"] = f"학습 내용 {block['unit']}에 수행 내용이 {len(siblings)}개인데 번호가 없는 머리가 있음"
        result = verdict(checks)
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": f"section1 > {block['block_id']} > 제목",
                "원고": visible(title) if title else None,
                "개발계획서": None,
                "체크": checks,
                "판정": result,
                "비고": notes,
                "수정 제안": None if result == PASS else "수행 내용 제목을 '~하기'로 종결(문장부호 없이)",
            }
        )
    return rows
