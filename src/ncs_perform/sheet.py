"""F02 검수 확인서 「수행 내용」 ①~④ 표. ②③의 내용 판단은 LLM 후보(△)."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "수행 내용"
ITEMS = [
    SheetItem("①", item_text(COMPONENT, "①"), ("F02-수행-①",)),
    SheetItem("②", item_text(COMPONENT, "②"), ("F02-수행-②",)),
    SheetItem("③", item_text(COMPONENT, "③"), ("F02-수행-③",)),
    SheetItem("④", item_text(COMPONENT, "④"), ("F02-수행-④",)),
]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
