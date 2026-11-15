"""F02 검수 확인서 「기타」 ①~⑧ 표. 모두 검사(③ 그림 속 노출·⑧ 글자 이미지 여부는 사람 확인)."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "기타"
IMPLEMENTED = {"①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧"}
ITEMS = [SheetItem(n, item_text(COMPONENT, n), ("F02-기타-" + n,) if n in IMPLEMENTED else ()) for n in "①②③④⑤⑥⑦⑧"]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
