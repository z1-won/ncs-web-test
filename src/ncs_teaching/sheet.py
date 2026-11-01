"""F02 검수 확인서 「교수·학습 방법」 ①~④ 표."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "교수·학습 방법"
ITEMS = [SheetItem(no, item_text(COMPONENT, no), ("F02-교수학습-" + no,)) for no in "①②③④"]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
