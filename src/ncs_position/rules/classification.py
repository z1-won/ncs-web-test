"""F02 위치 ①: 대·중·소분류 명칭이 개발계획서와 같은가, 기호 글꼴 문자는 없는가."""

from ncs_core import O, PASS, PUA, verdict, visible, X

from ..patterns import LABELS3, RP
from ..text import same

ITEM_ID = "F02-위치-①"


def check_classification(plan_values: dict[str, str], manuscript_values: dict[str, str]) -> list[dict]:
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
            notes["① 개발계획서와 명칭 일치"] = f'개발계획서: "{expected}"' if expected else "개발계획서에서 값을 읽지 못함"
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
                "수정 제안": None if result == PASS else expected,
            }
        )
    return rows
