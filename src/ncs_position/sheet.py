"""F02 검수 확인서 「NCS-학습모듈의 위치」 ①~⑤ 표."""

from ncs_core.f02_items import item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = "NCS-학습모듈의 위치"
ITEMS = [
    SheetItem('①', item_text(COMPONENT, '①'), ("F02-위치-①",)),
    SheetItem('②', item_text(COMPONENT, '②'), ("F02-위치-②③④",), "②"),
    SheetItem('③', item_text(COMPONENT, '③'), ("F02-위치-②③④",), "③"),
    SheetItem('④', item_text(COMPONENT, '④'),
        ("F02-위치-②③④",),
        "④",
    ),
    SheetItem('⑤', item_text(COMPONENT, '⑤'),
        ("F02-위치-⑤", "F02-위치-⑤-세분류"),
    ),
]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
