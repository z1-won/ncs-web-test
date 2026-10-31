"""F02 필요지식 ⑦: 그림·표 번호 연속 — figtab 검사 결과(findings)를 체크리스트 행으로 바꾼다."""

from ncs_core import FAIL, O, PASS, TRI, UNDECIDED, X

from ..figtab import ITEM as FIGTAB_ITEM
from ..figtab import check_figtab
from .common import ITEM

VALUE = {PASS: O, FAIL: X, UNDECIDED: TRI}


def check_figures(sections, labels: dict, *, min_agreement: float) -> list[dict]:
    rows = []
    for finding in check_figtab(sections, labels["lesson_spans"], min_agreement=min_agreement, labels=labels):
        sub = finding["item_id"].replace(FIGTAB_ITEM, "").lstrip("-") or "번호 연속(묶음)"
        value = VALUE[finding["verdict"]]
        rows.append(
            {
                "item_id": ITEM + "⑦",
                "region_path": finding["region_path"],
                "원고": finding.get("evidence_quote"),
                "체크": {sub: value},
                "판정": finding["verdict"],
                "비고": {sub: finding["reason"]} if value != O else {},
                "수정 제안": finding.get("suggestion"),
            }
        )
    return rows
