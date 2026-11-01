"""F02 검수 확인서 「참고 자료」 ①~④ 표. ④는 미검사."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "참고 자료"
IMPLEMENTED = {"①", "②", "③"}
ITEMS = [SheetItem(n, item_text(COMPONENT, n), ("F02-참고자료-" + n,) if n in IMPLEMENTED else ()) for n in "①②③④"]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
