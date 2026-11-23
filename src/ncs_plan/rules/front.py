"""1~3쪽 규칙 — ① NCS 목록 대조(+ 모듈 표의 NCS 쪽을 기준정보와 대조), ② 학습모듈 코드·명칭, ⑧ 필수 기재, ⑨ 변경 전후 대조표."""

from ncs_core import NA, O, TRI, X
from ncs_core.ncs_catalog import Catalog

from ..parsers import LM_CODE, UNIT_CODE, squash
from ..patterns import IMPROVE_TYPES, PLACEHOLDER
from .common import DOTS, pair, row, same_loose, same_text

REGION = "개발계획서"


def _no_table(no: str, name: str, suggestion: str) -> dict:
    checks = {f"{no} {name}": TRI}
    return row(no, REGION, "", None, checks, {f"{no} {name}": f"{name} 표를 읽지 못해 판단할 수 없음"}, suggestion)


# ── ① NCS 목록 대조 ─────────────────────────────────────────────────────────────

def check_catalog(plan: dict, catalog: Catalog | None) -> list[dict]:
    summary = plan.get("총괄표") or []
    position = plan.get("위치") or {}
    basic = plan.get("기본") or {}
    label_unit, label_class = "① 능력단위 코드·명칭", "① 분류 명칭"
    if not summary:
        return [_no_table("①", "총괄표", "총괄표에 능력단위번호·능력단위명을 기재할 것")]
    if catalog is None:
        checks = {label_unit: TRI, label_class: TRI}
        note = "NCS 목록 파일이 없어 대조하지 못함(ncs_units.tsv)"
        return [row("①", f"{REGION} > 총괄표", "", None, checks, {label_unit: note, label_class: note})]
    rows = []
    for entry in summary:
        code = entry["코드"]
        checks, notes = {}, {}
        if not UNIT_CODE.match(code):
            checks[label_unit] = X
            notes[label_unit] = f"능력단위번호 「{code}」 꼴이 아님(숫자 10자리_연도v버전)"
        else:
            unit = catalog.unit(code)
            level_row = catalog.level_row(code)
            name_in_list = unit.name if unit else (level_row["name"] if level_row else None)
            code_in_list = unit.code if unit else (level_row["code"] if level_row else None)
            if code_in_list is None:
                checks[label_unit] = TRI
                notes[label_unit] = f"NCS 목록에 없는 능력단위 「{code}」 — 목록 갱신 전 신규인지 확인"
            elif code_in_list != code:
                checks[label_unit] = X
                notes[label_unit] = f"총괄표 「{code}」, NCS 목록 「{code_in_list}」 (버전이 다름)"
            elif not same_loose(name_in_list, entry["명칭"]):
                checks[label_unit] = X
                notes[label_unit] = pair(name_in_list, entry["명칭"], "총괄표", "NCS 목록")
            else:
                checks[label_unit] = O
        rows.append(row("①", f"{REGION} > 총괄표", code, f"{code} {entry['명칭']}", checks, notes,
                        "총괄표의 능력단위번호·능력단위명을 NCS 목록과 같게 적을 것" if checks[label_unit] == X else None))
    first = next((e["코드"] for e in summary if UNIT_CODE.match(e["코드"])), None)
    subclass = catalog.subclass(first) if first else None
    checks, notes = {}, {}
    if subclass is None:
        checks[label_class] = TRI
        notes[label_class] = "NCS 목록에서 세분류를 찾지 못해 대·중·소·세분류 명칭을 대조하지 못함"
    else:
        wrong = []
        for label in ("대분류", "중분류", "소분류"):
            if position.get(label) and not same_loose(subclass.names[label], position[label]):
                wrong.append(pair(subclass.names[label], position[label], f"위치 표 {label}", "NCS 목록"))
        if basic.get("세분류명") and not same_loose(subclass.name, basic["세분류명"]):
            wrong.append(pair(subclass.name, basic["세분류명"], "세분류명", "NCS 목록"))
        if position.get("세분류") and not any(same_loose(subclass.name, s) for s in position["세분류"]):
            wrong.append(f"위치 표 세분류 목록에 이 세분류 「{subclass.name}」가 없음")
        checks[label_class] = X if wrong else O
        if wrong:
            notes[label_class] = "\n".join(wrong)
    rows.append(row("①", f"{REGION} > 위치", "", None, checks, notes, "분류 명칭을 NCS 목록과 같게 적을 것" if checks[label_class] == X else None))
    return rows


