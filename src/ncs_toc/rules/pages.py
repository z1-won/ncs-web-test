"""F02 차례 ⑦: 차례에 적힌 쪽수가 본문에서 그 제목이 실제로 시작하는 쪽과 같은가 — 차례 줄마다 1행.

hwpx에는 쪽 번호가 없으므로 원고를 한글에서 PDF로 저장한 '출력본'(역할 print)이 있어야 확정한다.
출력본이 없으면 △ 한 행으로 이유를 남긴다(미검사가 아니라 "왜 못 봤는지"가 확인서에 보이게).
출력본의 제목 쪽은 ncs_core.manuscript.pages.locate_headings가 찾고, 여기서는 차례 쪽수와 비교만 한다.
"""

from __future__ import annotations

from ncs_core import NA, O, PASS, TRI, X, verdict

ITEM_ID = "F02-차례-⑦"
CHECK = "⑦ 차례 쪽수 = 본문 시작 쪽"
SUGGEST_FIX = "차례의 쪽수를 본문 시작 쪽에 맞춤 (한글: 차례 필드 갱신 또는 직접 수정)"
SUGGEST_PRINT = "원고를 한글에서 PDF로 저장한 출력본을 함께 올림"


def toc_targets(toc: dict) -> list[tuple[str, str, str | None]]:
    """차례 줄 → (열쇠, 차례에 보이는 글, 쪽). 열쇠는 locate_headings의 열쇠와 같다."""
    out = []
    for lesson in toc["학습"]:
        out.append((f"학습 {lesson['no']}", f"학습 {lesson['no']}. {lesson['text']}", lesson.get("page")))
    for sub in toc["내용"]:
        out.append((f"{sub['no']}-{sub['sub']}", f"{sub['no']}-{sub['sub']}. {sub['text']}", sub.get("page")))
    for line in toc["줄"]:
        out.append((f"학습 {line['lesson']} {line['kind']}", f"학습 {line['lesson']} • {line['kind']}", line.get("page")))
    for name, page in toc["꼬리"].items():
        out.append((name, name, page))
    return out


def check_toc7(toc: dict, headings: dict | None, *, module_code: str = "", print_code: str | None = None,
               print_missing: str | None = None) -> list[dict]:
    """headings: locate_headings 결과(출력본 없으면 None). print_missing: 출력본을 못 쓴 이유(없음·읽기 실패)."""
    if headings is None:
        note = print_missing or "출력본 PDF가 없어 쪽수를 확인하지 못함"
        return [_row("section0 > 차례", {"차례": "전체"}, None, {CHECK: TRI}, {CHECK: note}, SUGGEST_PRINT)]
    if module_code and print_code and print_code != module_code:
        note = f"출력본 「{print_code}」, 원고 「{module_code}」 (다른 원고의 출력본이라 쪽수를 비교하지 않음)"
        return [_row("section0 > 차례", {"차례": "전체"}, print_code, {CHECK: TRI}, {CHECK: note}, "이 원고의 출력본 PDF를 올림")]
    broken = set(toc.get("쪽 깨짐", []))
    rows = []
    for key, label, page in toc_targets(toc):
        found = headings.get(key)
        shown = f"{label} {page}" if page else label
        suggestion = None
        if page is None and key in broken:
            value, note = X, f"차례 「{label} ?」 (쪽수가 갱신되지 않음)"
            suggestion = SUGGEST_FIX
        elif page is None:
            value, note = NA, "차례에 쪽수가 없는 줄"
        elif found is None:
            value, note = TRI, f"차례 「{shown}」, 출력본에서 「{label}」 시작 쪽을 찾지 못함"
        elif found["folio"] is None:
            value, note = TRI, f"차례 「{shown}」, 출력본 {found['index'] + 1}번째 쪽에 있으나 쪽 번호를 읽지 못함"
        elif found["source"] == "추정":
            same = found["folio"] == page
            value = TRI
            note = f"차례 「{shown}」, 출력본 {found['folio']}쪽 (쪽 번호를 읽지 못해 앞뒤 쪽에서 추정{'' if same else ', 다름'})"
        elif found["folio"] == page:
            value, note = O, ""
        else:
            value, note = X, f"차례 「{shown}」, 출력본 {found['folio']}쪽"
            suggestion = SUGGEST_FIX
        checks = {CHECK: value}
        rows.append(_row(f"section0 > 차례 > {key}", {"차례": shown},
                         found["folio"] if found else None, checks, {CHECK: note} if note else {}, suggestion))
    if not rows:
        rows.append(_row("section0 > 차례", {"차례": "전체"}, None, {CHECK: TRI}, {CHECK: "차례에서 쪽수가 있는 줄을 찾지 못함"}, None))
    return rows


def _row(region, manuscript, print_page, checks, notes, suggestion):
    result = verdict(checks)
    return {
        "item_id": ITEM_ID,
        "region_path": region,
        "위치": "차례",
        "원고": manuscript,
        "출력본": print_page,
        "체크": checks,
        "판정": result,
        "비고": notes,
        "수정 제안": None if result == PASS else suggestion,
    }
