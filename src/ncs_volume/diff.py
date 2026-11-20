"""기존 원고 대비 변경 행 찾기 — '1행에 1자 이상 변경된 내용은 1행 변경'(요구사항 표준 지침).

1. 비교 단위(글 문단·표 한 행·캡션)를 두 원고에서 순서대로 늘어놓고 글(공백 정리)로 짝을 짓는다(difflib, 표준 라이브러리).
2. 같은 단위 → 변경 없음. 새로 생긴 단위 → 그 행 전부 변경.
3. 바뀐 단위 → 비슷한 기존 단위(유사도 0.5 이상)와 글자 단위로 비교해, 바뀐 글자가 1자라도 든 행만 변경으로 센다.
   글자를 지우기만 한 곳은 지운 자리의 행을 변경으로 본다. 비슷한 단위가 없으면 그 단위의 행 전부 변경.
   표의 한 행은 Line 하나가 행 글 전체를 맡으므로 1자라도 바뀌면 그 표 행의 줄 수 전부가 변경이다.
줄 바꿈 위치가 달라져 뒤로 밀린 글자는 '바뀐 글자'가 아니므로 변경으로 세지 않는다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .layout import Line, Unit

_SPACES = re.compile(r"\s+")
SIMILAR = 0.5


def _key(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def _changed_positions(old: str, new: str) -> set[int]:
    marks: set[int] = set()
    for op, _i1, _i2, j1, j2 in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if op in ("replace", "insert"):
            marks.update(range(j1, j2))
        elif op == "delete":
            marks.add(min(j1, max(len(new) - 1, 0)))
    return marks


def _lines_with(unit: Unit, marks: set[int]) -> list[Line]:
    out = []
    for line in unit.lines:
        if any(line.start <= k < line.end for k in marks) or (line.start == line.end and line.start in marks):
            out.append(line)
    return out


def changed_lines(old_units: list[Unit], new_units: list[Unit]) -> list[tuple[int, Line]]:
    """[(new_units에서의 번호, 바뀐 행)]."""
    old_keys = [_key(u.text) for u in old_units]
    new_keys = [_key(u.text) for u in new_units]
    out: list[tuple[int, Line]] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, old_keys, new_keys, autojunk=False).get_opcodes():
        if op == "insert":
            out += [(j, line) for j in range(j1, j2) for line in new_units[j].lines]
        elif op == "replace":
            for j in range(j1, j2):
                unit = new_units[j]
                best, score = None, 0.0
                for i in range(i1, i2):
                    matcher = SequenceMatcher(None, old_keys[i], new_keys[j], autojunk=False)
                    if matcher.real_quick_ratio() > score and matcher.quick_ratio() > score:
                        ratio = matcher.ratio()
                        if ratio > score:
                            best, score = i, ratio
                if best is None or score < SIMILAR:
                    out += [(j, line) for line in unit.lines]
                else:
                    out += [(j, line) for line in _lines_with(unit, _changed_positions(old_units[best].text, unit.text))]
    return out
