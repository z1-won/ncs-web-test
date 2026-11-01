"""참고 자료 ③: 국문 → 국문 번역 → 영문 → 중문 → 일문 순, 국문은 가나다순·영문은 알파벳순, 동일 저자는 연대순(동일 연도 a/b/c). 1행."""

import re

from ncs_core import O, TRI, X

from .common import row

CHECK = "③ 나열 순서"
GROUP_ORDER = {"국문": 0, "국문 번역": 1, "영문": 2, "중문": 3, "일문": 4, "기타": 5}


def group_of(entry: dict) -> str:
    return "국문 번역" if entry["script"] == "국문" and entry["translated"] else entry["script"]


def sort_key(entry: dict):
    key = entry["key"]
    author = (key["raw_author"] if key else entry["text"]).strip().lower()
    author = re.sub(r"\s+", " ", author)
    return author, (key["year_raw"] if key else "")


def check_order(entries: list[dict]) -> list[dict]:
    if not entries:
        return [row("③", "section1 > 참고 자료", "", None, {CHECK: TRI}, {CHECK: "참고 자료 항목을 찾지 못함"})]
    problems, details = [], []
    # 1) 언어 블록 순서
    groups = [group_of(e) for e in entries]
    for prev, cur in zip(entries, entries[1:]):
        if GROUP_ORDER[group_of(cur)] < GROUP_ORDER[group_of(prev)]:
            problems.append(f"{cur['n']}번({group_of(cur)})이 {prev['n']}번({group_of(prev)}) 뒤에 옴")
            details.append({"n": cur["n"], "문제": f"{group_of(cur)} 자료는 {group_of(prev)} 자료보다 앞에"})
    # 2) 블록 안 정렬: 저자 → 연도
    for name in ("국문", "국문 번역", "영문", "중문", "일문"):
        block = [e for e in entries if group_of(e) == name]
        for prev, cur in zip(block, block[1:]):
            pa, py = sort_key(prev)
            ca, cy = sort_key(cur)
            if ca < pa or (ca == pa and cy < py):
                order = "가나다순" if name.startswith("국문") else "알파벳순"
                problems.append(f"{cur['n']}번 「{ca[:12]}」이 {prev['n']}번 「{pa[:12]}」보다 앞이어야 함({order})")
                details.append({"n": cur["n"], "문제": f"{order} 위반"})
    # 3) 동일 저자·동일 연도 a/b/c
    seen = {}
    for e in entries:
        if not e["key"]:
            continue
        k = (e["key"]["author"], e["key"]["year"])
        seen.setdefault(k, []).append(e)
    for (author, year), same in seen.items():
        if len(same) > 1 and not all(re.search(r"\d{4}[a-z]", s["key"]["year_raw"]) for s in same):
            problems.append(f"{', '.join(str(s['n']) + '번' for s in same)} 동일 저자·동일 연도인데 a/b/c 구분이 없음")
            details.append({"n": same[0]["n"], "문제": "동일 저자 동일 연도 a/b/c 필요"})
    counts = {name: groups.count(name) for name in GROUP_ORDER if groups.count(name)}
    checks = {CHECK: X if problems else O}
    notes = {CHECK: " / ".join(problems[:4]) + (" …" if len(problems) > 4 else "")} if problems else {}
    return [row("③", "section1 > 참고 자료", "", counts, checks, notes, "국문(가나다)→국문 번역→영문(알파벳)→중문→일문 순으로 정렬", 상세=details)]
