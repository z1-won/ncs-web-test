"""1~3쪽 규칙 — ① NCS 목록 대조, ② 학습모듈 코드·명칭, ⑧ 필수 기재, ⑨ 변경 전후 대조표."""

from ncs_core import NA, O, TRI, X
from ncs_core.ncs_catalog import Catalog

from ..parsers import LM_CODE, UNIT_CODE, squash
from ..patterns import IMPROVE_TYPES, PLACEHOLDER
from .common import pair, row, same_loose, same_text

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


# ── ② 학습모듈 코드·명칭 ─────────────────────────────────────────────────────────

def check_identity(plan: dict) -> list[dict]:
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
        else:
            checks[label_name] = X if not same_text(entry["명칭"], entry["LM 명칭"]) else O
            notes[label_name] = pair(entry["명칭"], entry["LM 명칭"], "총괄표 학습모듈명", "능력단위명")
        cross = []
        if position_pairs and not any(same_loose(entry["명칭"], u) and same_loose(entry["LM 명칭"], m) for u, m in position_pairs):
            cross.append(f"위치 표에 「{entry['명칭']} / {entry['LM 명칭']}」 짝이 없음")
        module = module_by_code.get(code)
        if module is None:
            cross.append(f"모듈 표(NCS 수정 금지)에 능력단위 「{code}」 표가 없음")
        else:
            if not same_loose(module["명칭"], entry["명칭"]):
                cross.append(pair(entry["명칭"], module["명칭"], "모듈 표 능력단위명", "총괄표"))
            if not same_loose(module["학습모듈명"], entry["LM 명칭"]):
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

def check_required(plan: dict, module_cells: list[str]) -> list[dict]:
    basic = plan.get("기본") or {}
    summary = plan.get("총괄표") or []
    label_basic, label_type, label_people, label_placeholder = "⑧ 기본 정보", "⑧ 개선 유형", "⑧ 담당 집필진·검토진", "⑧ 안내 문구·자리표시"
    checks, notes = {}, {}
    missing = [k for k, v in basic.items() if not v]
    checks[label_basic] = X if missing else O
    if missing:
        notes[label_basic] = "비어 있음: " + ", ".join(missing)
    if not summary:
        checks[label_type] = checks[label_people] = TRI
        notes[label_type] = notes[label_people] = "총괄표를 읽지 못함"
    else:
        if all(e["개선 유형"] is None for e in summary):
            checks[label_type] = NA   # 신규 개발 양식에는 개선 유형 열이 없다
            notes[label_type] = "총괄표에 개선 유형 열이 없음(신규 개발 양식)"
        else:
            bad_type = [f"{e['코드']} 「{e['개선 유형'] or '빈 칸'}」" for e in summary
                        if squash(e["개선 유형"] or "") not in {squash(t) for t in IMPROVE_TYPES}]
            checks[label_type] = X if bad_type else O
            if bad_type:
                notes[label_type] = "개선 유형은 신규 개발/기존 개선/양식 편집/최소개선 중 하나: " + ", ".join(bad_type)
        no_people = [e["코드"] for e in summary if not e["집필진"] or not e["검토진"]]
        checks[label_people] = X if no_people else O
        if no_people:
            notes[label_people] = "집필진 또는 검토진이 비어 있음: " + ", ".join(no_people)
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
        if not actual:
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
