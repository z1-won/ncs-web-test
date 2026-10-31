"""F02 개요 ⑤·⑥: '학습모듈의 내용 체계' 표의 학습명·학습 내용명(⑤), NCS 능력단위 요소 코드·명칭(⑥)이 개발계획서와 일치하는가."""

from ncs_core import NA, O, PASS, PUA, TRI, X, verdict, visible

from ..compare import diff_list
from ..text import same

ITEM_ID_5 = "F02-개요-⑤"
ITEM_ID_6 = "F02-개요-⑥"
REGION = "section0 > 학습모듈의 개요 > 학습모듈의 내용 체계"


def _missing(item_id: str, label: str, note: str) -> dict:
    return {
        "item_id": item_id,
        "region_path": REGION,
        "원고": None,
        "체크": {label: X},
        "판정": verdict({label: X}),
        "비고": {label: note},
        "수정 제안": "학습모듈의 내용 체계 표를 작성할 것",
    }


def check_structure_names(overview: dict, plan: dict | None) -> list[dict]:
    """⑤ 학습명·학습 내용명 ↔ 개발계획서. 차례 면과의 일치는 차례 검수 ③ 결과를 참조한다."""
    structure = overview.get("내용체계")
    label_l, label_c = "⑤ 학습명 개발계획서 일치", "⑤ 학습 내용명 개발계획서 일치"
    if not structure or not structure["학습"]:
        return [_missing(ITEM_ID_5, label_l, "'학습모듈의 내용 체계' 표 또는 학습명을 읽지 못함")]
    lessons = [visible(f"{L['no']}. {L['text']}") for L in structure["학습"]]
    contents = [visible(f"{s['no']}-{s['sub']}. {s['text']}") for s in structure["내용"]]
    notes: dict = {"근거": structure["근거"]}
    pua = [visible(t) for t in [L["text"] for L in structure["학습"]] + [s["text"] for s in structure["내용"]] if PUA.search(t)]
    if pua:
        # 비교는 기호 글꼴 문자를 가운뎃점으로 치환해서 하고, 문자 자체는 차례 ①에서 X로 보고한다.
        notes["기호 글꼴 문자(참고)"] = "가운뎃점이 기호 글꼴 문자 — ·(U+00B7)로 교체 (차례 ①에서 보고): " + "; ".join(pua)
    if not plan:
        checks = {label_l: TRI, label_c: TRI}
        notes[label_l] = notes[label_c] = "개발계획서를 읽지 못해 대조 불가 — 사람 확인"
    else:
        exp_l = plan["학습명"]
        exp_c = [f"{s['no']}-{s['sub']}. {s['text']}" for s in plan["내용명"]]
        if exp_l:
            value, diff = diff_list("학습명", exp_l, [L["text"] for L in structure["학습"]])
            checks = {label_l: value}
            if diff:
                notes[label_l] = "; ".join(diff)
        else:
            checks = {label_l: TRI}
            notes[label_l] = "개발계획서 학습명을 읽지 못함"
        if exp_c:
            value, diff = diff_list("학습 내용명", exp_c, contents)
            checks[label_c] = value
            if diff:
                notes[label_c] = "; ".join(diff)
        else:
            checks[label_c] = TRI
            notes[label_c] = "개발계획서 학습 내용명을 읽지 못함"
    result = verdict(checks)
    return [
        {
            "item_id": ITEM_ID_5,
            "region_path": REGION,
            "원고": {"학습": lessons, "학습 내용": contents},
            "개발계획서": {"학습명": plan["학습명"], "내용명": [f"{s['no']}-{s['sub']}. {s['text']}" for s in plan["내용명"]]} if plan else None,
            "체크": checks,
            "판정": result,
            "비고": notes,
            "수정 제안": None if result == PASS else "개발계획서의 학습명·학습 내용명과 같게 수정 (차례 면도 함께 확인)",
        }
    ]


def check_structure_elements(overview: dict, plan: dict | None, module_code: str) -> list[dict]:
    """⑥ NCS 능력단위 요소 코드 번호·요소 명칭 ↔ 개발계획서."""
    structure = overview.get("내용체계")
    label_set, label_name, label_prefix = "⑥ 요소 코드 번호 개발계획서 일치", "⑥ 요소 명칭 개발계획서 일치", "⑥ 코드 번호가 이 모듈의 능력단위 코드"
    if not structure or not structure["요소"]:
        return [_missing(ITEM_ID_6, label_set, "'학습모듈의 내용 체계' 표에서 요소 코드 번호를 읽지 못함")]
    elements = structure["요소"]
    unit = module_code.replace("LM", "")
    notes: dict = {"근거": structure["근거"]}
    wrong_prefix = [e["code"] for e in elements if not e["code"].startswith(unit + ".")]
    checks = {label_prefix: X if wrong_prefix else O}
    if wrong_prefix:
        notes[label_prefix] = f"능력단위 코드 {unit} 가 아닌 요소 코드: {wrong_prefix}"
    if not plan or not plan["요소"]:
        checks[label_set] = checks[label_name] = TRI
        notes[label_set] = "개발계획서 요소 코드를 읽지 못해 대조 불가 — 사람 확인" if plan else "개발계획서를 읽지 못해 대조 불가 — 사람 확인"
    else:
        exp = {e["code"]: e["name"] for e in plan["요소"]}
        got = {e["code"]: e["name"] for e in elements}
        missing, extra = sorted(exp.keys() - got.keys()), sorted(got.keys() - exp.keys())
        checks[label_set] = O if not missing and not extra else X
        parts = []
        if missing:
            parts.append(f"표에 없는 개발계획서 요소 코드: {missing}")
        if extra:
            parts.append(f"개발계획서에 없는 코드: {extra}")
        if parts:
            notes[label_set] = "; ".join(parts)
        bad = [f'{code}: "{got[code]}" / 기준 "{exp[code]}"' for code in got if code in exp and not same(exp[code], got[code])]
        checks[label_name] = X if bad else (O if got.keys() & exp.keys() else NA)
        if bad:
            notes[label_name] = "요소 명칭 다름 — " + "; ".join(bad)
    result = verdict(checks)
    return [
        {
            "item_id": ITEM_ID_6,
            "region_path": REGION,
            "원고": [{"코드번호": e["code"], "요소 명칭": visible(e["name"])} for e in elements],
            "개발계획서": plan["요소"] if plan else None,
            "체크": checks,
            "판정": result,
            "비고": notes,
            "수정 제안": None if result == PASS else "개발계획서의 능력단위 요소 코드 번호·요소명과 같게 수정",
        }
    ]
