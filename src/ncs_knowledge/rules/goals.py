"""F02 필요지식 ⑤: 각 학습 내용의 '학습 목표' = 개발계획서 학습 목표(수행 준거).

판정(정의서 V0.23 REQ-02-002 ① 표준 지침: 수행준거–학습목표 대응은 후보 제시 + 사람 확인, 허용 변경은 '변경 확인' 후보로 구분):
  O  문장이 모두 같음(순서만 다른 것은 같은 것으로 본다)
  X  띄어쓰기·부호·대소문자만 다름(학습목표는 수행준거의 띄어쓰기를 따른다 — F04 2-4), 문장이 빠지거나 계획서에 없는 문장이 있음, 딴 문장
  △  짝은 맞는데 낱말이 바뀜 — 용어·법령 사유의 허용 변경(F04 2-1·2-2)일 수 있어 '변경 확인' 후보로 둔다. 허용 변경인지는 내용 전문가가 판단한다
비교 전에 걷어내는 것은 글머리·계획서 번호 같은 표식만이다.

구조: normalize(문장) → compare_lists(기대 목록, 실제 목록) → check_goals(행 생성). 앞 둘은 ncs_core.goals에 있고
평가 ②(평가 준거의 학습 목표)도 같은 함수를 쓴다.
"""

from ncs_core import O, TRI, X, visible
from ncs_core.goals import compare_kinds, compare_lists, compare_to_pool, describe_kinds, difference, normalize

from .common import row

__all__ = ["check_goals", "compare_lists", "difference", "normalize"]


CHANGE_FIX = "허용 변경(용어·법령 사유)이면 개발계획서와 맞는지 확인하고, 아니면 개발계획서 학습 목표 문장으로 통일"


NCS_NOTE = "개발계획서가 없어 NCS 기준정보(수행준거)와 대조함 — "
NCS_TAIL = " — 개발계획서가 정식 기준이므로 계획서를 함께 올려 확정(기준정보의 띄어쓰기는 NCS 원문과 다를 수 있음)"


def check_goals(plan: dict | None, units: list[dict], ncs_criteria: list[str] | None = None) -> list[dict]:
    """ncs_criteria: 개발계획서가 없을 때 쓰는 그 능력단위의 NCS 수행준거 전부(ncs_core.ncs_catalog.criteria_of). 없으면 대조하지 못한다."""
    rows = []
    pool = [normalize(c) for c in ncs_criteria or []]
    for unit in units:
        key = f"{unit['no']}-{unit['sub']}"
        region = f"section1 > 학습 {unit['lesson']} > {key}. {visible(unit['text'])} > 학습 목표"
        actual = unit["goal"]
        shown = [visible(a) for a in actual]
        if not plan and pool:
            # 계획서가 없으면 받아 둔 NCS 수행준거와 대조한다(사람 작업 2번). 어느 학습 내용에 어느 문장이 가는지는 계획서가 정하므로
            # '수행준거에 있는 문장인가'만 본다. 다르면 △까지만 — 계획서가 정식 기준이고 기준정보의 띄어쓰기는 NCS 원문 확인 전이다
            problems = compare_to_pool([visible(normalize(a)) for a in actual], pool, where="본문 학습 목표")
            check = {"개발계획서 학습 목표 일치": TRI if problems or not actual else O}
            note = {}
            if problems:
                note = {"개발계획서 학습 목표 일치": f"{key} {NCS_NOTE}" + " · ".join(text for _, text in problems) + NCS_TAIL}
            elif not actual:
                note = {"개발계획서 학습 목표 일치": f"{key} 학습 목표 문장을 찾지 못함"}
            rows.append(row("⑤", region, shown, check, note, "개발계획서를 함께 올려 다시 검수" if problems else None))
            continue
        if not plan:
            # 계획서와 대조하는 항목이라 계획서가 없으면 확정할 수 없다 — 해당 없음(-)으로 두면 확인서에서 적합으로 접힌다
            rows.append(row("⑤", region, shown, {"개발계획서 학습 목표 일치": TRI},
                            {"개발계획서 학습 목표 일치": "개발계획서가 없어 학습 목표를 대조하지 못함"}, "개발계획서를 함께 올려 다시 검수"))
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
        problems = compare_kinds([normalize(e) for e in expected], [visible(normalize(a)) for a in actual], where="본문 학습 목표", basis="개발계획서")
        only_wording, note = describe_kinds(problems)
        checks["개발계획서 학습 목표 일치"] = O if not problems else TRI if only_wording else X
        if problems:
            notes["개발계획서 학습 목표 일치"] = f"{key} {note}"
        rows.append(row("⑤", region, shown, checks, notes, CHANGE_FIX if only_wording else "개발계획서 학습 목표 문장으로 통일", 개발계획서=expected))
    return rows
