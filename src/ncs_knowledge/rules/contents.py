"""F02 필요지식 ④: 본문 학습 내용명(N-M.) = 차례 면 = 내용체계 표, N = 놓인 학습, M 연번."""

from ncs_core import O, PUA, TRI, X, visible
from ncs_toc.compare import diff_list

from .common import row


def check_contents(toc: dict, overview: dict | None, body: dict, units: list[dict]) -> list[dict]:
    rows = []
    for no, a, b in body["spans"]:
        own = [u for u in units if u["lesson"] == no]
        region = f"section1 > 학습 {no} > N-M. 제목"
        actual = [u["text"] for u in own]
        checks, notes = {}, {}
        for name, ref in (
            ("차례 학습 내용명과 일치", [s["text"] for s in toc["내용"] if s["no"] == no]),
            ("내용체계 학습 내용명과 일치", [s["text"] for s in overview["내용"] if s["no"] == no] if overview else None),
        ):
            if ref is None:
                checks[name], notes[name] = TRI, "'학습모듈의 내용체계' 표를 찾지 못함"
                continue
            value, diff = diff_list("학습 내용명", ref, actual)
            checks[name] = value
            if diff:
                notes[name] = " / ".join(diff)
        wrong = [u for u in own if u["no"] != no]
        checks["N-M 의 N = 놓인 학습"] = X if wrong else O
        if wrong:
            notes["N-M 의 N = 놓인 학습"] = f"학습 {no}에 놓였는데 번호가 다름: " + ", ".join(f"{u['no']}-{u['sub']}. {visible(u['text'])}" for u in wrong)
        subs_no = [u["sub"] for u in own]
        checks["M 연번"] = O if subs_no == list(range(1, len(own) + 1)) else X
        if checks["M 연번"] == X:
            notes["M 연번"] = f"본문 순서 {subs_no} — 1부터 연속이어야 함"
        pua = [u["text"] for u in own if PUA.search(u["text"])]
        checks["기호 글꼴 문자 없음"] = X if pua else O
        if pua:
            notes["기호 글꼴 문자 없음"] = "기호 글꼴 문자: " + ", ".join(visible(t) for t in pua)
        rows.append(
            row("④", region, [f"{u['no']}-{u['sub']}. {visible(u['text'])}" for u in own], checks, notes,
                "차례·내용체계 값으로 통일", 기준={"차례": [s["text"] for s in toc["내용"] if s["no"] == no]})
        )
    return rows
