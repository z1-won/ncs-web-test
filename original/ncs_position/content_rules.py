"""F02 ①~④. I/O 없이 추출된 문단과 표만 비교한다."""

from .common import PUA, O, X, TRI, NA, RP, LABELS3, norm, same, visible, _verdict
from .tables import column, find_table


def _position_table(lines):
    """'[NCS-학습모듈의 위치]' 이후 처음 나오는 대/중/소분류 라벨의 다음 줄 = 값"""
    pos = {}
    anchor = next(
        (i for i, l in enumerate(lines) if l.startswith("[NCS-학습모듈의 위치]")), 0
    )
    for i in range(anchor, len(lines)):
        l = lines[i]
        if l in LABELS3 and l not in pos and i + 1 < len(lines):
            pos[l] = lines[i + 1]
        if len(pos) == 3:
            break
    return pos


def check_class3(plan_secs, ms_secs):
    P = _position_table([l for sec in plan_secs for l in sec])
    M = _position_table([l for l in ms_secs[0] if l])
    C = []
    for k in LABELS3:
        exp, act = P.get(k, ""), M.get(k, "")
        ok = same(exp, act)
        checks = {
            "① 개발계획서와 명칭 일치": O if ok else X,
            "기호 글꼴 문자 없음": X if PUA.search(act) else O,
        }
        notes = {}
        if not ok:
            notes["① 개발계획서와 명칭 일치"] = (
                f'개발계획서: "{exp}"' if exp else "개발계획서에서 값을 읽지 못함"
            )
        if PUA.search(act):
            notes["기호 글꼴 문자 없음"] = (
                "가운뎃점 등이 기호 글꼴(사용자 정의 영역) 문자 — ·(U+00B7)로 교체"
            )
        C.append(
            {
                "item_id": "F02-위치-①",
                "region_path": f"{RP} > {k}",
                "원고": visible(act),
                "개발계획서": exp,
                "체크": checks,
                "판정": _verdict(checks),
                "비고": notes,
                "수정 제안": None if _verdict(checks) == "반영" else exp,
            }
        )
    return C


def position_tables(tables):
    t1 = find_table(tables, "대분류")
    t2 = find_table(tables, "세분류", after=t1) if t1 else None
    return t1, t2


def extract_position(tables):
    """{'세분류': [...], '능력단위': [...], '학습모듈명': [...], '행쌍': [(능력단위, 학습모듈명), ...]}"""
    t1, t2 = position_tables(tables)
    out = {"세분류": [], "능력단위": [], "학습모듈명": [], "행쌍": []}
    if t2:
        hdr = {
            v: c
            for (r, c), v in t2["cells"].items()
            if v in ("세분류", "능력단위", "학습모듈명")
        }
        col_s, col_u, col_m = (
            hdr.get("세분류", 0),
            hdr.get("능력단위"),
            hdr.get("학습모듈명"),
        )
        out["세분류"] = [v for v in column(t2, col_s) if v != "세분류"]
        if col_u is not None:
            out["능력단위"] = [v for v in column(t2, col_u) if v != "능력단위"]
        if col_m is not None:
            out["학습모듈명"] = [v for v in column(t2, col_m) if v != "학습모듈명"]
        if col_u is not None and col_m is not None:
            for r in sorted({r for (r, c) in t2["cells"] if c in (col_u, col_m)}):
                u, m = t2["cells"].get((r, col_u), ""), t2["cells"].get((r, col_m), "")
                if (u or m) and u != "능력단위" and m != "학습모듈명":
                    out["행쌍"].append((u, m))
    return out


