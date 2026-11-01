"""F02 검수 확인서 「수행 내용」 ①~④ 표. ②③은 규칙이 없어 '미검사'로 둔다."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "수행 내용"
ITEMS = [
    SheetItem("①", item_text(COMPONENT, "①"), ("F02-수행-①",)),
    SheetItem("②", item_text(COMPONENT, "②")),
    SheetItem("③", item_text(COMPONENT, "③")),
    SheetItem("④", item_text(COMPONENT, "④"), ("F02-수행-④",)),
]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
