"""F02 위치 ①: 대·중·소분류 명칭이 개발계획서와 같은가, 기호 글꼴 문자는 없는가."""

from ncs_core.goals import explain_pair
from ncs_core import O, PASS, PUA, TRI, verdict, visible, X

from ..patterns import LABELS3, RP
from ..text import same

ITEM_ID = "F02-위치-①"


def check_classification(plan_values: dict[str, str], manuscript_values: dict[str, str], basis: str = "개발계획서",
                         plan: dict[str, str] | None = None) -> list[dict]:
    """plan_values: 기준값(NCS 목록 또는 개발계획서). basis: 그 출처 이름. plan: 기준이 NCS 목록일 때 개발계획서에서 읽은 값(대조용)."""
    rows = []
    for label in LABELS3:
        expected, actual = plan_values.get(label, ""), manuscript_values.get(label, "")
        ok = same(expected, actual)
        checks = {
            "① 개발계획서와 명칭 일치": O if ok else X,
            "기호 글꼴 문자 없음": X if PUA.search(actual) else O,
        }
        notes = {}
        if not ok:
            notes["① 개발계획서와 명칭 일치"] = (f"{label}: " + explain_pair(expected, visible(actual), "원고", basis)) if expected else f"{basis}에서 값을 읽지 못함"
        if plan is not None and plan.get(label) and not same(expected, plan[label]):
            checks["개발계획서↔NCS 목록"] = TRI
            notes["개발계획서↔NCS 목록"] = f"{label}: " + explain_pair(expected, plan[label], "개발계획서", "NCS 목록") + " — 개발계획서 갱신 여부 확인"
        if PUA.search(actual):
            notes["기호 글꼴 문자 없음"] = "가운뎃점 등이 기호 글꼴(사용자 정의 영역) 문자 — ·(U+00B7)로 교체"
        result = verdict(checks)
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": f"{RP} > {label}",
                "원고": visible(actual),
                "개발계획서": expected,
                "체크": checks,
                "판정": result,
                "비고": notes,
                "수정 제안": None if result == PASS else (f'{basis}대로 "{expected}"로 수정' if not ok else "기호 글꼴 문자를 일반 문자로 교체" if PUA.search(actual) else None),
            }
        )
    return rows
