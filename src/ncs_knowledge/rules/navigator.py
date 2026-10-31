"""F02 필요지식 ①②③: 내비게이터 학습명 — 코드 번호 삭제 / '~하기' 종결 / 차례 면·내용체계 표 학습명과 일치."""

import re

from ncs_core import O, PUA, TRI, X, visible

from ..text import norm, same
from .common import row

CODE = re.compile(r"(LM\s?)?\d{10}_\d{2}v\d+(\.\d+)?|LM\s?\d{8,10}|\(\s*\d{10}[^)]*\)")  # 능력단위·요소·모듈 코드


def check_navigator(toc: dict, overview: dict | None, body: dict) -> list[dict]:
    rows = []
    runs = body["nav_runs"]
    if not runs:
        for no in ("①", "②", "③"):
            rows.append(row(no, "section1 > 내비게이터", None, {"내비게이터 찾기": TRI}, {"내비게이터 찾기": "'학습 1'…'학습 N' 제목 묶음을 찾지 못함"}))
        return rows
    n_toc = len(toc["학습"])
    if len(runs) != n_toc or any(len(r) != n_toc for r in runs):
        rows.append(
            row("③", "section1 > 내비게이터", f"묶음 {len(runs)}개, 길이 {[len(r) for r in runs]}",
                {"내비게이터 묶음 수·길이": TRI},
                {"내비게이터 묶음 수·길이": f"차례 학습 {n_toc}개 — 묶음 수나 학습 수가 다름(학습 구간이 어긋났을 수 있음)"})
        )
    for index in range(max(len(r) for r in runs)):
        no = index + 1
        texts = [(ri + 1, r[index]["text"]) for ri, r in enumerate(runs) if index < len(r)]
        region = f"section1 > 내비게이터 > 학습 {no} (묶음 {len(texts)}회)"
        first = texts[0][1]
        # ① 코드 번호
        hit = [(ri, t) for ri, t in texts if CODE.search(t)]
        checks = {"코드 번호 없음": X if hit else O}
        notes = {"코드 번호 없음": "코드가 남아 있음: " + " / ".join(f'묶음{ri} "{visible(t)}"' for ri, t in hit[:3])} if hit else {}
        rows.append(row("①", region, visible(first), checks, notes, CODE.sub("", first).strip() if hit else None))
        # ② '~하기'
        bad = [(ri, t) for ri, t in texts if not re.search(r"하기$", t.strip())]
        checks = {"'~하기' 종결": X if bad else O}
        notes = {"'~하기' 종결": "'~하기'로 끝나지 않음: " + " / ".join(f'묶음{ri} "{visible(t)}"' for ri, t in bad[:3])} if bad else {}
        rows.append(row("②", region, visible(first), checks, notes))
        # ③ 차례·내용체계 일치 + 묶음 간 일치 + 기호 글꼴
        checks, notes = {}, {}
        toc_text = toc["학습"][index]["text"] if index < n_toc else None
        ov_text = overview["학습"][index]["text"] if overview and index < len(overview["학습"]) else None
        for name, ref in (("차례 학습명과 일치", toc_text), ("내용체계 학습명과 일치", ov_text)):
            if ref is None:
                checks[name], notes[name] = TRI, "기준 쪽에 이 번호의 학습이 없음"
                continue
            diff = [(ri, t) for ri, t in texts if not same(ref, t)]
            checks[name] = O if not diff else X
            if diff:
                notes[name] = f'기준 "{visible(ref)}" / ' + " / ".join(f'묶음{ri} "{visible(t)}"' for ri, t in diff[:3])
        unique = {norm(t) for _, t in texts}
        checks["묶음 간 일치"] = O if len(unique) == 1 else X
        if len(unique) > 1:
            notes["묶음 간 일치"] = "내비게이터 묶음마다 학습명이 다름: " + " / ".join(sorted(visible(u) for u in unique))
        pua = [t for _, t in texts if PUA.search(t)]
        checks["기호 글꼴 문자 없음"] = X if pua else O
        if pua:
            notes["기호 글꼴 문자 없음"] = f"기호 글꼴 문자: {visible(pua[0])} — ·(U+00B7)로 교체"
        rows.append(
            row("③", region, visible(first), checks, notes,
                norm(toc_text) if toc_text and checks.get("차례 학습명과 일치") == X else None,
                기준={"차례": visible(toc_text) if toc_text else None, "내용체계": visible(ov_text) if ov_text else None})
        )
    return rows
