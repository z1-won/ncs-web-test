"""개발계획서 점검 확인서 — F02 확인서와 같은 모양(구성요소 × 번호 × 적합/부적합)으로 접는다."""

from ncs_core.plan_items import PLAN_COMPONENT, plan_item_text
from ncs_core.sheet import SheetItem, build_sheet

COMPONENT = PLAN_COMPONENT
ITEMS = [SheetItem(no, plan_item_text(no), (f"PLAN-{no}",)) for no in "①②③④⑤⑥⑦⑧⑨⑩"]


def sheet(checklist):
    return build_sheet(checklist, ITEMS, COMPONENT)
