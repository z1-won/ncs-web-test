"""F02 검수 확인서 「필요 지식」 ①~⑧ 표."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "필요 지식"
ITEMS = [
    SheetItem('①', item_text(COMPONENT, '①'), ("F02-필요지식-①",)),
    SheetItem('②', item_text(COMPONENT, '②'), ("F02-필요지식-②",)),
    SheetItem('③', item_text(COMPONENT, '③'), ("F02-필요지식-③",)),
    SheetItem('④', item_text(COMPONENT, '④'), ("F02-필요지식-④",)),
    SheetItem('⑤', item_text(COMPONENT, '⑤'), ("F02-필요지식-⑤",)),
    SheetItem('⑥', item_text(COMPONENT, '⑥'), ("F02-필요지식-⑥",)),
    SheetItem('⑦', item_text(COMPONENT, '⑦'), ("F02-필요지식-⑦",)),
    SheetItem('⑧', item_text(COMPONENT, '⑧'), ("F02-필요지식-⑧",)),
]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
