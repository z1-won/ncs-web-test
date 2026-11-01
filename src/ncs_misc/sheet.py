"""F02 검수 확인서 「기타」 ①~⑧ 표. ③④⑤⑧은 미검사."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "기타"
IMPLEMENTED = {"①", "②", "⑥", "⑦"}
ITEMS = [SheetItem(n, item_text(COMPONENT, n), ("F02-기타-" + n,) if n in IMPLEMENTED else ()) for n in "①②③④⑤⑥⑦⑧"]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
