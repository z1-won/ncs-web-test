"""F02 검수 확인서 「기타」 ①~⑧ 표. 모두 검사(③ 그림 속 노출·⑧ 글자 이미지 여부는 사람 확인).
마지막 '편집'(편집 체계 — 용지·여백·글꼴)과 '법령'(법령 현행화 후보)은 F02에 없는 항목이라 화면·결과에만 나오고 확인서 파일에는 들어가지 않는다(ncs_service.export.full_sheet)."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "기타"
IMPLEMENTED = {"①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧"}
EDITING = SheetItem("편집", "편집 체계는 집필 양식(F14)과 같은가? (F02 확인서에 없는 항목)\n- 용지 A4, 여백 좌우 25·위 20·아래 13·머리말 10·꼬리말 12㎜\n- 글꼴 KoPub바탕체·KoPub돋움체",
                    ("F02-기타-편집",))
LAWS = SheetItem("법령", "원고에 적힌 법령 이름은 현행인가? (F02 확인서에 없는 항목)\n- 폐지·명칭 변경·정식 명칭과 띄어쓰기가 다른 법령은 현행화 대상 후보\n- 바꿀지는 수행준거 준용 범위와 내용 전문가 판단",
                  ("F02-기타-법령",))
ITEMS = [SheetItem(n, item_text(COMPONENT, n), ("F02-기타-" + n,) if n in IMPLEMENTED else ()) for n in "①②③④⑤⑥⑦⑧"] + [EDITING, LAWS]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
