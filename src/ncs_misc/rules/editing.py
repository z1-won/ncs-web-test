"""편집 체계(안내서 A-07): 용지·여백과 글꼴이 집필 양식(F14, KoPub 필수)과 같은가 — 원고당 1행.

F02 검수 확인서에는 이 항목이 없다. 그래서 확인서 번호 대신 '편집'으로 화면·결과에만 보이고, 확인서 파일(54개 항목)에는 넣지 않는다.
기준은 ncs_core.layout: A4, 여백 좌우 25·위 20·아래 13·머리말 10·꼬리말 12㎜(허용 오차 0.5㎜), 글꼴 KoPub 계열.
  용지·여백  X  구역 하나라도 기준과 다름 — 숫자 대조라 확정한다(안내서 A-07: 자동 판정)
            △  원고에서 용지 정보를 찾지 못함
  글꼴      △  KoPub 계열이 아닌 글꼴로 적힌 글자가 있음 — 붙여 넣은 글·표 안 글자일 수 있고, 기준을 실제 원고 5건으로만 확인해
               자동으로 부적합을 내지 않는다(심의본·에디팅본은 0자, 1차 초안은 25자였다)
            O  모두 KoPub 계열
hwp는 용지·글꼴 정보를 읽지 못해 둘 다 △.
"""

from ncs_core import O, TRI, X
from ncs_core.layout import FONT_FAMILY, MARGINS_MM, other_fonts, page_problems, read_layout
from ncs_core.notes import lines

from .common import row

NO = "편집"
PAGE = "편집 용지·여백"
FONT = "편집 글꼴(KoPub)"
STANDARD = "A4, 여백 " + "·".join(f"{name} {value:g}" for name, value in MARGINS_MM.items()) + "㎜"
MAX_FONTS = 5


def check_editing(context) -> list[dict]:
    layout = read_layout(context.manuscript.path) if context.manuscript.format == "hwpx" else None
    if layout is None:
        note = "hwp는 용지·글꼴 정보를 읽지 못함 — hwpx로 저장해 다시 검수하거나 사람이 확인"
        return [row(NO, "원고", "", None, {PAGE: TRI, FONT: TRI}, {PAGE: note, FONT: note})]
    checks, notes = {}, {}
    problems = page_problems(layout)
    if not layout["구역"]:
        checks[PAGE], notes[PAGE] = TRI, "원고에서 용지 정보를 찾지 못함"
    elif problems:
        checks[PAGE], notes[PAGE] = X, lines(problems)
    else:
        checks[PAGE] = O
    others = other_fonts(layout)
    if others:
        total = sum(layout["글꼴"].values())
        shown = [f"{font} {count}자(전체 {total}자 중) — 예: 「{example}」" for font, count, example in others[:MAX_FONTS]]
        if len(others) > MAX_FONTS:
            shown.append(f"외 글꼴 {len(others) - MAX_FONTS}종")
        checks[FONT], notes[FONT] = TRI, lines(shown) + "\n— 붙여 넣은 글이나 표 안 글자일 수 있어 사람 확인"
    else:
        checks[FONT] = O
    suggestion = " / ".join(text for text in (
        f"쪽 설정을 집필 양식과 같게 맞춤({STANDARD})" if checks[PAGE] == X else "",
        f"{FONT_FAMILY}바탕체·{FONT_FAMILY}돋움체가 아닌 글꼴을 양식 스타일로 바꿈" if checks[FONT] == TRI else "") if text)
    return [row(NO, "원고", "", {"구역": layout["구역"], "글꼴": layout["글꼴"]}, checks, notes, suggestion or None)]
