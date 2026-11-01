"""F02 필요지식 ⑤: 각 학습 내용의 '학습 목표' = 개발계획서 학습 목표(수행 준거).

판정은 동일 여부만 본다(O/X). 띄어쓰기·대소문자·부호 차이도 모두 X이고, 윤문(△)은 없다.
문장 순서만 다른 것은 같은 것으로 본다(집합 비교). 비교 전에 걷어내는 것은 글머리·계획서 번호 같은 표식만이다.

구조: normalize(문장) → compare_lists(기대 목록, 실제 목록) → check_goals(행 생성). 앞 둘은 ncs_core.goals에 있고
평가 ②(평가 준거의 학습 목표)도 같은 함수를 쓴다.
"""

from ncs_core import NA, O, X, visible
from ncs_core.goals import compare_lists, difference, normalize

from .common import row

__all__ = ["check_goals", "compare_lists", "difference", "normalize"]


def check_goals(plan: dict | None, units: list[dict]) -> list[dict]:
    rows = []
    for unit in units:
        key = f"{unit['no']}-{unit['sub']}"
        region = f"section1 > 학습 {unit['lesson']} > {key}. {visible(unit['text'])} > 학습 목표"
        actual = unit["goal"]
        shown = [visible(a) for a in actual]
        if not plan:
            rows.append(row("⑤", region, shown, {"개발계획서 학습 목표 일치": NA}, {"개발계획서": "개발계획서를 읽지 못해 대조 생략"}))
            continue
        checks, notes = {}, {}
        if unit["goal_k"] is None:
            checks["학습 목표 블록"], notes["학습 목표 블록"] = X, f"{key} 제목 아래 '학습 목표' 줄을 찾지 못함"
        expected_unit = plan["내용"].get((unit["no"], unit["sub"]))
        if expected_unit is None:
            checks["개발계획서 학습 목표 일치"] = X
            notes["개발계획서 학습 목표 일치"] = f"{key} 개발계획서에 없음 (계획서 목록: {sorted(plan['내용'])})"
            rows.append(row("⑤", region, shown, checks, notes))
            continue
        expected = expected_unit["goals"]
        problems = compare_lists([normalize(e) for e in expected], [visible(normalize(a)) for a in actual])
        checks["개발계획서 학습 목표 일치"] = X if problems else O
        if problems:
            notes["개발계획서 학습 목표 일치"] = f"{key} " + " · ".join(problems)
        rows.append(row("⑤", region, shown, checks, notes, "개발계획서 학습 목표 문장으로 통일", 개발계획서=expected))
    return rows
