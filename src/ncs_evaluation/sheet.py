"""평가 확인서: ①②③을 검사하고 ④⑤는 미검사로 표시한다."""
from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "평가"
IMPLEMENTED = {"①", "②", "③"}
ITEMS = [SheetItem(n, item_text(COMPONENT, n), ("F02-평가-" + n,) if n in IMPLEMENTED else ()) for n in "①②③④⑤"]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
