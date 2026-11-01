"""참고 자료 ①: 본문(내용·표·그림)에 인용한 모든 문헌이 참고 자료에 있는가 — 본문 출처 줄의 저자(연도) ↔ 참고 자료 항목. 1행."""

from ncs_core import NA, O, TRI, X, visible

from .common import row

CHECK = "① 본문 인용 문헌의 참고 자료 수록"


def find_entry(citation: dict, entries: list[dict]):
    """출처의 저자(연도)와 맞는 참고 자료 항목. 저자는 정규화해 앞부분 일치(본문 '3인 외' ↔ 참고 자료 전원), 연도 같음. LM 코드가 있으면 코드로도."""
    key = citation["key"]
    for entry in entries:
        if citation["lm_code"] and citation["lm_code"] in entry["text"]:
            return entry
        ek = entry["key"]
        if key and ek and ek["year"] == key["year"] and (ek["author"].startswith(key["author"]) or key["author"].startswith(ek["author"])) and key["author"]:
            return entry
    return None


def check_coverage(entries: list[dict], citations: list[dict]) -> list[dict]:
    literature = [c for c in citations if c["literature"]]
    if not entries:
        return [row("①", "section1 > 참고 자료", "", {"본문 출처": len(literature)}, {CHECK: X if literature else TRI},
                    {CHECK: "참고 자료 항목을 찾지 못함" + (f" — 본문에 문헌 출처 {len(literature)}건이 있음" if literature else "")}, "참고 자료 작성")]
    if not literature:
        return [row("①", "section1 > 참고 자료", "", {"본문 출처": 0, "참고 자료": len(entries)}, {CHECK: NA},
                    {CHECK: "본문에 문헌 출처(집필진 제작·스크린 숏 제외)가 없어 대조할 것이 없음"})]
    missing, unreadable, details = [], [], []
    for c in literature:
        if c["key"] is None and not c["lm_code"]:
            unreadable.append(c)
            details.append({"문단": c["idx"], "출처": visible(c["text"]), "문제": "저자(연도) 꼴이 아니어서 대조 못 함"})
            continue
        if find_entry(c, entries) is None:
            missing.append(c)
            details.append({"문단": c["idx"], "출처": visible(c["text"]), "문제": "참고 자료에 같은 저자(연도)가 없음"})
    checks = {CHECK: X if missing else TRI if unreadable else O}
    notes = {}
    if missing:
        notes[CHECK] = f"본문 문헌 출처 {len(literature)}건 중 {len(missing)}건이 참고 자료에 없음: " + " / ".join(
            visible(c["text"])[:40] for c in missing[:3]) + (" …" if len(missing) > 3 else "")
    if unreadable:
        notes[CHECK + "(확인)"] = f"{len(unreadable)}건은 저자(연도) 꼴이 아니라 대조하지 못함"
    return [row("①", "section1 > 참고 자료", "", {"본문 출처": len(literature), "참고 자료": len(entries)}, checks, notes,
                "본문에 인용한 문헌을 참고 자료에 추가(저자·연도·코드 일치)", 상세=details)]
