"""⑩ 법령 명칭 현행 여부 — 계획서에 적힌 법령 이름이 현행인가(폐지·명칭 변경은 현행화 대상으로 표시).

법령명 추출은 ncs_core.law_catalog.extract_law_names, 판정 근거는 law_names.tsv(법제처 Open API 조회 결과).
NCS(수정 금지) 쪽에 있는 법령명은 집필자가 고칠 수 없으므로 X 대신 △로 두고 '직능연 협의' 안내만 한다.
"""

from ncs_core import NA, O, TRI, X
from ncs_core.law_catalog import LawCatalog, extract_law_names

from .common import row

LABEL = "⑩ 법령 명칭 현행"


def _texts(module: dict) -> list[tuple[str, str, bool]]:
    """(자리, 글, NCS 쪽인가)"""
    out = [("능력단위 정의", module["정의"], True), ("학습모듈의 목표", module["목표"], False)]
    for element in module["요소"]:
        for sentence in element["수행준거"]:
            out.append((f"수행준거 {element['코드']}", sentence, True))
    for lesson in module["학습"]:
        for sub in lesson["내용"]:
            for goal in sub["목표"]:
                out.append((f"학습 목표 {sub['번호']}-{sub['소번호'] or '?'}", goal, False))
    return out


def check_laws(module: dict, catalog: LawCatalog | None) -> list[dict]:
    found: dict[str, tuple[str, bool, bool]] = {}   # 표기 → (자리, 따옴표, NCS 쪽)
    for where, text, ncs_side in _texts(module):
        for name, quoted in extract_law_names(text):
            found.setdefault(name, (where, quoted, ncs_side))
    region = f"개발계획서 > 모듈 표 {module['코드'] or '(코드 없음)'}"
    if not found:
        return [row("⑩", region, module["코드"], None, {LABEL: NA}, {LABEL: "법령 이름이 없음"})]
    if catalog is None:
        names = ", ".join(f"「{n}」" for n in list(found)[:5])
        return [row("⑩", region, module["코드"], names, {LABEL: TRI}, {LABEL: "법령명 표(law_names.tsv)가 없어 현행 여부를 확인하지 못함: " + names})]
    rows = []
    for name, (where, quoted, ncs_side) in found.items():
        entry = catalog.lookup(name)
        checks, notes, suggestion = {}, {}, None
        if entry is None:
            checks[LABEL] = TRI
            notes[LABEL] = f"{where} 「{name}」 — 법령명 표에 없음(scripts/data/build_law_names.py로 조회 필요)"
        elif entry.status == "미검색":
            checks[LABEL] = TRI
            notes[LABEL] = f"{where} 「{name}」 — 법제처 현행·연혁 목록에 없는 이름(법령명이 틀렸거나 법령이 아님). 정확한 법령명 확인"
        elif entry.status == "현행":
            checks[LABEL] = O
        elif entry.status in ("폐지", "명칭변경"):
            why = f"폐지됨({entry.revision}, 시행 {entry.effective})" if entry.status == "폐지" else f"현행 명칭 「{entry.current_name}」"
            if ncs_side:
                checks[LABEL] = TRI
                notes[LABEL] = f"{where} 「{name}」 — {why}. NCS 원문(수정 금지)이므로 직능연과 협의"
            else:
                checks[LABEL] = X
                notes[LABEL] = f"{where} 「{name}」 — {why}"
                suggestion = f"「{name}」 → 「{entry.current_name}」로 현행화" if entry.current_name else f"「{name}」 폐지 — 대체 법령 확인"
        else:
            checks[LABEL] = TRI
            notes[LABEL] = f"「{name}」 — 연혁만 있고 현행 목록에 없음(법제처 확인)"
        rows.append(row("⑩", f"{region} > {where}", module["코드"], name, checks, notes, suggestion))
    return rows