# ── ① NCS 기준정보 대조(모듈 표의 NCS 수정 금지 쪽) ──────────────────────────────

def _spaced(text: str | None) -> str:
    """띄어쓰기를 견주는 꼴 — 가운뎃점은 꼴과 앞뒤 공백을 하나로 맞춘다(글꼴·입력 차이는 띄어쓰기 차이가 아니다. ④와 같은 기준)."""
    import re

    return " ".join(re.sub(r"\s*·\s*", "·", DOTS.sub("·", text or "")).split())


def _text_kind(reference: str | None, written: str | None) -> str:
    """'같음' / '띄어쓰기' / '다름'."""
    a, b = _spaced(reference), _spaced(written)
    return "같음" if a == b else "띄어쓰기" if a.replace(" ", "") == b.replace(" ", "") else "다름"


def check_ncs_text(plan: dict, catalog) -> list[dict]:
    """모듈 표의 NCS 쪽(능력단위 정의·능력단위요소·수행준거)이 받아 둔 NCS 기준정보(ncs_elements.tsv)와 같은가 — 사람 작업 2번 'NCS 기준정보 확인'.
    이 칸들은 고치는 칸이 아니므로 글자가 다르거나 빠진 것은 X. 띄어쓰기만 다른 것은 △ — 기준정보(NCS API)와 NCS 원문 파일(F22)의
    띄어쓰기가 다른 사례가 있어 어느 쪽이 맞는지 원문으로 확인해야 한다. 기준정보를 받아 두지 않은 능력단위는 대조하지 못했다고 한 줄로 알린다(△).
    능력단위번호(버전 포함)가 같은 기준정보하고만 대조한다 — 버전이 다르면 앞의 '① 능력단위 코드·명칭'이 알린다."""
    modules = plan.get("모듈") or []
    if catalog is None or not modules:
        return []
    label_def, label_set, label_name, label_crit, label_space = "① 능력단위 정의", "① 능력단위요소 구성", "① 능력단위요소명", "① 수행준거", "① NCS 표기 띄어쓰기"
    rows, unknown = [], []
    for module in modules:
        code = module.get("코드") or ""
        detail = catalog.unit_detail(code) if UNIT_CODE.match(code) else None
        if detail is None or detail.get("code") != code:
            unknown.append(code or "(코드 없음)")
            continue
        checks, notes, spacing = {}, {}, []

        def judge(label: str, where: str, reference: str, written: str, wrong: list) -> None:
            kind = _text_kind(reference, written)
            if kind == "다름":
                wrong.append(f"{where}: " + pair(reference, written, "계획서", "NCS 기준정보"))
            elif kind == "띄어쓰기":
                spacing.append(f"{where}: 계획서 「{_spaced(written)}」, NCS 기준정보 「{_spaced(reference)}」")

        wrong = []
        if module.get("정의") or detail.get("definition"):
            judge(label_def, "정의", detail.get("definition") or "", module.get("정의") or "", wrong)
            checks[label_def] = X if wrong else O
            if wrong:
                notes[label_def] = "\n".join(wrong)
        reference = {e["code"]: e for e in detail.get("elements") or []}
        written = {e["코드"]: e for e in module.get("요소") or []}
        missing, extra = [c for c in reference if c not in written], [c for c in written if c not in reference]
        checks[label_set] = X if missing or extra else O
        if missing or extra:
            notes[label_set] = " / ".join(part for part in ("NCS에 있는데 계획서에 없는 요소: " + ", ".join(f"{c} {reference[c]['name']}" for c in missing) if missing else "",
                                                            "NCS에 없는 요소: " + ", ".join(extra) if extra else "") if part)
        wrong_names, wrong_criteria = [], []
        for element_code, ref in reference.items():
            mine = written.get(element_code)
            if mine is None:
                continue
            judge(label_name, element_code, ref["name"], mine.get("명칭") or "", wrong_names)
            left = list(ref.get("criteria") or [])
            right = list(mine.get("수행준거") or [])
            for text in list(left):          # 글자가 같은 것(띄어쓰기는 달라도)끼리 먼저 짝짓는다
                twin = next((other for other in right if _text_kind(text, other) != "다름"), None)
                if twin is not None:
                    left.remove(text)
                    right.remove(twin)
                    judge(label_crit, element_code, text, twin, wrong_criteria)
            for text in list(left):          # 남은 것은 번호(1.1 …)가 같은 것끼리 — 글자가 달라진 수행준거
                number = text.split(" ", 1)[0]
                twin = next((other for other in right if other.split(" ", 1)[0] == number), None)
                if twin is not None:
                    left.remove(text)
                    right.remove(twin)
                    judge(label_crit, element_code, text, twin, wrong_criteria)
            wrong_criteria.extend(f"{element_code}: NCS 수행준거가 계획서에서 빠짐 「{text}」" for text in left)
            wrong_criteria.extend(f"{element_code}: NCS에 없는 수행준거 「{text}」" for text in right)
        checks[label_name] = X if wrong_names else O
        checks[label_crit] = X if wrong_criteria else O
        if wrong_names:
            notes[label_name] = "\n".join(wrong_names)
        if wrong_criteria:
            notes[label_crit] = "\n".join(wrong_criteria)
        if spacing:
            checks[label_space] = TRI
            more = f" 외 {len(spacing) - 3}곳" if len(spacing) > 3 else ""
            notes[label_space] = (f"NCS 기준정보와 띄어쓰기만 다른 곳 {len(spacing)}곳 — NCS 원문(F22)의 띄어쓰기를 확인\n" + "\n".join(spacing[:3]) + more)
        bad = any(value == X for value in checks.values())
        rows.append(row("①", f"{REGION} > 모듈 표", code, f"{code} {module.get('명칭') or ''}".strip(), checks, notes,
                        "NCS(수정 금지) 쪽의 정의·능력단위요소·수행준거를 NCS와 같게 되돌릴 것" if bad else None))
    if unknown:
        label = "① NCS 기준정보"
        shown = ", ".join(unknown[:5]) + (f" 외 {len(unknown) - 5}개" if len(unknown) > 5 else "")
        rows.append(row("①", f"{REGION} > 모듈 표", "", None, {label: TRI},
                        {label: f"능력단위 {len(unknown)}개는 같은 번호의 NCS 기준정보(요소·수행준거)를 받아 두지 않아 대조하지 못함: {shown}"}))
    return rows


