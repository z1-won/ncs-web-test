"""참고 자료 ②: 항목마다 F14 서지 양식 골격(서지 사항·URL·검색 연월일·마침표 구분)에 맞는가 — 항목당 1행.

본문(그림·표 출처)에서 인용되지 않은 항목은 판정에 넣지 않고 참고 비고로만 적는다 — 참고 자료에는 본문 출처 줄로
드러나지 않는 배경 문헌도 실리므로 미인용을 위반으로 보지 않는다. 구 기관명(한국직업능력개발원)은 △.
"""

import re

from ncs_core import NA, O, TRI, X, visible

from ..templates import hints, match_template
from .common import row
from .coverage import find_entry

CHECK = "② 서지 형식"
CITED = "② 본문 출처 기재(참고)"
AGENCY = "② 기관명"
OLD_AGENCY = re.compile(r"한국직업능력개발원")
SPACE_BEFORE_YEAR = re.compile(r"^[^()]+\s\(")


def check_format(entries: list[dict], citations: list[dict]) -> list[dict]:
    if not entries:
        return [row("②", "section1 > 참고 자료", "", None, {CHECK: TRI}, {CHECK: "참고 자료 항목을 찾지 못함"})]
    cited = {id(e) for c in citations if c["literature"] for e in [find_entry(c, entries)] if e is not None}
    rows = []
    for entry in entries:
        text, script = entry["text"], entry["script"]
        name = match_template(text, script)
        checks, notes = {}, {}
        if name and not (script == "국문" and SPACE_BEFORE_YEAR.match(text)):
            checks[CHECK] = O
            notes["템플릿"] = name
        else:
            checks[CHECK] = X
            why = hints(text, script)
            notes[CHECK] = f"{entry['n']}번 F14 서지 양식과 골격이 다름" + (": " + ", ".join(why) if why else "")
        if OLD_AGENCY.search(text):
            checks[AGENCY], notes[AGENCY] = TRI, f"{entry['n']}번 '한국직업능력개발원' → 현재 명칭 '한국직업능력연구원'인지 확인"
        if id(entry) not in cited:
            checks[CITED] = NA
            notes[CITED] = f"{entry['n']}번은 본문 그림·표 출처에서 인용되지 않음(본문 내용 인용이면 무관)"
        rows.append(row("②", f"section1 > 참고 자료 > {entry['n']}번", f"{entry['n']}번", visible(text), checks, notes,
                        "F14 서지 양식(저자(연도). 『책명』. 출판사. 등)으로 수정하고 본문 출처와 맞춤", 문자=script))
    return rows
