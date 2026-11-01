"""F02 위치 ②③④: 세분류 목록·순서, 능력단위명·학습모듈명 목록, 학습모듈 순서와 행 대응."""

from ncs_core import FAIL, NA, O, PASS, PUA, TRI, UNDECIDED, verdict, visible, X

from ..compare import list_diff, summarize_diff
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
        "비고": {check_name: note},
        "수정 제안": None,
    }


def check_position(plan: dict, manuscript: dict, basis: str = "개발계획서", plan_only: dict | None = None) -> list[dict]:
    """체크리스트 1건(②③④). plan = 기준(NCS 목록 또는 개발계획서, parse_position 꼴), basis = 그 출처 이름.
    plan_only: 기준이 NCS 목록일 때 개발계획서에서 읽은 표 — 목록과 다르면 △로 알린다(계획서 갱신 여부 확인)."""
    if not plan["세분류"] and not plan["능력단위"]:
        return [
            _unreadable(
                f"{basis} 위치 표 읽기",
                TRI,
                UNDECIDED,
                f"{basis}에서 세분류·능력단위·학습모듈명 표를 찾지 못해 ②③④를 검사하지 못함",
                _show(manuscript),
            )
        ]
    if not manuscript["세분류"] and not manuscript["능력단위"]:
        return [_unreadable("표 존재", X, FAIL, "세분류·능력단위·학습모듈명 표를 찾지 못함", None)]

    checks, notes, details = {}, {}, []
    # ② 세분류: 내용·순서 모두 X (F02 '순서대로 모두 나열'). 세분류 목록은 계획서 값을 그대로 썼을 수 있다(pipeline 참고)
    sub_basis = "개발계획서" if plan_only is not None and plan["세분류"] is plan_only["세분류"] else basis
    content, order, found, info = list_diff("세분류", plan["세분류"], manuscript["세분류"], basis=sub_basis)
    details += found
    label = "② 세분류 목록·순서 일치"
    checks[label] = X if (content == X or order == TRI) else content
    if checks[label] != O:
        notes[label] = summarize_diff("세분류", info, basis=sub_basis) or found[0]
    # ③ 내용, ④ 순서(△)
    orders, order_notes = [], []
    for key, label in (("능력단위", "③ 능력단위명 목록 일치"), ("학습모듈명", "③ 학습모듈명 목록 일치")):
        content, order, found, info = list_diff(key, plan[key], manuscript[key], basis=basis)
        checks[label] = content
        details += found
        if content != O:
            notes[label] = summarize_diff(key, info, basis=basis) or found[0]
        orders.append(order)
        if order == TRI:
            order_notes.append(key)
    checks["④ 학습모듈 순서 준용"] = TRI if TRI in orders else (NA if all(o == NA for o in orders) else O)
    if TRI in orders:
        notes["④ 학습모듈 순서 준용"] = f"{'·'.join(order_notes)} 순서가 {basis}과 다름 — 능력단위 순서 일부 변경이 허용되므로 의도된 변경인지 확인"
    bad = [(u, m) for u, m in manuscript["행쌍"] if not same(u, m) and (u, m) not in plan["행쌍"]]
    checks["④ 능력단위-학습모듈명 행 대응"] = O if not bad else X
    if bad:
        notes["④ 능력단위-학습모듈명 행 대응"] = f"행 대응 불일치 {len(bad)}건: " + ", ".join(f'"{visible(u)}"↔"{visible(m)}"' for u, m in bad[:3]) + (" …" if len(bad) > 3 else "")
        details += [f'행 대응 불일치: 능력단위 "{visible(u)}" ↔ 학습모듈명 "{visible(m)}"' for u, m in bad]
    pua = [v for k in TABLE_HEADERS for v in manuscript[k] if PUA.search(v)]
    checks["기호 글꼴 문자 없음"] = X if pua else O
    if pua:
        notes["기호 글꼴 문자 없음"] = "기호 글꼴(사용자 정의 영역) 문자 사용: " + ", ".join(visible(v) for v in pua[:3])
    # 기준이 NCS 목록일 때: 개발계획서가 목록과 다르면 알린다(원고 판정과 별개, 계획서 갱신 여부 확인)
    if plan_only is not None and (plan_only["세분류"] or plan_only["능력단위"]):
        gaps = []
        for key in ("세분류", "능력단위", "학습모듈명"):
            if plan_only[key] and plan[key] is not plan_only[key]:  # 세분류는 계획서 값을 그대로 기준으로 썼으면 대조할 것이 없다
                _, _, _, gap = list_diff(key, plan[key], plan_only[key], basis="NCS 목록")
                text = summarize_diff(key, gap, basis="NCS 목록", where="개발계획서")
                if text:
                    gaps.append(text)
        if gaps:
            checks["개발계획서↔NCS 목록"] = TRI
            notes["개발계획서↔NCS 목록"] = " / ".join(gaps) + " — 개발계획서 갱신 여부 확인"
    advice = []
    if checks["② 세분류 목록·순서 일치"] != O:
        advice.append(f"{sub_basis}의 세분류 {len(plan['세분류'])}개를 순서대로 모두 나열")
    if any(checks[k] != O for k in ("③ 능력단위명 목록 일치", "③ 학습모듈명 목록 일치")):
        advice.append(f"{basis}의 능력단위명·학습모듈명 {len(plan['능력단위'])}개를 모두 나열(원고 열의 누락·다름 참고)")
    if checks["④ 능력단위-학습모듈명 행 대응"] != O:
        advice.append(f"능력단위와 학습모듈명을 {basis}과 같은 행끼리 짝지음")
    if pua:
        advice.append("기호 글꼴 문자를 일반 문자로 교체")
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
            "상세": details,
            "수정 제안": None if result == PASS else " / ".join(advice) or None,
        }
    ]
