"""F02 검수 확인서 「차례」 ①~⑦ 표. ⑦은 출력본 PDF가 있을 때 확정, 없으면 판단불가."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "차례"
ITEMS = [
    SheetItem('①', item_text(COMPONENT, '①'), ("F02-차례-①",)),
    SheetItem('②', item_text(COMPONENT, '②'), ("F02-차례-②",)),
    SheetItem('③', item_text(COMPONENT, '③'), ("F02-차례-③",)),
    SheetItem('④', item_text(COMPONENT, '④'), ("F02-차례-④",)),
    SheetItem('⑤', item_text(COMPONENT, '⑤'), ("F02-차례-⑤",)),
    SheetItem('⑥', item_text(COMPONENT, '⑥'), ("F02-차례-⑥",)),
    SheetItem('⑦', item_text(COMPONENT, '⑦'), ("F02-차례-⑦",)),
]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
