"""F02 위치 ⑤: 해당 학습모듈 행의 굵게·KoPub돋움체·셀 음영 (v1.1 판정 정책 유지).

주의: 개발계획서 학습모듈명으로 행을 못 찾으면 모듈 코드의 번호를 행 순번으로 쓰는
기존 fallback을 유지한다. 정확성 개선 과제는 docs/REVIEW.md를 참고한다.
"""

from ncs_core import FAIL, O, PASS, Table, TRI, UNDECIDED, verdict, X

from ..patterns import KOPUB_DOTUM, MODULE_CODE_PARTS, RP, TABLE_HEADERS
from ..text import same

ITEM_ID = "F02-위치-⑤"
ITEM_ID_SUB = "F02-위치-⑤-세분류"
REGION = f"{RP} > 세분류·능력단위 표"


def _styled_cells(table: Table) -> dict[tuple[int, int], dict]:
    """셀 텍스트와 서식을 한 사전으로: {(r,c): {'text', 'fill', 'runs'}}"""
    return {
        key: {"text": table["cells"].get(key, ""), **table["styles"].get(key, {"fill": None, "runs": []})}
        for key in table["cells"]
    }


def _is_bold(cell: dict) -> bool:  # 모든 글자 run이 굵게 속성 또는 Bold 글꼴
    return bool(cell["runs"]) and all(r["bold"] or "bold" in (r["font"] or "").lower() for r in cell["runs"])


def _is_kopub_dotum(cell: dict) -> bool:
    return bool(cell["runs"]) and all((r["font"] or "").replace(" ", "").startswith(KOPUB_DOTUM) for r in cell["runs"])


def _fonts(cell: dict) -> list[str]:
    return sorted({f"{r['font']}{'(굵게)' if r['bold'] else ''}" for r in cell["runs"]})


def _column_rows(cells: dict, col: int, header: str) -> list[tuple[int, dict]]:
    """해당 열의 비어 있지 않은 셀을 (행, 셀)로, 헤더 제외."""
    return [(r, v) for (r, c), v in sorted(cells.items()) if c == col and v["text"] and v["text"] != header]


def _unreadable(item_id, check_name, value, result, note, manuscript=None, plan_name=None):
    return {
        "item_id": item_id,
        "region_path": REGION,
        "원고": manuscript,
        "개발계획서": plan_name,
        "체크": {check_name: value},
        "판정": result,
        "비고": {check_name: note},
        "수정 제안": None,
    }


def check_emphasis(table: Table | None, module_code: str, plan_module_name: str | None = None, *, has_styles=True):
    """체크리스트 2건: F02-위치-⑤ (능력단위·학습모듈명 행) + F02-위치-⑤-세분류 (덤)."""
    if not has_styles:
        return [_unreadable(ITEM_ID, "서식 읽기", TRI, UNDECIDED, "hwp(바이너리)는 글꼴·음영을 읽지 않음 — hwpx로 저장해 다시 검사")]
    if table is None:
        return [_unreadable(ITEM_ID, "표 존재", X, FAIL, "세분류·능력단위·학습모듈명 표를 찾지 못함")]

    cells = _styled_cells(table)
    headers = {v["text"]: c for (r, c), v in cells.items() if v["text"] in TABLE_HEADERS}
    subs = _column_rows(cells, headers["세분류"], "세분류")
    units = _column_rows(cells, headers["능력단위"], "능력단위")
    modules = _column_rows(cells, headers["학습모듈명"], "학습모듈명")

    # 해당 행: 모듈 코드 → 세분류 DD번째, 능력단위 EE번째
    parts = MODULE_CODE_PARTS.match(module_code)
    i_sub, i_unit = (int(parts.group(4)) - 1, int(parts.group(5)) - 1) if parts else (None, None)
    # 학습모듈명으로 교차 확인 (개발계획서 값이 있으면 그걸, 없으면 코드만)
    i_name = next(
        (k for k, (r, v) in enumerate(modules) if plan_module_name and same(plan_module_name, v["text"])), None
    )
    index = i_name if i_name is not None else i_unit
    how = (
        f'개발계획서 학습모듈명 "{plan_module_name}" 과 일치하는 행'
        if i_name is not None
        else f'모듈 코드 {module_code} 의 능력단위 번호 {i_unit + 1 if i_unit is not None else "?"}'
    )

    rows = []
    if index is None or index >= len(modules):
        rows.append(
            _unreadable(
                ITEM_ID,
                "해당 행 찾기",
                TRI,
                UNDECIDED,
                f"해당 학습모듈 행을 정하지 못함 ({how}; 표의 학습모듈명 {len(modules)}개)",
                [v["text"] for r, v in modules],
                plan_module_name,
            )
        )
    else:
        rows.append(_emphasis_row(cells, headers, modules, units, index, how, plan_module_name))

    # 덤: 해당 세분류 음영 (F11: "해당 학습모듈이 속하는 세분류에 음영 표시")
    if i_sub is not None and i_sub < len(subs):
        rows.append(_sub_row(subs, i_sub, module_code))
    return rows