# ── ② 학습모듈 코드·명칭 ─────────────────────────────────────────────────────────

DRAFT_NOTE = "1차 문서 — 최종 단계에서 개발기관이 기재"


def check_identity(plan: dict, *, draft: bool = False) -> list[dict]:
    summary = plan.get("총괄표") or []
    position = plan.get("위치") or {}
    modules = plan.get("모듈") or []
    label_code, label_name, label_cross = "② LM 코드", "② 학습모듈명 = 능력단위명", "② 표 간 일치"
    if not summary:
        return [_no_table("②", "총괄표", "총괄표를 작성할 것")]
    rows = []
    module_by_code = {m["코드"]: m for m in modules}
    position_pairs = {(squash(p["능력단위"]), squash(p["학습모듈명"])) for p in position.get("모듈", [])}
    for entry in summary:
        code, checks, notes = entry["코드"], {}, {}
        expected_lm = f"LM{code}"
        if not LM_CODE.match(entry["LM 코드"]):
            checks[label_code] = X
            notes[label_code] = f"NCS학습모듈 코드 「{entry['LM 코드']}」 꼴이 아님(LM+능력단위번호)"
        elif entry["LM 코드"] != expected_lm:
            checks[label_code] = X
            notes[label_code] = f"총괄표 「{entry['LM 코드']}」, 능력단위번호로 만든 코드 「{expected_lm}」"
        else:
            checks[label_code] = O
        if same_loose(entry["명칭"], entry["LM 명칭"]):
            checks[label_name] = O
        elif draft and not entry["LM 명칭"]:
            checks[label_name] = NA
            notes[label_name] = DRAFT_NOTE
        else:
            checks[label_name] = X if not same_text(entry["명칭"], entry["LM 명칭"]) else O
            notes[label_name] = pair(entry["명칭"], entry["LM 명칭"], "총괄표 학습모듈명", "능력단위명")
        cross = []
        # 1차 문서: 위치 표의 학습모듈명은 추후 기관에서 기재한다(F21 3쪽) — 비어 있어도 된다
        if position_pairs and not any(same_loose(entry["명칭"], u) and (same_loose(entry["LM 명칭"], m) or (draft and not m))
                                      for u, m in position_pairs):
            if any(same_loose(entry["명칭"], u) and not m for u, m in position_pairs):
                cross.append(f"위치 표의 「{entry['명칭']}」 학습모듈명이 비어 있음 — 개발기관이 기재할 것")
            else:
                cross.append(f"위치 표에 「{entry['명칭']} / {entry['LM 명칭']}」 짝이 없음")
        module = module_by_code.get(code)
        if module is None:
            cross.append(f"모듈 표(NCS 수정 금지)에 능력단위 「{code}」 표가 없음")
        else:
            if not same_loose(module["명칭"], entry["명칭"]):
                cross.append(pair(entry["명칭"], module["명칭"], "모듈 표 능력단위명", "총괄표"))
            if not same_loose(module["학습모듈명"], entry["LM 명칭"]) and not (draft and not entry["LM 명칭"]):
                cross.append(pair(entry["LM 명칭"], module["학습모듈명"], "모듈 표 학습모듈명", "총괄표"))
        checks[label_cross] = X if cross else O
        if cross:
            notes[label_cross] = "\n".join(cross)
        rows.append(row("②", f"{REGION} > 총괄표", code, f"{entry['LM 코드']} {entry['LM 명칭']}", checks, notes,
                        "학습모듈 코드는 'LM'+능력단위번호, 학습모듈명은 능력단위명과 같게 세 표에 통일할 것" if X in checks.values() else None))
    extra = [m["코드"] for m in modules if m["코드"] and m["코드"] not in {e["코드"] for e in summary}]
    if extra:
        rows.append(row("②", f"{REGION} > 모듈 표", "", None, {label_cross: X},
                        {label_cross: "총괄표에 없는 능력단위의 모듈 표가 있음: " + ", ".join(extra)}, "총괄표와 모듈 표의 능력단위를 맞출 것"))
    return rows


