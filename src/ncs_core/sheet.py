"""검수 확인서(F02) 표 형식으로 결과를 접는다.

확인서는 구성요소 × 체크 항목(①②③…) × 검수결과(적합/부적합)로 되어 있어,
행 단위 체크리스트를 F02 항목 번호별로 다시 모아 적합/부적합/판단불가 하나로 종합한다.
"""

from dataclasses import dataclass
from typing import Any

from .text import FAIL, PASS, TRI, UNDECIDED, X, visible

NOT_CHECKED = "미검사"


@dataclass(frozen=True)
class SheetItem:
    """확인서의 한 줄. item_ids: 이 항목을 이루는 체크리스트 item_id들.
    check_prefix: 한 행에 여러 항목이 섞여 있을 때(예: ②③④) 이 항목의 체크 이름 접두."""

    no: str
    text: str
    item_ids: tuple[str, ...] = ()
    check_prefix: str | None = None


def _item_checks(rows: list[dict], item: SheetItem) -> list[tuple[str, str, str, str, str | None]]:
    """(체크 이름, 값, 비고, 위치, 수정 제안) — 이 항목에 속하는 체크만.

    위치는 행의 "위치"(엔진이 넣는 짧은 표기, 예 '1-1')이고 없으면 빈 문자열.
    """
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
            note = notes.get(name, "") if isinstance(notes, dict) else "\n".join(notes)
            suggestion = row.get("수정 제안")
            out.append((name, value, note, row.get("위치") or "", suggestion if isinstance(suggestion, str) else None))
    return out


MAX_LOCATIONS = 8       # 머리 줄에 적는 위치 수. 넘으면 '…'
MAX_NOTE_LENGTH = 160   # 사례 한 줄의 최대 길이(한 건짜리 체크). 줄 단위로 자르므로 줄 중간이 끊기지 않는다
MAX_EXAMPLE_LENGTH = 140  # 사례 한 줄의 최대 길이(여러 건짜리 체크) — 두 문서의 문구가 다 보이게
MAX_EXAMPLE_LINES = 6   # 사례 줄 수. 넘으면 '외 n줄'


def _clip(line: str, limit: int) -> str:
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _example_lines(note: str, limit: int) -> list[str]:
    """엔진이 준 비고를 줄 단위로. 엔진이 이미 줄을 나눴으면(여러 사례) 그대로 두고, 각 줄만 길이를 자른다."""
    lines = [_clip(x.strip(), limit) for x in note.splitlines() if x.strip()]
    if len(lines) > MAX_EXAMPLE_LINES:
        lines = lines[:MAX_EXAMPLE_LINES] + [f"외 {len(lines) - MAX_EXAMPLE_LINES}줄"]
    return lines


def summarize_remarks(checks: list[tuple[str, str, str, str, str | None]]) -> list[str]:
    """확인서 비고 줄 목록 — 체크마다 머리 줄 + 사례 줄, 마지막에 '→ 수정 제안' 줄.

    확인서는 판정과 근거를 적는 곳이라 세 가지 역할을 줄로 나눈다(읽는 사람이 구분자를 해석하지 않게).
    - 머리 줄: '이름: N건 중 부적합 n건·판단불가 m건 (위치, …)'. 한 건만 검사한 체크는 건수가 의미 없으므로 '이름:'만.
    - 사례 줄: 첫 위반 행의 비고. 엔진이 여러 줄(번호 매긴 사례)로 줬으면 줄마다 한 줄, 줄 단위로만 자른다.
    - 조치 줄: '→ 수정 제안'. 엔진이 ' / '로 여러 제안을 이어 준 것은 제안마다 한 줄.
    어디가 어떻게 다른지의 상세는 지적사항 표에 있다.
    """
    stats: dict[str, dict] = {}
    for name, value, note, where, suggestion in checks:
        stat = stats.setdefault(name, {"total": 0, X: 0, TRI: 0, "where": [], "note": "", "suggest": None})
        stat["total"] += 1
        if value in (X, TRI):
            stat[value] += 1
            if where and where not in stat["where"]:
                stat["where"].append(where)
            if note and not stat["note"]:
                stat["note"] = note
            if suggestion and not stat["suggest"]:
                stat["suggest"] = suggestion
    lines, suggestions = [], []
    for name, stat in stats.items():
        if not stat[X] and not stat[TRI]:
            continue
        if stat["total"] == 1:
            example = _example_lines(stat["note"], MAX_NOTE_LENGTH)
            lines.append(f"{name}:" if example else f"{name}: {'부적합' if stat[X] else '판단불가'}")
        else:
            example = _example_lines(stat["note"], MAX_EXAMPLE_LENGTH)
            counts = "·".join(f"{label} {stat[key]}건" for key, label in ((X, "부적합"), (TRI, "판단불가")) if stat[key])
            where = stat["where"]
            shown = ", ".join(where[:MAX_LOCATIONS]) + (" …" if len(where) > MAX_LOCATIONS else "")
            lines.append(f"{name}: {stat['total']}건 중 {counts}" + (f" ({shown})" if shown else ""))
        lines += example
        for one in (stat["suggest"] or "").split(" / "):
            one = one.strip()
            if one and one not in suggestions:
                suggestions.append(one)
    lines += [f"→ {one}" for one in suggestions]
    return lines


def build_sheet(checklist: list[dict], items: list[SheetItem], component: str) -> list[dict[str, Any]]:
    sheet = []
    for item in items:
        checks = _item_checks(checklist, item)
        values = [v for _, v, _, _, _ in checks]
        if not item.item_ids or not checks:
            verdict = NOT_CHECKED
        elif X in values:
            verdict = FAIL
        elif TRI in values:
            verdict = UNDECIDED
        else:
            verdict = PASS
        remarks = summarize_remarks(checks)
        sheet.append(
            {
                "구성요소": component,
                "번호": item.no,
                "체크 항목": visible(item.text),  # 원문의 기호 글꼴 글자(네모 번호 󰊱 등)는 화면에서 깨지므로 읽을 수 있게
                "검수결과": verdict,
                "적합": verdict == PASS,
                "부적합": verdict == FAIL,
                "비고": "\n".join(remarks) if remarks else ("규칙 미구현" if verdict == NOT_CHECKED else ""),
            }
        )
    return sheet