def _emphasis_row(cells, headers, modules, units, index, how, plan_module_name):
    row = modules[index][0]
    unit = cells.get((row, headers["능력단위"]))
    module = cells.get((row, headers["학습모듈명"]))
    others = [v for k, (r, v) in enumerate(modules) if k != index] + [v for k, (r, v) in enumerate(units) if k != index]
    other_fills = {v["fill"] for v in others}
    checks, notes = {}, {}
    for label, cell in (("능력단위명", unit), ("학습모듈명", module)):
        if cell is None or not cell["runs"]:
            checks[f"{label} 굵은 글씨"] = checks[f"{label} KoPub돋움체"] = checks[f"{label} 음영"] = X
            notes[f"{label} 굵은 글씨"] = f"{label} 칸이 비어 있음"
            continue
        checks[f"{label} 굵은 글씨"] = O if _is_bold(cell) else X
        if not _is_bold(cell):
            notes[f"{label} 굵은 글씨"] = f"글꼴 {_fonts(cell)} — 굵게 속성도 Bold 글꼴도 아님"
        checks[f"{label} KoPub돋움체"] = O if _is_kopub_dotum(cell) else X
        if not _is_kopub_dotum(cell):
            notes[f"{label} KoPub돋움체"] = f"글꼴 {_fonts(cell)} — KoPub돋움체가 아님"
        if cell["fill"] is None:
            checks[f"{label} 음영"] = X
            notes[f"{label} 음영"] = "셀 음영 없음"
        elif cell["fill"] in other_fills:
            checks[f"{label} 음영"] = X
            notes[f"{label} 음영"] = f'셀 음영 {cell["fill"]} 이 다른 행과 같은 색 — 해당 행만 구별되는 음영이어야 함'
        else:
            checks[f"{label} 음영"] = O
    # 덤: 해당 행만 굵게인가 (다른 행도 굵으면 강조 의미 없음 → 사람 확인)
    bold_others = [v["text"] for v in others if _is_bold(v)]
    checks["해당 행만 굵게"] = TRI if bold_others else O
    if bold_others:
        notes["해당 행만 굵게"] = f"다른 행도 굵은 글씨: {sorted(set(bold_others))[:5]}"
    result = verdict(checks)
    return {
        "item_id": ITEM_ID,
        "region_path": f'{REGION} > {index + 1}행 "{module["text"] if module else ""}"',
        "원고": {
            "능력단위": unit["text"] if unit else None,
            "학습모듈명": module["text"] if module else None,
            "글꼴": _fonts(module) if module else None,
            "음영": module["fill"] if module else None,
            "다른 행 음영": sorted(f or "없음" for f in other_fills),
        },
        "개발계획서": plan_module_name,
        "해당 행 근거": how,
        "체크": checks,
        "판정": result,
        "비고": notes,
        "수정 제안": None if result == PASS else "해당 행 능력단위명·학습모듈명: KoPub돋움체 Bold + 다른 행과 구별되는 셀 음영",
    }


def _sub_row(subs, i_sub, module_code):
    _, cell = subs[i_sub]
    other_fills = {v["fill"] for k, (r, v) in enumerate(subs) if k != i_sub}
    ok = cell["fill"] is not None and cell["fill"] not in other_fills
    checks = {"해당 세분류 음영": O if ok else X}
    notes = {} if ok else {
        "해당 세분류 음영": "세분류 칸 음영 없음" if cell["fill"] is None else f'음영 {cell["fill"]} 이 다른 세분류와 같은 색'
    }
    return {
        "item_id": ITEM_ID_SUB,
        "region_path": f'{REGION} > 세분류 "{cell["text"]}"',
        "원고": {"세분류": cell["text"], "음영": cell["fill"], "다른 세분류 음영": sorted(f or "없음" for f in other_fills)},
        "개발계획서": None,
        "해당 행 근거": f"모듈 코드 {module_code} 의 세분류 번호 {i_sub + 1}",
        "체크": checks,
        "판정": verdict(checks),
        "비고": notes,
        "수정 제안": None if ok else "해당 세분류 칸에 다른 세분류와 구별되는 음영",
    }
