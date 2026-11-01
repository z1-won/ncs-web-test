"""판권 ①: 개발 이력과 판권을 지침에 맞게 작성하였는가.

- 양식: 모듈 코드의 판 번호(LM…_24v3의 v3)가 1이면 신규 양식(이력 블록 1개·세분류명), 2 이상이면 개선 양식(이력 블록 2개 이상·학습모듈명).
  양식 표가 둘 다 남아 있거나 판권 표가 둘이면 X(양식 미정리).
- 세분류 코드 8자리 = 모듈 코드 앞 8자리. 학습모듈명(LM코드)의 코드 = 모듈 코드. 자리표시(○○○, 20XX, (세분류 코드번호)) 남아 있으면 X.
- 판권 표: 저작권자·연구사업기관·발행일 값, ISBN 행. 개선 양식의 '이전 이력' 블록은 구 기관명을 허용한다.
- 개발 이력의 개발기관: 위탁 개발기관(협회)만 적는 것이 F14 지침 — 빈 칸·자리표시·구 명칭만 지적한다.
"""

from ncs_core import NA, O, PASS, TRI, X, verdict, visible

from ..tables import LM_CODE, PLACEHOLDER

ITEM_ID = "F02-판권-①"
REGION = "section1 > 개발 이력 및 판권"


def _row(region: str, where: str, source, checks: dict, notes: dict, suggestion=None, **extra) -> dict:
    result = verdict(checks)
    out = {"item_id": ITEM_ID, "region_path": region, "위치": where, "원고": source, "체크": checks, "판정": result, "비고": notes,
           "수정 제안": None if result == PASS else suggestion}
    out.update(extra)
    return out


def expected_form(module_code: str) -> str | None:
    m = LM_CODE.search(module_code)
    if not m:
        return None
    return "신규" if int(m.group(3)) <= 1 else "개선"


