"""F02 차례 ③: 개발계획서를 기준으로 다섯 자리(차례·개요·내비게이터·필요지식·평가)의 명칭을 비교한다.

개발계획서를 못 읽으면 차례를 기준으로 비교하되 △로 둔다.
"""

from ncs_core import O, PASS, PUA, TRI, UNDECIDED, verdict, visible, X

from ..compare import diff_list, pua_note
from ..text import norm, same

ITEM_ID = "F02-차례-③"


def _row(place, region_path, *, manuscript, reference, checks, notes, suggestion):
    result = verdict(checks)
    return {
        "item_id": ITEM_ID,
        "region_path": region_path,
        "자리": place,
        "원고": manuscript,
        "기준": reference,
        "체크": checks,
        "판정": result,
        "비고": notes,
        "수정 제안": None if result == PASS else suggestion,
    }


def _unreadable(place, region_path, check_name, note):
    return {
        "item_id": ITEM_ID,
        "region_path": region_path,
        "자리": place,
        "원고": None,
        "기준": None,
        "체크": {check_name: TRI},
        "판정": UNDECIDED,
        "비고": {check_name: note},
        "수정 제안": None,
    }


def check_toc3(plan, toc, overview, body, eval_tables=None) -> list[dict]:
    rows = []
    use_plan_names = bool(plan and plan["학습명"])
    use_plan_subs = bool(plan and plan["내용명"])
    ref_names = [norm(x) for x in plan["학습명"]] if use_plan_names else [L["text"] for L in toc["학습"]]
    ref_subs = plan["내용명"] if use_plan_subs else toc["내용"]
    ref_sub_texts = [s["text"] for s in ref_subs]
    toc_texts = [L["text"] for L in toc["학습"]] + [s["text"] for s in toc["내용"]]
    toc_pua = {PUA.sub("·", t) for t in toc_texts if PUA.search(t)}
    reference = {
        "학습명": ref_names,
        "학습 내용명": ref_sub_texts,
        "출처": "개발계획서" if use_plan_names and use_plan_subs else "차례" if not use_plan_names and not use_plan_subs else "혼합",
        "학습명 출처": "개발계획서" if use_plan_names else "차례",
        "학습 내용명 출처": "개발계획서" if use_plan_subs else "차례",
    }
    base_note = {}
    if not use_plan_names:
        base_note["기준"] = "개발계획서 학습명을 읽지 못해 차례를 기준으로 비교 (△)"
    if not use_plan_subs:
        base_note["기준(내용명)"] = "개발계획서 학습 내용명을 읽지 못해 차례를 기준으로 비교 (△)"

    def item(place, act_names, act_subs, region_path, extra_checks=None, extra_notes=None):
        checks, notes = {}, dict(base_note)
        if act_names is not None:
            value, found = diff_list("학습명", ref_names, act_names)
            checks["학습명 일치"] = value
            if found:
                notes["학습명 일치"] = " / ".join(found)
            if not use_plan_names and value == O and place != "차례":
                checks["학습명 일치"] = TRI
                notes["학습명 일치"] = "차례와 일치 (개발계획서 미확인)"
        if act_subs is not None:
            value, found = diff_list("학습 내용명", ref_sub_texts, act_subs)
            checks["학습 내용명 일치"] = value
            if found:
                notes["학습 내용명 일치"] = " / ".join(found)
            if not use_plan_subs and value == O and place != "차례":
                checks["학습 내용명 일치"] = TRI
                notes["학습 내용명 일치"] = "차례와 일치 (개발계획서 미확인)"
        value, found = pua_note((act_names or []) + (act_subs or []), toc_pua)
        checks["기호 글꼴 문자 없음"] = value
        if found:
            notes["기호 글꼴 문자 없음"] = " / ".join(found)
        if extra_checks:
            checks.update(extra_checks)
        if extra_notes:
            notes.update(extra_notes)
        rows.append(
            _row(
                place,
                region_path,
                manuscript={
                    "학습명": [visible(x) for x in act_names] if act_names is not None else None,
                    "학습 내용명": [visible(x) for x in act_subs] if act_subs is not None else None,
                },
                reference=reference,
                checks=checks,
                notes=notes,
                suggestion="기준 값으로 통일",
            )
        )

    # 1 차례 — 개발계획서 기준일 때만 의미 있음(차례 기준이면 자기 자신이므로 PUA만)
    if use_plan_names or use_plan_subs:
        item(
            "차례",
            [L["text"] for L in toc["학습"]] if use_plan_names else None,
            [s["text"] for s in toc["내용"]] if use_plan_subs else None,
            "section0 > 차례",
        )
    # 2 개요 내용체계
    if overview:
        item(
            "학습모듈의 개요 > 내용체계",
            [L["text"] for L in overview["학습"]],
            [s["text"] for s in overview["내용"]],
            "section0 > 학습모듈의 개요 > 내용체계 표",
        )
    else:
        rows.append(_unreadable("내용체계", "section0 > 학습모듈의 개요", "표 찾기", "'학습모듈의 내용체계' 표를 찾지 못함"))
    # 3 내비게이터 — 첫 묶음을 비교하고, 나머지 묶음의 차이는 추가 체크로
    if body["nav_runs"]:
        extra_checks, extra_notes = {}, {}
        for r_i, run in enumerate(body["nav_runs"][1:], 2):
            value, found = diff_list("학습명", ref_names, [x["text"] for x in run])
            if value == X:
                key = f"내비게이터 {r_i}번째(학습 {r_i}) 일치"
                extra_checks[key] = X
                extra_notes[key] = " / ".join(found)
        if len(body["nav_runs"]) != len(toc["학습"]):
            extra_checks["내비게이터 반복 횟수"] = TRI
            extra_notes["내비게이터 반복 횟수"] = (
                f"내비게이터 묶음 {len(body['nav_runs'])}개 / 차례 학습 {len(toc['학습'])}개 — 학습 구간이 어긋났을 수 있음"
            )
        item(
            "내비게이터",
            [x["text"] for x in body["nav_runs"][0]],
            None,
            f"section1 > 내비게이터 (학습마다 반복 {len(body['nav_runs'])}회)",
            extra_checks,
            extra_notes,
        )
    else:
        rows.append(_unreadable("내비게이터", "section1 > 내비게이터", "내비게이터 찾기", "'학습 1'…'학습 N' 제목 묶음을 찾지 못함"))
    # 4 필요지식 N-M. 제목 — 학습 구간 안의 것만, (no, sub) 순서로
    body_subs = sorted({(s["no"], s["sub"]): s["text"] for L in body["lessons"] for s in L["subs"]}.items())
    item("필요지식(본문) 학습 내용명", None, [t for _, t in body_subs], "section1 > 본문 N-M. 제목")
    # 5 평가 — 학습마다. 1순위: 표의 '학습 내용' 열(확정). 2순위: 블록 안 짧은 줄 휴리스틱(△)
    rows.append(_evaluation_row(body, ref_subs, ref_sub_texts, eval_tables, use_plan_subs, toc_pua, base_note))
    return rows