# ── ⑧ 필수 기재 ─────────────────────────────────────────────────────────────────

DRAFT_OPTIONAL = ("영문 세분류명", "개발기관명")   # 1차 문서에서 비어 있어도 되는 기본 정보 칸(세분류명·신규/개선은 1차에도 있어야 함)


MINIMAL = "최소개선"       # 개선 유형(띄어쓰기를 뺀 꼴)
TYPE_BASIS = "F05 최소개선 유형 세부 지침 1항"


def _is_type(value: str | None, kind: str) -> bool:
    return squash(value or "") == kind


def _type_against_change(summary: list[dict], change: list[dict] | None) -> list[str] | None:
    """개선 유형이 대조표의 분석 결과와 어울리지 않는 능력단위(후보). 대조표가 없거나 유형 열이 없으면 None(체크를 내지 않는다).

    최소개선은 "NCS 능력단위 코드 및 기본 구조에는 변경이 없"을 때 적용한다(F05 1항) — 대조표에 '코드 변경'·'신설'로 적힌 능력단위가 최소개선이면 유형을 확인한다.
    양식 편집은 코드 변경이 "없거나 경미"하면 되므로(F21 양식편집 운영 기준) 코드 변경만으로는 후보로 올리지 않는다.
    '신설이면 신규 개발'이라는 기준은 지침에 없어 보지 않는다. 유형은 직능연이 분류하고 변경은 협의로 정하므로 X로 올리지 않는다.
    """
    if not change or all(e["개선 유형"] is None for e in summary):
        return None
    result = {entry["개선 후 코드"]: squash(entry["분석 결과"] or "") for entry in change if entry["개선 후 코드"]}
    odd = []
    for e in summary:
        kind, analysis = squash(e["개선 유형"] or ""), result.get(e["코드"], "")
        if kind == MINIMAL and ("코드변경" in analysis or "신설" in analysis):
            odd.append(f"{e['코드']} — 대조표의 분석 결과는 「{analysis.replace('능력단위', '능력단위 ').replace('코드변경', '코드 변경')}」인데 개선 유형이 「{e['개선 유형']}」임. "
                       f"최소개선은 능력단위 코드와 기본 구조에 변경이 없을 때 적용({TYPE_BASIS}) — 직능연과 유형 확인")
    return odd


