"""F02 검수 확인서 「개발 이력 및 판권」 ① 표."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "개발 이력 및판권"
ITEMS = [SheetItem("①", item_text(COMPONENT, "①"), ("F02-판권-①",))]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
