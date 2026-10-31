"""F02 위치 ②③④: 세분류 목록·순서, 능력단위명·학습모듈명 목록, 학습모듈 순서와 행 대응."""

from ncs_core import FAIL, NA, O, PASS, PUA, TRI, UNDECIDED, verdict, visible, X

from ..compare import list_check
from ..patterns import RP, TABLE_HEADERS
from ..text import same

ITEM_ID = "F02-위치-②③④"
REGION = f"{RP} > 세분류·능력단위 표"


def _show(position: dict) -> dict:
    return {k: [visible(x) for x in position[k]] for k in TABLE_HEADERS}


def _unreadable(check_name, value, result, note, manuscript):
    return {
        "item_id": ITEM_ID,
        "region_path": REGION,
        "원고": manuscript,
        "개발계획서": None,
        "체크": {check_name: value},
        "판정": result,
        "비고": [note],
        "수정 제안": None,
    }


def check_position(plan: dict, manuscript: dict) -> list[dict]:
    """체크리스트 1건(②③④). plan/manuscript는 parsers.parse_position의 결과."""
    if not plan["세분류"] and not plan["능력단위"]:
        return [
            _unreadable(
                "개발계획서 위치 표 읽기",
                TRI,
                UNDECIDED,
                "개발계획서에서 세분류·능력단위·학습모듈명 표를 찾지 못해 ②③④를 검사하지 못함",
                _show(manuscript),
            )
        ]
    if not manuscript["세분류"] and not manuscript["능력단위"]:
        return [_unreadable("표 존재", X, FAIL, "세분류·능력단위·학습모듈명 표를 찾지 못함", None)]

    checks, notes = {}, []
    # ② 세분류: 내용·순서 모두 X (F02 '순서대로 모두 나열')
    content, order, found = list_check("세분류", plan["세분류"], manuscript["세분류"])
    notes += found
    checks["② 세분류 목록·순서 일치"] = X if (content == X or order == TRI) else content
    # ③ 내용, ④ 순서(△)
    orders = []
    for key, label in (("능력단위", "③ 능력단위명 목록 일치"), ("학습모듈명", "③ 학습모듈명 목록 일치")):
        content, order, found = list_check(key, plan[key], manuscript[key])
        checks[label] = content
        notes += found
        orders.append(order)
    checks["④ 학습모듈 순서 준용"] = TRI if TRI in orders else (NA if all(o == NA for o in orders) else O)
    if TRI in orders:
        notes.append("④ 순서가 개발계획서와 다름 — 능력단위 순서 일부 변경이 허용되므로 의도된 변경인지 사람 확인")
    bad = [(u, m) for u, m in manuscript["행쌍"] if not same(u, m) and (u, m) not in plan["행쌍"]]
    checks["④ 능력단위-학습모듈명 행 대응"] = O if not bad else X
    notes += [f'행 대응 불일치: 능력단위 "{visible(u)}" ↔ 학습모듈명 "{visible(m)}"' for u, m in bad]
    pua = [v for k in TABLE_HEADERS for v in manuscript[k] if PUA.search(v)]
    checks["기호 글꼴 문자 없음"] = X if pua else O
    if pua:
        notes.append("기호 글꼴(사용자 정의 영역) 문자 사용: " + ", ".join(visible(v) for v in pua))
    result = verdict(checks)
    reference = {k: plan[k] for k in TABLE_HEADERS}
    return [
        {
            "item_id": ITEM_ID,
            "region_path": REGION,
            "원고": _show(manuscript),
            "개발계획서": reference,
            "체크": checks,
            "판정": result,
            "비고": notes,
            "수정 제안": None if result == PASS else reference,
        }
    ]
