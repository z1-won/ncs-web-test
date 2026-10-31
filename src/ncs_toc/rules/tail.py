"""F02 차례 ⑤·⑥: 참고 자료, 활용 서식·부록의 차례↔본문 일치."""

from ncs_core import O, PASS, TRI, verdict, X

ITEM_ID_5 = "F02-차례-⑤"
ITEM_ID_6 = "F02-차례-⑥"


def check_toc5(presence: dict, toc: dict) -> list[dict]:
    found = presence["참고 자료"]
    in_toc = "참고 자료" in toc["꼬리"]
    checks = {
        "⑤ 참고 자료 본문 존재": O if found["있음"] else X,
        "차례에 참고 자료 줄": O if in_toc else X,
    }
    notes = {"근거": found["근거"]}
    if not in_toc:
        notes["차례에 참고 자료 줄"] = '차례에 "참고 자료" 줄이 없음'
    if not found["있음"]:
        notes["⑤ 참고 자료 본문 존재"] = "본문에서 참고 자료를 찾지 못함 (필수 작성)"
    result = verdict(checks)
    return [
        {
            "item_id": ITEM_ID_5,
            "region_path": "section1 > 참고 자료",
            "원고": found["근거"],
            "차례": toc["꼬리"].get("참고 자료"),
            "체크": checks,
            "판정": result,
            "비고": notes,
            "수정 제안": None if result == PASS else "참고 자료를 작성하고 차례에 쪽수와 함께 제시",
        }
    ]


def check_toc6(presence: dict, toc: dict) -> list[dict]:
    rows = []
    for name in ("활용 서식", "부록"):
        found, in_toc = presence[name], name in toc["꼬리"]
        toc_page = toc["꼬리"][name] or "" if in_toc else ""
        if found["있음"] is None:
            value = TRI
            note = f'본문: {found["근거"]}' + (f" / 차례에는 {name} {toc_page}" if in_toc else " / 차례에는 없음")
        elif in_toc and found["있음"]:
            value, note = O, f'차례·본문 모두 있음 — {found["근거"]}'
        elif in_toc and not found["있음"]:
            value, note = X, f'차례에는 "{name} {toc_page}" 이 있는데 본문에 없음 — 미작성이면 차례에서 삭제'
        elif not in_toc and found["있음"]:
            value, note = X, f'본문에 {name} 이 있는데({found["근거"]}) 차례에 없음 — 차례에 추가'
        else:
            value, note = O, "차례·본문 모두 없음 (해당 없음)"
        label = f"⑥ {name} 차례↔본문 일치"
        checks = {label: value}
        if value == O:
            suggestion = None
        elif in_toc and found["있음"] is False:
            suggestion = "차례에서 삭제"
        elif found["있음"] and not in_toc:
            suggestion = "차례에 추가"
        else:
            suggestion = "본문 확인 후 차례와 맞출 것"
        rows.append(
            {
                "item_id": ITEM_ID_6,
                "region_path": f"section0 > 차례 > {name}",
                "원고": {"차례": toc["꼬리"].get(name) if in_toc else None, "본문": found["있음"]},
                "체크": checks,
                "판정": verdict(checks),
                "비고": {label: note} if value != O or "해당 없음" in note else {},
                "수정 제안": suggestion,
            }
        )
    return rows