def _list_check(name, exp, act):
    """목록 비교 → (내용 체크값, 순서 체크값, 비고). 내용 = 누락/추가/변경, 순서 = 공통 원소의 순서"""
    if not exp:
        return (
            TRI,
            NA,
            [
                f"{name}: 개발계획서에서 목록을 읽지 못함 — 개발계획서 표 구조 확인(검사 불가)"
            ],
        )
    if not act:
        return (
            X,
            NA,
            [f"{name}: 원고 위치 표에 목록이 비어 있음 (개발계획서 {len(exp)}개)"],
        )
    E, A = [norm(x) for x in exp], [norm(x) for x in act]
    notes = []
    missing = [exp[i] for i, e in enumerate(E) if e not in A]
    extra = [act[j] for j, a in enumerate(A) if a not in E]
    # 같은 자리 바뀜(변경)은 누락+추가가 아니라 '다름' 으로
    if len(E) == len(A) and len(missing) == len(extra):
        pairs = [
            (i, exp[i], act[i])
            for i in range(len(E))
            if E[i] != A[i] and E[i] not in A and A[i] not in E
        ]
        for i, e, a in pairs:
            notes.append(
                f'{name} {i+1}번째 다름: 원고 "{visible(a)}" / 개발계획서 "{e}"'
            )
            missing.remove(e)
            extra.remove(a)
    notes += [f'{name} 누락: "{x}"' for x in missing] + [
        f'{name} 원고에 추가: "{visible(x)}"' for x in extra
    ]
    if len(exp) != len(act):
        notes.insert(0, f"{name} 개수: 원고 {len(act)} / 개발계획서 {len(exp)}")
    content = O if not notes else X
    Ec, Ac = [e for e in E if e in A], [a for a in A if a in E]
    order = O
    if Ec != Ac:
        order = TRI
        notes.append(
            f"{name} 순서 다름: 원고 {[visible(x) for x in act]} / 개발계획서 {exp}"
        )
    return content, order, notes


def check_position(plan_tables, ms_tables):
    """checklist 1건 (②③④). ①은 check_class3, ⑤는 check_emphasis"""
    rp = f"{RP} > 세분류·능력단위 표"
    P, M = extract_position(plan_tables), extract_position(ms_tables)
    show = lambda D: {
        k: [visible(x) for x in D[k]] for k in ("세분류", "능력단위", "학습모듈명")
    }
    if not P["세분류"] and not P["능력단위"]:
        return [
            {
                "item_id": "F02-위치-②③④",
                "region_path": rp,
                "원고": show(M),
                "개발계획서": None,
                "체크": {"개발계획서 위치 표 읽기": TRI},
                "판정": "판단불가",
                "비고": [
                    "개발계획서에서 세분류·능력단위·학습모듈명 표를 찾지 못해 ②③④를 검사하지 못함"
                ],
                "수정 제안": None,
            }
        ]
    if not M["세분류"] and not M["능력단위"]:
        return [
            {
                "item_id": "F02-위치-②③④",
                "region_path": rp,
                "원고": None,
                "개발계획서": None,
                "체크": {"표 존재": X},
                "판정": "미반영",
                "비고": ["세분류·능력단위·학습모듈명 표를 찾지 못함"],
                "수정 제안": None,
            }
        ]
    checks, notes = {}, []
    # ② 세분류: 내용·순서 모두 X (F02 '순서대로 모두 나열')
    c, o, n = _list_check("세분류", P["세분류"], M["세분류"])
    notes += n
    checks["② 세분류 목록·순서 일치"] = X if (c == X or o == TRI) else c
    # ③ 내용, ④ 순서(△)
    order_vals = []
    for key, label in (
        ("능력단위", "③ 능력단위명 목록 일치"),
        ("학습모듈명", "③ 학습모듈명 목록 일치"),
    ):
        c, o, n = _list_check(key, P[key], M[key])
        checks[label] = c
        notes += n
        order_vals.append(o)
    checks["④ 학습모듈 순서 준용"] = (
        TRI if TRI in order_vals else (NA if all(v == NA for v in order_vals) else O)
    )
    if TRI in order_vals:
        notes.append(
            "④ 순서가 개발계획서와 다름 — 능력단위 순서 일부 변경이 허용되므로 의도된 변경인지 사람 확인"
        )
    bad = [(u, m) for u, m in M["행쌍"] if not same(u, m) and (u, m) not in P["행쌍"]]
    checks["④ 능력단위-학습모듈명 행 대응"] = O if not bad else X
    notes += [
        f'행 대응 불일치: 능력단위 "{visible(u)}" ↔ 학습모듈명 "{visible(m)}"'
        for u, m in bad
    ]
    pua = [
        v for k in ("세분류", "능력단위", "학습모듈명") for v in M[k] if PUA.search(v)
    ]
    checks["기호 글꼴 문자 없음"] = X if pua else O
    if pua:
        notes.append(
            "기호 글꼴(사용자 정의 영역) 문자 사용: "
            + ", ".join(visible(v) for v in pua)
        )
    v = _verdict(checks)
    return [
        {
            "item_id": "F02-위치-②③④",
            "region_path": rp,
            "원고": show(M),
            "개발계획서": {k: P[k] for k in ("세분류", "능력단위", "학습모듈명")},
            "체크": checks,
            "판정": v,
            "비고": notes,
            "수정 제안": (
                None
                if v == "반영"
                else {k: P[k] for k in ("세분류", "능력단위", "학습모듈명")}
            ),
        }
    ]
