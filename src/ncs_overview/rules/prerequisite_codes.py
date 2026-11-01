"""F02 개요 ③: '선수학습'에 NCS 능력단위·학습모듈을 제시한 경우 코드 번호를 함께 적었는가. 예: 네일 미용 위생서비스(LM1201010411_23v5)

항목마다:
  - 코드가 있으면: 형식(LM + 10자리 + _NNvN) → NCS 목록에 있는 코드인가 → 적힌 이름이 목록의 능력단위명과 같은가 → 자기 모듈이 아닌가
  - 코드가 없으면: 이름이 NCS 목록의 능력단위명(학습모듈명)과 같은가. 같으면 "NCS 학습모듈인데 코드 미병기"(X), 없으면 과목명으로 보고 넘어간다.
NCS 목록이 없으면 코드 형식만 보고 나머지는 △. ④(수준)는 목록에 수준 정보가 없어 그대로 미검사.
"""

import re

from ncs_core import O, PASS, TRI, X, make_normalizer, verdict, visible
from ncs_core.ncs_catalog import catalog

ITEM_ID = "F02-개요-③"
REGION = "section0 > 학습모듈의 개요 > 선수학습"
CODE_IN_ITEM = re.compile(r"^(?P<name>.*?)\s*[(（]\s*(?P<code>(?:LM)?\d{10}(?:_\d+v\d+)?)\s*[)）]\s*$")
FULL_CODE = re.compile(r"^LM\d{10}_\d+v\d+$")
_norm, same_name = make_normalizer()


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", "", _norm(text)).lower()


def check_prerequisite_codes(overview: dict, module_code: str) -> list[dict]:
    block = overview.get("선수학습")
    if not block or not block["items"]:
        checks = {"③ 코드 병기": TRI}
        return [_row(None, checks, {"③ 코드 병기": "'선수학습' 내용을 찾지 못함 (②에서 보고)"}, None)]
    cat = catalog()
    names = {}
    if cat:
        for sub in cat.subclasses.values():
            for unit in sub.units:
                names.setdefault(_norm_key(unit.name), []).append(unit)
    checks = {"③ 코드 병기": O, "③ 코드 유효(NCS 목록)": O if cat else TRI, "③ 명칭 일치(NCS 목록)": O if cat else TRI}
    notes: dict[str, list[str]] = {k: [] for k in checks}
    shown = []
    for item in block["items"]:
        m = CODE_IN_ITEM.match(item)
        if not m:
            hits = names.get(_norm_key(item), [])
            if hits:
                checks["③ 코드 병기"] = X
                codes = ", ".join(f"LM{u.code}" for u in hits[:2])
                notes["③ 코드 병기"].append(f"「{visible(item)}」 — NCS 학습모듈명인데 코드가 없음 (예: {visible(item)}({codes}))")
                shown.append({"항목": item, "판단": "NCS 학습모듈 · 코드 없음"})
                if any(u.base == module_code.replace("LM", "")[:10] for u in hits):
                    checks["③ 코드 유효(NCS 목록)"] = X
                    notes["③ 코드 유효(NCS 목록)"].append(f"「{visible(item)}」 — 이 학습모듈 자신을 선수학습으로 적음")
            else:
                shown.append({"항목": item, "판단": "과목명으로 봄" if cat else "코드 없음(목록 없어 판단 못 함)"})
                if not cat:
                    checks["③ 코드 병기"] = TRI if checks["③ 코드 병기"] == O else checks["③ 코드 병기"]
                    notes["③ 코드 병기"].append(f"「{visible(item)}」 — NCS 목록이 없어 학습모듈명인지 판단 못 함")
            continue
        name, code = m.group("name").strip(), m.group("code")
        entry = {"항목": item, "코드": code}
        if not FULL_CODE.match(code):
            checks["③ 코드 병기"] = X
            notes["③ 코드 병기"].append(f"「{visible(item)}」 — 코드 꼴은 LM + 10자리 + _NNvN (예: LM1201010411_23v5)")
        if code.replace("LM", "")[:10] == module_code.replace("LM", "")[:10]:
            checks["③ 코드 유효(NCS 목록)"] = X
            notes["③ 코드 유효(NCS 목록)"].append(f"「{visible(item)}」 — 이 학습모듈 자신의 코드")
        if cat:
            unit = cat.unit(code)
            if unit is None:
                checks["③ 코드 유효(NCS 목록)"] = X
                notes["③ 코드 유효(NCS 목록)"].append(f"「{visible(item)}」 — NCS 목록에 없는 코드 {code}")
            else:
                entry["NCS"] = f"{unit.name}(LM{unit.code})"
                if f"LM{unit.code}" != (code if code.startswith("LM") else "LM" + code) and "_" in code:
                    notes["③ 코드 유효(NCS 목록)"].append(f"「{visible(item)}」 — 버전이 목록과 다름: 적힌 {code} / 목록 LM{unit.code}")
                    checks["③ 코드 유효(NCS 목록)"] = X
                if not same_name(unit.name, name):
                    checks["③ 명칭 일치(NCS 목록)"] = X
                    notes["③ 명칭 일치(NCS 목록)"].append(f"원고 「{visible(name)}」 / NCS 목록 「{unit.name}」 (코드 {code})")
        shown.append(entry)
    flat = {k: " / ".join(v) for k, v in notes.items() if v}
    if not cat:
        flat.setdefault("③ 코드 유효(NCS 목록)", "NCS 목록(ncs_units.tsv)이 없어 코드·명칭 대조 생략 — scripts/build_ncs_catalog.py")
    return [_row(shown, checks, flat, "NCS 능력단위·학습모듈은 '명칭(LM코드)' 꼴로, 명칭·코드를 NCS 목록과 같게")]


def _row(evidence, checks, notes, suggestion):
    result = verdict(checks)
    return {
        "item_id": ITEM_ID,
        "region_path": REGION,
        "원고": evidence,
        "체크": checks,
        "판정": result,
        "비고": notes,
        "수정 제안": None if result == PASS else suggestion,
    }
