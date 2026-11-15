"""평가 확인서: ①~⑤를 모두 검사한다(④는 종결 형태·목표 유사만, 구체성은 사람 확인)."""
from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "평가"
IMPLEMENTED = {"①", "②", "③", "④", "⑤"}
ITEMS = [SheetItem(n, item_text(COMPONENT, n), ("F02-평가-" + n,) if n in IMPLEMENTED else ()) for n in "①②③④⑤"]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