def check_required(plan: dict, module_cells: list[str], *, draft: bool = False) -> list[dict]:
    basic = plan.get("기본") or {}
    summary = plan.get("총괄표") or []
    label_basic, label_type, label_people, label_placeholder = "⑧ 기본 정보", "⑧ 개선 유형", "⑧ 담당 집필진·검토진", "⑧ 안내 문구·자리표시"
    label_lead, label_change = "⑧ 최소개선 담당", "⑧ 개선 유형과 대조표"
    checks, notes = {}, {}
    missing = [k for k, v in basic.items() if not v and not (draft and k in DRAFT_OPTIONAL)]
    deferred = [k for k, v in basic.items() if not v and draft and k in DRAFT_OPTIONAL]
    checks[label_basic] = X if missing else O
    if missing:
        notes[label_basic] = "비어 있음: " + ", ".join(missing)
    elif deferred:
        notes[label_basic] = f"{DRAFT_NOTE}: " + ", ".join(deferred)
    if not summary:
        checks[label_type] = checks[label_people] = TRI
        notes[label_type] = notes[label_people] = "총괄표를 읽지 못함"
    else:
        if all(e["개선 유형"] is None for e in summary):
            checks[label_type] = NA   # 신규 개발 양식에는 개선 유형 열이 없다
            notes[label_type] = "총괄표에 개선 유형 열이 없음(신규 개발 양식)"
        elif draft and all(not e["개선 유형"] for e in summary):
            checks[label_type] = NA
            notes[label_type] = DRAFT_NOTE
        else:
            bad_type = [f"{e['코드']} 「{e['개선 유형'] or '빈 칸'}」" for e in summary
                        if squash(e["개선 유형"] or "") not in {squash(t) for t in IMPROVE_TYPES}]
            checks[label_type] = X if bad_type else O
            if bad_type:
                notes[label_type] = "개선 유형은 신규 개발/기존 개선/양식 편집/최소개선 중 하나: " + ", ".join(bad_type)
        # 최소개선은 대표집필자 1인이 일괄 담당하고 별도 검토진을 두지 않는 것이 원칙이다(F05 최소개선 유형 세부 지침 2항) — 검토진 칸은 비어도 된다
        minimal = [e for e in summary if _is_type(e["개선 유형"], MINIMAL)]
        no_people = [e["코드"] for e in summary if not e["집필진"] or (not e["검토진"] and e not in minimal)]
        if draft and no_people:
            checks[label_people] = NA
            notes[label_people] = DRAFT_NOTE
        else:
            checks[label_people] = X if no_people else O
            if no_people:
                notes[label_people] = "집필진 또는 검토진이 비어 있음(최소개선은 검토진을 비워도 됨): " + ", ".join(no_people)
        writers = sorted({squash(e["집필진"]) for e in minimal if e["집필진"]})
        if minimal and not draft:
            checks[label_lead] = TRI if len(writers) > 1 else O
            if len(writers) > 1:
                notes[label_lead] = ("최소개선 학습모듈의 담당 집필진이 여럿임: " + ", ".join(f"{e['코드']} 「{e['집필진']}」" for e in minimal if e["집필진"])
                                     + " — 대표집필자 1인이 일괄 담당하는지 확인(F05 최소개선 유형 세부 지침 2항)")
        odd = _type_against_change(summary, plan.get("대조표"))
        if odd is not None:
            checks[label_change] = TRI if odd else O
            if odd:
                notes[label_change] = "\n".join(odd)
    placeholders = sorted({m.group(0) for text in module_cells for m in [PLACEHOLDER.search(text)] if m})
    checks[label_placeholder] = X if placeholders else O
    if placeholders:
        notes[label_placeholder] = "양식의 자리표시로 보이는 글이 남아 있음: " + ", ".join(placeholders)
    return [row("⑧", f"{REGION} > 기본 정보·총괄표", "", None, checks, notes, "비어 있는 항목을 채우고 양식 안내 문구를 지울 것" if X in checks.values() else None)]


