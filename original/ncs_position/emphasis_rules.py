"""F02 ⑤의 v1.1 판정 정책. 입력은 이미 추출된 서식 표이다.

주의: 코드 번호를 행 순번으로 사용하는 기존 fallback을 유지한다.
정확성 개선 과제는 docs/REVIEW.md를 참고한다.
"""

import re
from .common import O, X, TRI, same, _verdict


def _is_bold(cell):  # 모든 글자 run 이 굵게 속성 또는 Bold 글꼴
    return bool(cell["runs"]) and all(
        r["bold"] or "bold" in (r["font"] or "").lower() for r in cell["runs"]
    )


def _is_kopub_dotum(cell):
    return bool(cell["runs"]) and all(
        (r["font"] or "").replace(" ", "").startswith("KoPub돋움체")
        for r in cell["runs"]
    )


def _fonts(cell):
    return sorted({f"{r['font']}{'(굵게)' if r['bold'] else ''}" for r in cell["runs"]})


def _find_position_table(tables):
    for t in tables:
        if any(v["text"] == "세분류" for v in t["cells"].values()) and any(
            v["text"] == "학습모듈명" for v in t["cells"].values()
        ):
            return t
    return None


def _col_rows(t, col, header):
    """해당 열의 비어 있지 않은 셀을 (행, 셀) 로, 헤더 제외"""
    return [
        (r, v)
        for (r, c), v in sorted(t["cells"].items())
        if c == col and v["text"] and v["text"] != header
    ]


