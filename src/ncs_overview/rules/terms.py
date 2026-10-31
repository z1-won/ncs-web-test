"""F02 개요 ⑧: '핵심 용어'가 최대 개수(기본 10) 이내의 단어(명사형)인가. 명사형 여부는 휴리스틱으로 △만 낸다."""

from ncs_core import O, PASS, TRI, X, verdict

from ..patterns import TERM_PREDICATE

ITEM_ID = "F02-개요-⑧"


def check_terms(overview: dict, max_items: int, max_length: int) -> list[dict]:
    block = overview.get("핵심 용어")
    label_n, label_form = f"⑧ 핵심 용어 {max_items}개 이내", "⑧ 단어(명사형) 형태"
    notes: dict[str, str] = {}
    if not block or not block["items"]:
        checks = {label_n: X}
        notes[label_n] = "'핵심 용어' 제목 또는 내용을 찾지 못함"
        evidence = None
    else:
        items = block["items"]
        n = len(items)
        checks = {label_n: O if n <= max_items else X}
        if n > max_items:
            notes[label_n] = f"핵심 용어 {n}개 — {max_items}개 이내로 줄일 것"
        suspicious = [t for t in items if TERM_PREDICATE.search(t) or len(t) > max_length or t.endswith(".")]
        checks[label_form] = TRI if suspicious else O
        if suspicious:
            notes[label_form] = "단어(명사형)가 아닐 수 있는 항목 — 사람 확인: " + "; ".join(f'"{t}"' for t in suspicious)
        evidence = {"항목": items, "개수": n, "p": block["p"]}
    result = verdict(checks)
    return [
        {
            "item_id": ITEM_ID,
            "region_path": "section0 > 학습모듈의 개요 > 핵심 용어",
            "원고": evidence,
            "체크": checks,
            "판정": result,
            "비고": notes,
            "수정 제안": None if result == PASS else f"핵심 용어를 {max_items}개 이내의 단어(명사형)로 제시",
        }
    ]
