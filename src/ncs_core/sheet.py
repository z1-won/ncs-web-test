"""검수 확인서(F02) 표 형식으로 결과를 접는다.

확인서는 구성요소 × 체크 항목(①②③…) × 검수결과(적합/부적합)로 되어 있어,
행 단위 체크리스트를 F02 항목 번호별로 다시 모아 적합/부적합/판단불가 하나로 종합한다.
"""

from dataclasses import dataclass
from typing import Any

from .text import FAIL, PASS, TRI, UNDECIDED, X

NOT_CHECKED = "미검사"


@dataclass(frozen=True)
class SheetItem:
    """확인서의 한 줄. item_ids: 이 항목을 이루는 체크리스트 item_id들.
    check_prefix: 한 행에 여러 항목이 섞여 있을 때(예: ②③④) 이 항목의 체크 이름 접두."""

    no: str
    text: str
    item_ids: tuple[str, ...] = ()
    check_prefix: str | None = None


def _item_checks(rows: list[dict], item: SheetItem) -> list[tuple[str, str, str]]:
    """(체크 이름, 값, 비고) — 이 항목에 속하는 체크만."""
    out = []
    for row in rows:
        if row["item_id"] not in item.item_ids:
            continue
        notes = row["비고"]
        named = [k for k in row["체크"] if k[:1] in "①②③④⑤⑥⑦⑧⑨"]
        for name, value in row["체크"].items():
            # 접두가 있는 항목은 자기 접두의 체크만, 단 번호 없는 체크뿐인 행(표를 못 읽은 경우)은 모두 포함
            if item.check_prefix and named and not name.startswith(item.check_prefix):
                continue
            note = notes.get(name, "") if isinstance(notes, dict) else "; ".join(notes)
            out.append((name, value, note))
    return out


def build_sheet(checklist: list[dict], items: list[SheetItem], component: str) -> list[dict[str, Any]]:
    sheet = []
    for item in items:
        checks = _item_checks(checklist, item)
        values = [v for _, v, _ in checks]
        if not item.item_ids or not checks:
            verdict = NOT_CHECKED
        elif X in values:
            verdict = FAIL
        elif TRI in values:
            verdict = UNDECIDED
        else:
            verdict = PASS
        remarks = [f"{name}: {note}" if note else name for name, value, note in checks if value in (X, TRI)]
        sheet.append(
            {
                "구성요소": component,
                "번호": item.no,
                "체크 항목": item.text,
                "검수결과": verdict,
                "적합": verdict == PASS,
                "부적합": verdict == FAIL,
                "비고": "; ".join(dict.fromkeys(remarks)) if remarks else ("규칙 미구현" if verdict == NOT_CHECKED else ""),
            }
        )
    return sheet