def check_emphasis(tables, module_code, plan_module_name=None):
    """checklist 2건: F02-위치-⑤ (능력단위·학습모듈명 행) + F02-위치-⑤-세분류 (덤)"""
    RP = "section0 > NCS-학습모듈의 위치 > 세분류·능력단위 표"
    if tables is None:
        return [
            {
                "item_id": "F02-위치-⑤",
                "region_path": RP,
                "원고": None,
                "개발계획서": None,
                "체크": {"서식 읽기": TRI},
                "판정": "판단불가",
                "비고": {
                    "서식 읽기": "hwp(바이너리)는 글꼴·음영을 읽지 않음 — hwpx로 저장해 다시 검사"
                },
                "수정 제안": None,
            }
        ]
    t = _find_position_table(tables)
    if t is None:
        return [
            {
                "item_id": "F02-위치-⑤",
                "region_path": RP,
                "원고": None,
                "개발계획서": None,
                "체크": {"표 존재": X},
                "판정": "미반영",
                "비고": {"표 존재": "세분류·능력단위·학습모듈명 표를 찾지 못함"},
                "수정 제안": None,
            }
        ]

    hdr = {
        v["text"]: c
        for (r, c), v in t["cells"].items()
        if v["text"] in ("세분류", "능력단위", "학습모듈명")
    }
    subs = _col_rows(t, hdr["세분류"], "세분류")
    units = _col_rows(t, hdr["능력단위"], "능력단위")
    mods = _col_rows(t, hdr["학습모듈명"], "학습모듈명")

    # 해당 행: 모듈 코드 → 세분류 DD번째, 능력단위 EE번째
    m = re.match(r"LM(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", module_code)
    i_sub, i_unit = (int(m.group(4)) - 1, int(m.group(5)) - 1) if m else (None, None)
    # 학습모듈명으로 교차 확인 (개발계획서 값이 있으면 그걸, 없으면 코드만)
    i_name = next(
        (
            k
            for k, (r, v) in enumerate(mods)
            if plan_module_name and same(plan_module_name, v["text"])
        ),
        None,
    )
    idx = i_name if i_name is not None else i_unit
    how = (
        f'개발계획서 학습모듈명 "{plan_module_name}" 과 일치하는 행'
        if i_name is not None
        else f'모듈 코드 {module_code} 의 능력단위 번호 {i_unit + 1 if i_unit is not None else "?"}'
    )

    C = []
    if idx is None or idx >= len(mods):
        C.append(
            {
                "item_id": "F02-위치-⑤",
                "region_path": RP,
                "원고": [v["text"] for r, v in mods],
                "개발계획서": plan_module_name,
                "체크": {"해당 행 찾기": TRI},
                "판정": "판단불가",
                "비고": {
                    "해당 행 찾기": f"해당 학습모듈 행을 정하지 못함 ({how}; 표의 학습모듈명 {len(mods)}개)"
                },
                "수정 제안": None,
            }
        )
    else:
        row = mods[idx][0]
        u, mcell = t["cells"].get((row, hdr["능력단위"])), t["cells"].get(
            (row, hdr["학습모듈명"])
        )
        others = [v for k, (r, v) in enumerate(mods) if k != idx] + [
            v for k, (r, v) in enumerate(units) if k != idx
        ]
        other_fills = {v["fill"] for v in others}
        checks, notes = {}, {}
        for label, cell in (("능력단위명", u), ("학습모듈명", mcell)):
            if cell is None or not cell["runs"]:
                checks[f"{label} 굵은 글씨"] = checks[f"{label} KoPub돋움체"] = checks[
                    f"{label} 음영"
                ] = X
                notes[f"{label} 굵은 글씨"] = f"{label} 칸이 비어 있음"
                continue
            checks[f"{label} 굵은 글씨"] = O if _is_bold(cell) else X
            if not _is_bold(cell):
                notes[f"{label} 굵은 글씨"] = (
                    f"글꼴 {_fonts(cell)} — 굵게 속성도 Bold 글꼴도 아님"
                )
            checks[f"{label} KoPub돋움체"] = O if _is_kopub_dotum(cell) else X
            if not _is_kopub_dotum(cell):
                notes[f"{label} KoPub돋움체"] = (
                    f"글꼴 {_fonts(cell)} — KoPub돋움체가 아님"
                )
            if cell["fill"] is None:
                checks[f"{label} 음영"] = X
                notes[f"{label} 음영"] = "셀 음영 없음"
            elif cell["fill"] in other_fills:
                checks[f"{label} 음영"] = X
                notes[f"{label} 음영"] = (
                    f'셀 음영 {cell["fill"]} 이 다른 행과 같은 색 — 해당 행만 구별되는 음영이어야 함'
                )
            else:
                checks[f"{label} 음영"] = O
        # 덤: 해당 행만 굵게인가 (다른 행도 굵으면 강조 의미 없음 → 사람 확인)
        bold_others = [v["text"] for v in others if _is_bold(v)]
        checks["해당 행만 굵게"] = TRI if bold_others else O
        if bold_others:
            notes["해당 행만 굵게"] = (
                f"다른 행도 굵은 글씨: {sorted(set(bold_others))[:5]}"
            )
        v = _verdict(checks)
        C.append(
            {
                "item_id": "F02-위치-⑤",
                "region_path": f'{RP} > {idx + 1}행 "{mcell["text"] if mcell else ""}"',
                "원고": {
                    "능력단위": u["text"] if u else None,
                    "학습모듈명": mcell["text"] if mcell else None,
                    "글꼴": _fonts(mcell) if mcell else None,
                    "음영": mcell["fill"] if mcell else None,
                    "다른 행 음영": sorted(f or "없음" for f in other_fills),
                },
                "개발계획서": plan_module_name,
                "해당 행 근거": how,
                "체크": checks,
                "판정": v,
                "비고": notes,
                "수정 제안": (
                    None
                    if v == "반영"
                    else "해당 행 능력단위명·학습모듈명: KoPub돋움체 Bold + 다른 행과 구별되는 셀 음영"
                ),
            }
        )

    # 덤: 해당 세분류 음영 (F11: "해당 학습모듈이 속하는 세분류에 음영 표시")
    if i_sub is not None and i_sub < len(subs):
        srow, scell = subs[i_sub]
        sfills = {v["fill"] for k, (r, v) in enumerate(subs) if k != i_sub}
        ok = scell["fill"] is not None and scell["fill"] not in sfills
        checks = {"해당 세분류 음영": O if ok else X}
        notes = (
            {}
            if ok
            else {
                "해당 세분류 음영": (
                    "세분류 칸 음영 없음"
                    if scell["fill"] is None
                    else f'음영 {scell["fill"]} 이 다른 세분류와 같은 색'
                )
            }
        )
        C.append(
            {
                "item_id": "F02-위치-⑤-세분류",
                "region_path": f'{RP} > 세분류 "{scell["text"]}"',
                "원고": {
                    "세분류": scell["text"],
                    "음영": scell["fill"],
                    "다른 세분류 음영": sorted(f or "없음" for f in sfills),
                },
                "개발계획서": None,
                "해당 행 근거": f"모듈 코드 {module_code} 의 세분류 번호 {i_sub + 1}",
                "체크": checks,
                "판정": _verdict(checks),
                "비고": notes,
                "수정 제안": (
                    None if ok else "해당 세분류 칸에 다른 세분류와 구별되는 음영"
                ),
            }
        )
    return C


def plan_module_name(sections, module_code):
    lines = [l for sec in sections for l in sec]
    code = module_code.replace("LM", "")
    start = next(
        (
            i
            for i, l in enumerate(lines)
            if l == code and i > 0 and lines[i - 1].startswith("능력단위 코드번호")
        ),
        None,
    )
    if start is None:
        return None
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("NCS (수정 금지)")),
        len(lines),
    )
    block = lines[start:end]
    for i, l in enumerate(block):
        if re.fullmatch(r"(①\s*-\s*b\s*)?학습\s*모듈\s*명", l) and i + 1 < len(block):
            return block[i + 1]
        m = re.match(r"(?:①\s*-\s*b\s*)?학습\s*모듈\s*명\s+(\S.+)$", l)
        if m:
            return m.group(1).strip()
    return None