def _evaluation_row(body, ref_subs, ref_sub_texts, eval_tables, use_plan_subs, toc_pua, base_note):
    checks, notes, seen = {}, {}, []
    by_table = bool(eval_tables)
    for lesson in body["lessons"]:
        expected = [s["text"] for s in ref_subs if s["no"] == lesson["no"]]
        key = f"학습 {lesson['no']} 평가"
        if by_table:
            start, end = lesson["raw_span"]
            tables = [(kind, values) for paragraph, kind, values in eval_tables if start <= paragraph < end]
            if not tables:
                checks[key] = X
                notes[key] = "학습 구간 안에 평가 준거·평가 방법 표('학습 내용' 열)를 찾지 못함"
                continue
            problems = []
            for kind, values in tables:
                seen += values
                value, found = diff_list(f"{kind} 학습 내용", expected, values)
                if value == X:
                    problems += found
            checks[key] = O if not problems else X
            if problems:
                notes[key] = " / ".join(problems)
            kinds = {kind for kind, _ in tables}
            missing = [k for k in ("평가 준거", "평가 방법") if k not in kinds]
            if missing:
                checks[key] = TRI if checks[key] == O else checks[key]
                notes[key] = (notes.get(key, "") + f" / {', '.join(missing)} 표('학습 내용' 열)를 찾지 못함").strip(" /")
        else:
            if not lesson["eval"]:
                checks[key] = X
                notes[key] = "'평 가' 제목을 찾지 못함"
                continue
            candidates = lesson["eval_cands"]
            seen += candidates
            missing = [e for e in expected if not any(same(e, c) for c in candidates)]
            strange = sorted({c for c in candidates if not any(same(e, c) for e in expected)})
            if missing:
                checks[key] = X
                notes[key] = "평가 표에 없는 학습 내용명: " + ", ".join(f'"{m}"' for m in missing)
            elif strange:
                checks[key] = TRI
                notes[key] = "기준에 없는 짧은 줄(학습 내용명일 수 있음): " + ", ".join(f'"{visible(x)}"' for x in strange[:5])
            else:
                checks[key] = TRI
                notes[key] = "표를 못 읽어 문단 휴리스틱으로 확인 (hwpx 권장)"
    if not body["lessons"]:
        checks["평가 구간 찾기"] = TRI
        notes["평가 구간 찾기"] = "학습 구간을 읽지 못해 평가 표 대조를 수행하지 못함"
    if not use_plan_subs:
        checks["개발계획서 기준 확인"] = TRI
        notes["개발계획서 기준 확인"] = "개발계획서 학습 내용명을 읽지 못해 차례를 기준으로 비교"
    value, found = pua_note(seen, toc_pua)
    checks["기호 글꼴 문자 없음"] = value
    all_notes = dict(base_note)
    all_notes.update(notes)
    if found:
        all_notes["기호 글꼴 문자 없음"] = " / ".join(found)
    return _row(
        "평가",
        "section1 > 평가 (평가 준거·평가 방법 표)",
        manuscript={
            "평가 표 학습 내용" if by_table else "학습 내용명 후보": sorted(set(seen)),
            "읽기": "표 셀" if by_table else "문단 휴리스틱",
        },
        reference={"학습 내용명": ref_sub_texts, "출처": "개발계획서" if use_plan_subs else "차례"},
        checks=checks,
        notes=all_notes,
        suggestion="평가 준거·평가 방법 표의 학습 내용명을 기준 값으로 통일",
    )
