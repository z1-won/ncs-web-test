"""F02 교수·학습 방법 ①·③: 교수 방법 / 학습 방법이 3개 이상 작성되었는가? 학습마다 1행."""

from ncs_core import O, X, visible

from .common import PART_LABEL, no_block_row, row

ITEM_NO = {"교수": "①", "학습": "③"}


def check_counts(blocks: list[dict], part: str, *, min_items: int = 3) -> list[dict]:
    no, label = ITEM_NO[part], PART_LABEL[part]
    name = f"{no} {label} {min_items}개 이상"
    if not blocks:
        return [no_block_row(no, name)]
    rows = []
    for block in blocks:
        items = block[part]
        count = len(items)
        checks = {name: O if count >= min_items else X}
        notes = {}
        if count == 0:
            notes[name] = f"'{label}' 소제목 또는 글머리 항목을 찾지 못함"
        elif count < min_items:
            notes[name] = f"{count}개 — {min_items}개 이상 작성해야 함"
        others = [p for p in block["기타 문단"] if p["part"] == part]
        if others:
            notes[f"{no} 글머리 없는 문단"] = f"{len(others)}개 — 항목으로 세지 않음: " + " / ".join(f'p{p["idx"]} "{visible(p["text"][:30])}"' for p in others[:3])
        rows.append(row(no, block, {"개수": count, "항목": [visible(p["text"]) for p in items]}, checks, notes,
                        f"{label}을 {min_items}개 이상 작성"))
    return rows