def check_colophon(histories: list[dict], colophons: list[dict], module_code: str, config) -> list[dict]:
    rows = []
    form = expected_form(module_code)
    code_match = LM_CODE.search(module_code)
    subclass = code_match.group(1)[:8] if code_match else None

    # 1) 양식 — 이력 표 개수·블록 수
    checks, notes = {}, {}
    if not histories:
        checks["양식"] = X
        notes["양식"] = "'NCS학습모듈 개발이력' 표를 찾지 못함"
    elif len(histories) > 1:
        checks["양식"] = X
        notes["양식"] = f"개발 이력 표가 {len(histories)}개 — 신규·개선 양식이 모두 남아 있음(해당 양식 하나만 남길 것)"
    elif form is None:
        checks["양식"] = TRI
        notes["양식"] = f"모듈 코드({module_code})에서 판 번호를 읽지 못해 신규/개선 양식을 정하지 못함"
    else:
        blocks = histories[0]["blocks"]
        actual = "신규" if len(blocks) == 1 else "개선" if len(blocks) >= 2 else "미상"
        checks["양식"] = O if actual == form else X
        if actual != form:
            notes["양식"] = f"코드 판 번호상 {form} 양식이어야 하는데 이력 블록 {len(blocks)}개({actual} 양식 꼴)"
    rows.append(_row(REGION + " > 양식", "", {"기대 양식": form, "이력 표": len(histories), "판권 표": len(colophons)}, checks, notes,
                     "모듈 코드 판 번호에 맞는 개발 이력 양식 하나만 남기고 나머지는 삭제"))

    # 2) 개발 이력 내용 — 기대 양식에 맞는 표(없으면 첫 표)의 마지막(이번) 블록 기준
    if histories:
        chosen = next((h for h in histories if (len(h["blocks"]) == 1) == (form == "신규")), histories[0]) if form else histories[0]
        for h in (chosen,):
            blocks = h["blocks"]
            current = blocks[-1] if blocks else None
            checks, notes = {}, {}
            if current is None:
                checks["이력 내용"] = X
                notes["이력 내용"] = "개발 이력 표에 '발행일' 행이 없음"
            else:
                filled = {k: v for k, v in current.items() if k in ("발행일", "세분류명", "학습모듈명", "개발기관")}
                holders = [k for k, v in filled.items() if v and PLACEHOLDER.search(v)] + \
                          (["집필진"] if any(PLACEHOLDER.search(v) for v in current["집필진"]) else []) + \
                          (["검토진"] if any(PLACEHOLDER.search(v) for v in current["검토진"]) else [])
                checks["자리표시 제거"] = X if holders else O
                if holders:
                    notes["자리표시 제거"] = "양식의 자리표시(○○○·코드번호 자리)가 그대로 남은 칸: " + ", ".join(holders)
                if form == "신규" or (form is None and current["세분류명"] is not None):
                    value = current["세분류명"] or ""
                    import re
                    m = re.search(r"\((\d{8})\)", value)
                    checks["세분류 코드 8자리"] = O if m and m.group(1) == subclass else X
                    if not (m and m.group(1) == subclass):
                        notes["세분류 코드 8자리"] = f'세분류명 칸 "{visible(value)[:30]}" — "세분류명(세분류 코드 8자리)" 꼴로 {subclass or "모듈 코드 앞 8자리"} 기재'
                if form == "개선" or (form is None and current["학습모듈명"] is not None):
                    value = current["학습모듈명"] or ""
                    m = LM_CODE.search(value)
                    checks["학습모듈명·코드"] = O if m and m.group() == (code_match.group() if code_match else None) else X
                    if checks["학습모듈명·코드"] == X:
                        notes["학습모듈명·코드"] = f'학습모듈명 칸 "{visible(value)[:40]}" — "학습모듈명({module_code})" 꼴이어야 함'
                # F14 메모: "위탁 개발기관이 있는 경우 직능연을 병기하지 않습니다" → 협회명만 적힌 것이 정상.
                # 지적 대상은 빈 칸, 자리표시(○○○협회), 구 명칭(한국직업능력개발원)만.
                agency = current["개발기관"] or ""
                if not agency.strip():
                    checks["개발기관 명칭"] = X
                    notes["개발기관 명칭"] = "개발기관 칸이 비어 있음"
                elif "한국직업능력개발원" in agency:
                    checks["개발기관 명칭"] = X
                    notes["개발기관 명칭"] = f'구 명칭 "한국직업능력개발원" — 현재 명칭은 "{config.agency}": "{visible(agency)[:40]}"'
                if not current["집필진"] or not current["검토진"]:
                    checks["집필진·검토진"] = X
                    notes["집필진·검토진"] = "집필진 또는 검토진 칸이 비어 있음"
            rows.append(_row(REGION + " > 개발 이력", "", {"블록": len(blocks), "이번 블록": {k: v for k, v in (current or {}).items() if k != "rows"}},
                             checks, notes, "개발 이력 표의 세분류 코드·학습모듈명·개발기관·집필진·검토진을 지침대로 기재"))

    # 3) 판권 표
    checks, notes = {}, {}
    if not colophons:
        checks["판권 표"] = X
        notes["판권 표"] = "판권 표(저작권자·연구사업기관·발행일·ISBN)를 찾지 못함"
        rows.append(_row(REGION + " > 판권", "", None, checks, notes, "판권 표 작성"))
        return rows
    if len(colophons) > 1:
        checks["판권 표"] = X
        notes["판권 표"] = f"판권 표가 {len(colophons)}개 — 하나만 남길 것"
    c = colophons[-1]
    checks["학습모듈명·코드"] = O if c["code"] and code_match and c["code"] == code_match.group() else X
    if checks["학습모듈명·코드"] == X:
        notes["학습모듈명·코드"] = f'판권 첫 칸 "{visible(c["학습모듈명"])[:40]}" — "학습모듈명({module_code})" 이어야 함'
    checks["저작권자"] = O if (c["저작권자"] or "") == config.copyright_holder else X
    if checks["저작권자"] == X:
        notes["저작권자"] = f'"{c["저작권자"]}" — "{config.copyright_holder}"'
    checks["연구사업기관"] = O if (c["연구사업기관"] or "") == config.agency else X
    if checks["연구사업기관"] == X:
        notes["연구사업기관"] = f'"{c["연구사업기관"]}" — "{config.agency}"'
    checks["발행일"] = O if c["발행일"] and not PLACEHOLDER.search(c["발행일"]) else X
    if checks["발행일"] == X:
        notes["발행일"] = f'발행일 "{c["발행일"]}"'
    checks["ISBN 행"] = O if c["ISBN"] else X
    if not c["ISBN"]:
        notes["ISBN 행"] = "ISBN 행이 없음"
    elif not c["isbn_value"]:
        notes["ISBN 행(참고)"] = "ISBN 값은 비어 있음(발행 전이면 정상)"
    if histories and histories[0]["blocks"] and histories[0]["blocks"][-1].get("학습모듈명"):
        name_h = histories[0]["blocks"][-1]["학습모듈명"]
        if LM_CODE.sub("", name_h).replace(" ", "") != LM_CODE.sub("", c["학습모듈명"]).replace(" ", ""):
            checks["이력·판권 모듈명 일치"] = X
            notes["이력·판권 모듈명 일치"] = f'개발 이력 "{visible(name_h)[:30]}" / 판권 "{visible(c["학습모듈명"])[:30]}"'
    rows.append(_row(REGION + " > 판권", "", {k: v for k, v in c.items() if k != "paragraph"}, checks, notes,
                     f"판권 표를 학습모듈명({module_code}) · 저작권자 {config.copyright_holder} · 연구사업기관 {config.agency} · 발행일 · ISBN 으로 기재"))
    return rows
