"""hwpx 문단 번호(자동 번호) 복원.

한글의 '문단 번호'는 텍스트에 들어 있지 않다. 문단 → paraPr(heading type=NUMBER, idRef, level) → header.xml의
numbering 정의(수준별 서식 '^1.', '(^2)' 와 숫자/가나다/①… 종류)를 따라, 한글이 화면에 찍는 번호를 그대로 만든다.
같은 numbering id 안에서 연번이고 상위 수준이 올라가면 하위 카운터는 초기화된다. 번호를 '새로 시작'하면 한글은
numbering id를 새로 만들므로 id별 카운터로 충분하다. 글머리표(BULLET)는 글머리 글자를 돌려준다.
"""

import re
import xml.etree.ElementTree as ET

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"

_GA = "가나다라마바사아자차카타파하"
_JAMO = "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ"
_ROMAN = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv")
PLACEHOLDER = re.compile(r"\^(\d)")


def format_number(kind: str, n: int) -> str:
    """numFormat 종류와 서수 n → 글자. 모르는 종류는 숫자로 쓰고 '?'를 붙인다."""
    if n < 1:
        return str(n)
    if kind == "DIGIT":
        return str(n)
    if kind == "HANGUL_SYLLABLE":
        return _GA[n - 1] if n <= len(_GA) else str(n)
    if kind == "HANGUL_JAMO":
        return _JAMO[n - 1] if n <= len(_JAMO) else str(n)
    if kind == "CIRCLED_DIGIT":
        return chr(0x2460 + n - 1) if n <= 20 else str(n)
    if kind == "CIRCLED_HANGUL_JAMO":          # ㉠㉡㉢ …
        return chr(0x3260 + n - 1) if n <= 14 else str(n)
    if kind == "CIRCLED_HANGUL_SYLLABLE":      # ㉮㉯㉰ …
        return chr(0x326E + n - 1) if n <= 14 else str(n)
    if kind == "LATIN_SMALL":
        return chr(ord("a") + n - 1) if n <= 26 else str(n)
    if kind == "LATIN_CAPITAL":
        return chr(ord("A") + n - 1) if n <= 26 else str(n)
    if kind == "CIRCLED_LATIN_SMALL":          # ⓐⓑⓒ …
        return chr(0x24D0 + n - 1) if n <= 26 else str(n)
    if kind == "CIRCLED_LATIN_CAPITAL":        # ⒶⒷⒸ …
        return chr(0x24B6 + n - 1) if n <= 26 else str(n)
    if kind == "ROMAN_SMALL":
        return _ROMAN[n - 1] if n <= len(_ROMAN) else str(n)
    if kind == "ROMAN_CAPITAL":
        return _ROMAN[n - 1].upper() if n <= len(_ROMAN) else str(n)
    return f"{n}?"


def read_definitions(header: ET.Element) -> dict:
    """header.xml → {'headings': {paraPr id: (type, idRef, level)}, 'numberings': {id: {level: (kind, pattern, start)}},
    'bullets': {id: 글자}}."""
    headings = {}
    for para_pr in header.iter(HH + "paraPr"):
        heading = para_pr.find(HH + "heading")
        if heading is not None and heading.get("type") in ("NUMBER", "BULLET"):
            headings[para_pr.get("id")] = (heading.get("type"), heading.get("idRef"), int(heading.get("level", "0")))
    numberings = {}
    for numbering in header.iter(HH + "numbering"):
        numberings[numbering.get("id")] = {
            int(head.get("level")): (head.get("numFormat", "DIGIT"), head.text or "", int(head.get("start", "1") or 1))
            for head in numbering.findall(HH + "paraHead")
        }
    bullets = {bullet.get("id"): bullet.get("char", "") for bullet in header.iter(HH + "bullet")}
    return {"headings": headings, "numberings": numberings, "bullets": bullets}


def render_numbers(para_pr_ids: list[str | None], definitions: dict) -> list[str | None]:
    """문단별 paraPr id 목록(문서 순서) → 문단별 번호 글자('1.', '(가)', '①' …) 또는 글머리 글자, 없으면 None."""
    counters: dict[str, dict[int, int]] = {}
    out: list[str | None] = []
    for para_pr_id in para_pr_ids:
        heading = definitions["headings"].get(para_pr_id)
        if heading is None:
            out.append(None)
            continue
        kind, ref, level = heading
        if kind == "BULLET":
            out.append(definitions["bullets"].get(ref, "") or None)
            continue
        levels = definitions["numberings"].get(ref, {})
        head = levels.get(level + 1)  # paraHead level은 1부터, heading level은 0부터
        if head is None:
            out.append(None)
            continue
        counter = counters.setdefault(ref, {})
        counter[level] = counter.get(level, head[2] - 1) + 1
        for deeper in [k for k in counter if k > level]:
            del counter[deeper]
        def substitute(match):
            k = int(match.group(1))
            number_kind = levels.get(k, ("DIGIT", "", 1))[0]
            return format_number(number_kind, counter.get(k - 1, 0))
        out.append(PLACEHOLDER.sub(substitute, head[1]) or None)
    return out
