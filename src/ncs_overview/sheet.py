"""F02 검수 확인서 「학습모듈의 개요」 ①~⑧ 표."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "학습모듈의 개요"
ITEMS = [
    SheetItem('①', item_text(COMPONENT, '①'), ("F02-개요-①",)),
    SheetItem('②', item_text(COMPONENT, '②'), ("F02-개요-②",)),
    SheetItem('③', item_text(COMPONENT, '③'), ("F02-개요-③",)),
    SheetItem('④', item_text(COMPONENT, '④'), ("F02-개요-④",)),
    SheetItem('⑤', item_text(COMPONENT, '⑤'), ("F02-개요-⑤",)),
    SheetItem('⑥', item_text(COMPONENT, '⑥'), ("F02-개요-⑥",)),
    SheetItem('⑦', item_text(COMPONENT, '⑦'), ("F02-개요-⑦",)),
    SheetItem('⑧', item_text(COMPONENT, '⑧'), ("F02-개요-⑧",)),
]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