# ── ⑨ 변경 전후 대조표 ──────────────────────────────────────────────────────────

def expected_analysis(before: str, after: str) -> str:
    if not before and after:
        return "능력단위 신설"
    if before and not after:
        return "능력단위 삭제"
    if before == after:
        return "변경 없음"
    return "능력단위 코드 변경"


def check_change_table(plan: dict) -> list[dict]:
    change = plan.get("대조표")
    summary = plan.get("총괄표") or []
    label_match, label_analysis = "⑨ 개선 후 = 총괄표", "⑨ 분석 결과"
    if change is None:
        kind = squash((plan.get("기본") or {}).get("신규/개선") or "")
        if kind.startswith("신규"):
            label = "⑨ 대조표"
            return [row("⑨", f"{REGION} > 변경 전·후 대조표", "", None, {label: NA}, {label: "신규 개발 세분류 — NCS 변경 전·후 대조표 해당 없음"})]
        return [_no_table("⑨", "NCS 변경 전·후 대조표", "1쪽 NCS 변경 전·후 대조표를 작성할 것")]
    rows = []
    summary_codes = {e["코드"] for e in summary}
    after_codes = set()
    for entry in change:
        before, after = entry["개선 전 코드"], entry["개선 후 코드"]
        checks, notes = {}, {}
        if after:
            after_codes.add(after)
            if summary_codes and after not in summary_codes:
                checks[label_match] = X
                notes[label_match] = f"개선 후 「{after}」가 총괄표에 없음"
            else:
                checks[label_match] = O if summary_codes else TRI
                if not summary_codes:
                    notes[label_match] = "총괄표를 읽지 못해 대조 생략"
        else:
            checks[label_match] = NA
        expected = expected_analysis(before, after)
        actual = entry["분석 결과"]
        if not actual and not before:
            checks[label_analysis] = X
            notes[label_analysis] = "개선 전 능력단위번호와 분석 결과가 비어 있음 — 변경전후대조표를 보고 적을 것(개선 전이 없는 능력단위면 「능력단위 신설」)"
        elif not actual:
            checks[label_analysis] = X
            notes[label_analysis] = f"분석 결과가 비어 있음 — 코드 비교로는 「{expected}」"
        elif squash(expected) in squash(actual) or squash(actual) in squash(expected):
            checks[label_analysis] = O
        else:
            checks[label_analysis] = X
            notes[label_analysis] = f"대조표 「{actual}」, 코드 비교 「{expected}」 (개선 전 {before or '없음'} → 개선 후 {after or '없음'})"
        rows.append(row("⑨", f"{REGION} > 변경 전·후 대조표", after or before, f"{before} → {after}", checks, notes,
                        "개선 후 능력단위를 총괄표와 맞추고 분석 결과를 코드 비교대로 적을 것" if X in checks.values() else None))
    missing = sorted(summary_codes - after_codes)
    if change and missing:
        rows.append(row("⑨", f"{REGION} > 변경 전·후 대조표", "", None, {label_match: X},
                        {label_match: "총괄표에는 있는데 대조표 개선 후에 없음: " + ", ".join(missing)}, "대조표에 빠진 능력단위를 추가할 것"))
    if not rows:
        rows.append(_no_table("⑨", "NCS 변경 전·후 대조표", "대조표에 능력단위를 기재할 것"))
    return rows
