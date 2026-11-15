"""참고 자료 ③: 국문 → 국문 번역 → 영문 → 중문 → 일문 순, 국문은 가나다순·영문은 알파벳순, 동일 저자는 연대순(동일 연도 a/b/c). 1행."""

import re

from ncs_core import O, TRI, X

from ..entries import latin_led_korean
from .common import row

CHECK = "③ 나열 순서"
GROUP_ORDER = {"국문": 0, "국문 번역": 1, "영문": 2, "중문": 3, "일문": 4, "기타": 5}
AUTHOR_END = re.compile(r"[(「『]")  # 연도 괄호가 없는 항목에서 저자가 끝나는 자리(쉼표는 'Kovitz, B.'의 이름이라 자르지 않는다)

# 영문으로 시작하는 국문 자료('AIoT 기술 가이드라인 및 …(2025), 한국…협회')를 어디에 둘지는 체크리스트·F14에 규정이 없고
# 최종본(0405 「SW공학센터(2013.12)」)에도 있다. 판정 원칙(체크리스트에 없지만 최종본에 있는 것은 △)에 따라
# 아래 배치 중 하나로 보면 순서가 맞을 때 △(사람 확인), 어느 배치로도 순서가 틀리면 X.
PLACEMENTS = ("국문 맨 앞", "국문 맨 뒤", "영문 목록")


def group_of(entry: dict) -> str:
    return "국문 번역" if entry["script"] == "국문" and entry["translated"] else entry["script"]


def sort_key(entry: dict):
    key = entry["key"]
    # 연도가 없는 항목('A.M.Davis. 「Software …」')은 문장 전체가 아니라 저자 부분으로 비교한다 — 전체로 비교하면
    # 같은 저자의 두 자료가 제목 기호(「 > a) 때문에 순서 위반으로 나온다(SW제품기획 0405 국외 자료).
    author = (key["raw_author"] if key else AUTHOR_END.split(entry["text"], 1)[0].rstrip(" .")).strip().lower()
    author = re.sub(r"\s+", " ", author)
    return author, (key["year_raw"] if key else "")


def same_author(a: str, b: str) -> bool:
    """같은 저자인가 — 연도 없는 항목은 저자 뒤에 제목이 붙어 읽히므로('a.m.davis. a.m.davis inc') 저자+마침표 앞부분이 같으면 같다."""
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def precedes(cur: tuple[str, str], prev: tuple[str, str]) -> bool:
    """cur가 prev보다 앞에 와야 하는가(=순서 위반). 같은 저자면 연도로만 본다."""
    (ca, cy), (pa, py) = cur, prev
    if same_author(ca, pa):
        return bool(cy and py and cy < py)
    return ca < pa


def _order_problems(entries: list[dict], unsure: list[dict], placement: str | None) -> tuple[list[str], list[dict]]:
    """언어 블록 순서와 블록 안 정렬 위반. unsure 항목은 placement대로 놓았다고 보고 따진다."""
    unsure_ids = {id(e) for e in unsure}

    def group(e):
        if id(e) in unsure_ids and placement == "영문 목록":
            return "영문"
        return group_of(e)

    def key(e):
        if id(e) in unsure_ids and placement == "국문 맨 앞":
            return "", ""
        if id(e) in unsure_ids and placement == "국문 맨 뒤":
            return "􏿿", ""
        return sort_key(e)

    problems, details = [], []
    for prev, cur in zip(entries, entries[1:]):
        if GROUP_ORDER[group(cur)] < GROUP_ORDER[group(prev)]:
            problems.append(f"{cur['n']}번({group(cur)})이 {prev['n']}번({group(prev)}) 뒤에 옴")
            details.append({"n": cur["n"], "문제": f"{group(cur)} 자료는 {group(prev)} 자료보다 앞에"})
    for name in ("국문", "국문 번역", "영문", "중문", "일문"):
        block = [e for e in entries if group(e) == name]
        for prev, cur in zip(block, block[1:]):
            if precedes(key(cur), key(prev)):
                order = "가나다순" if name.startswith("국문") else "알파벳순"
                problems.append(f"{cur['n']}번 「{sort_key(cur)[0][:12]}」이 {prev['n']}번 「{sort_key(prev)[0][:12]}」보다 앞이어야 함({order})")
                details.append({"n": cur["n"], "문제": f"{order} 위반"})
    return problems, details


def check_order(entries: list[dict]) -> list[dict]:
    if not entries:
        return [row("③", "section1 > 참고 자료", "", None, {CHECK: TRI}, {CHECK: "참고 자료 항목을 찾지 못함"})]
    # 1)·2) 언어 블록 순서와 블록 안 정렬(저자 → 연도)
    unsure = [e for e in entries if group_of(e).startswith("국문") and latin_led_korean(e["text"])]
    fits = []
    if unsure:
        tried = {p: _order_problems(entries, unsure, p) for p in PLACEMENTS}
        fits = [p for p, (found, _) in tried.items() if not found]
        problems, details = tried[fits[0] if fits else "영문 목록"]
    else:
        problems, details = _order_problems(entries, [], None)
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
    groups = [group_of(e) for e in entries]
    counts = {name: groups.count(name) for name in GROUP_ORDER if groups.count(name)}
    checks = {CHECK: X if problems else (TRI if unsure else O)}
    notes = {CHECK: " / ".join(problems[:4]) + (" …" if len(problems) > 4 else "")} if problems else {}
    if unsure:
        names = ", ".join(f"{e['n']}번 「{e['text'][:16]}」" for e in unsure)
        if fits:
            where = "·".join(fits)
            to = "으로" if (ord(where[-1]) - 0xAC00) % 28 else "로"  # 받침 있으면 '으로'(목록으로), 없으면 '로'(뒤로)
            if not problems:
                notes[CHECK] = f"영문으로 시작하는 국문 자료 {names}의 자리는 규정이 없음 — {where}{to} 보면 순서가 맞음, 사람 확인"
            notes[CHECK + "(참고)"] = f"영문으로 시작하는 국문 자료 {names} — {where}{to} 보고 순서를 따짐"
        else:
            notes[CHECK + "(참고)"] = (f"영문으로 시작하는 국문 자료 {names} — 국문 맨 앞·국문 맨 뒤·영문 목록(알파벳순) 어느 자리로 보아도 순서가 맞지 않음")
    return [row("③", "section1 > 참고 자료", "", counts, checks, notes, "국문(가나다)→국문 번역→영문(알파벳)→중문→일문 순으로 정렬", 상세=details)]
