"""평가 ②: '평가 준거'의 학습 목표 = 개발계획서 학습 목표(NCS 수행 준거). 학습 내용당 1행, 동일 여부만(O/X).

비교 함수는 필요 지식 ⑤와 같은 ncs_core.goals.compare_lists다. 학습 내용명은 평가 준거 표의 '학습 내용' 셀을
계획서의 같은 학습(N) 안 학습 내용명과 이름으로 맞춘다(번호가 셀에 없으므로).
"""

import re

from ncs_core import NA, O, TRI, X, verdict, visible
from ncs_core.goals import compare_lists, normalize

ITEM_ID = "F02-평가-②"
CHECK = "② 평가 준거 학습 목표 계획서 일치"


def _row(lesson: int, region: str, source, checks: dict, notes: dict, suggestion=None, **extra) -> dict:
    result = verdict(checks)
    out = {"item_id": ITEM_ID, "region_path": region, "위치": f"학습 {lesson}", "원고": source, "체크": checks,
           "판정": result, "비고": notes, "수정 제안": suggestion if result != "적합" else None}
    out.update(extra)
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def check_criteria_goals(regions: list[dict], plan_goals: dict | None) -> list[dict]:
    rows = []
    for region in regions:
        lesson = region["lesson"]
        base = f"section1 > 학습 {lesson} > 평가 > 평가 준거"
        if not region["found"]:
            rows.append(_row(lesson, base, None, {CHECK: TRI}, {CHECK: "; ".join(region["notes"]) or "평가 구역을 찾지 못함"}))
            continue
        if not region["criteria"]:
            rows.append(_row(lesson, base, None, {CHECK: X}, {CHECK: "평가 준거 표(학습 내용 | 학습 목표)를 찾지 못함"}, "평가 준거 표 작성"))
            continue
        if plan_goals is None:
            for units in region["criteria"]:
                for unit in units:
                    rows.append(_row(lesson, f"{base} > {unit['name']}", [visible(g) for g in unit["goals"]],
                                     {CHECK: NA}, {CHECK: "개발계획서를 읽지 못해 대조 생략"}))
            continue
        own = {key: value for key, value in plan_goals["내용"].items() if key[0] == lesson}
        by_name = {}
        for key, value in own.items():
            by_name.setdefault(_clean(value["text"]), []).append(key)
        for units in region["criteria"]:
            for unit in units:
                region_path = f"{base} > {unit['name']}"
                shown = [visible(g) for g in unit["goals"]]
                keys = by_name.get(_clean(unit["name"]), [])
                if len(keys) != 1:
                    note = (f"계획서 학습 {lesson}에 같은 이름의 학습 내용이 없음 (계획서: {[v['text'] for v in own.values()]})" if not keys
                            else "계획서에 같은 이름의 학습 내용이 여러 개라 연결하지 못함")
                    rows.append(_row(lesson, region_path, shown, {CHECK: X if not keys else TRI}, {CHECK: note},
                                     "학습 내용명을 개발계획서와 같게 한 뒤 학습 목표 대조"))
                    continue
                expected = own[keys[0]]["goals"]
                problems = compare_lists([normalize(e) for e in expected], [visible(normalize(a)) for a in unit["goals"]])
                checks = {CHECK: X if problems else O}
                notes = {CHECK: f"{keys[0][0]}-{keys[0][1]} " + " · ".join(problems)} if problems else {}
                rows.append(_row(lesson, region_path, shown, checks, notes, "개발계획서 학습 목표 문장으로 통일", 개발계획서=expected))
    return rows
