"""F02 필요지식 ⑥: 본문 번호 체계 󰊱 〉 1. 〉 (1) 〉 (가) 〉 1) 〉 가) 〉 ① 〉 ㉠ 〉 ⓐ (F11 p.43).

학습 내용(N-M)당 1행. 안에서 '필요 지식 / 수행 내용 / 수행 순서 / 재료 / 안전…' 머리말마다 번호가 새로 시작한다고 본다.
규칙 3개: 첫 수준이 󰊱 / 수준은 +1만(건너뜀 X) / 같은 수준은 연번.
텍스트 첫 글자로 수준을 판정하므로 한글 자동 번호(문단 번호 속성)는 보이지 않는다 → 번호 문단 0개면 △.
"""

import re

from ncs_core import O, TRI, X, visible

from ..structure import MEMO_LINE, mark
from .common import row

_GA = "가나다라마바사아자차카타파하"
LEVELS = [  # (수준, 이름, 정규식, 서수 함수)
    (1, "󰊱", re.compile(r"^([\U000F02B1-\U000F02C9]|[❶-❿➊-➓])"),
     lambda m: (ord(m.group(1)) - 0xF02B0) if ord(m.group(1)) >= 0xF02B1 else ((ord(m.group(1)) - 0x2775) if ord(m.group(1)) < 0x278A else ord(m.group(1)) - 0x2789)),
    (2, "1.", re.compile(r"^(\d{1,2})\.(?!\d)\s*"), lambda m: int(m.group(1))),
    (3, "(1)", re.compile(r"^\((\d{1,2})\)\s*"), lambda m: int(m.group(1))),
    (4, "(가)", re.compile(rf"^\(([{_GA}])\)\s*"), lambda m: _GA.index(m.group(1)) + 1),
    (5, "1)", re.compile(r"^(\d{1,2})\)\s*"), lambda m: int(m.group(1))),
    (6, "가)", re.compile(rf"^([{_GA}])\)\s*"), lambda m: _GA.index(m.group(1)) + 1),
    (7, "①", re.compile(r"^([①-⑳])"), lambda m: ord(m.group(1)) - 0x2460 + 1),
    (8, "㉠", re.compile(r"^([㉠-㉭])"), lambda m: ord(m.group(1)) - 0x3260 + 1),
    (9, "ⓐ", re.compile(r"^([ⓐ-ⓩ])"), lambda m: ord(m.group(1)) - 0x24D0 + 1),
]
NAMES = {level: name for level, name, _, _ in LEVELS}
NOT_A_NUMBER = (re.compile(r"^\d+-\d+\."), re.compile(r"^\d+\.\d+\s"), re.compile(r"^\[그림|^[〈<]표"))


def level_of(text: str):
    if any(p.match(text) for p in NOT_A_NUMBER):
        return None
    for level, _, pattern, ordinal in LEVELS:
        if m := pattern.match(text):
            return level, ordinal(m)
    return None


def check_numbering(body: dict, units: list[dict], table_paragraphs: set[int] | None) -> list[dict]:
    rows, lines = [], body["lines"]
    for unit in units:
        key = f"{unit['no']}-{unit['sub']}"
        region = f"section1 > 학습 {unit['lesson']} > {key}. {visible(unit['text'])}"
        segments, segment, name = [], [], "제목 아래"
        for k in range(unit["k0"] + 1, unit["k1"]):
            i, text = lines[k]
            if head := mark(text):
                segments.append((name, segment))
                segment, name = [], head
                continue
            if table_paragraphs is not None and i in table_paragraphs:
                continue
            if MEMO_LINE.match(text):
                continue
            if found := level_of(text):
                segment.append((i, found[0], found[1], text))
        segments.append((name, segment))
        checks = {"첫 수준이 󰊱": O, "수준 순서(건너뜀 없음)": O, "같은 수준 연번": O}
        notes, n_numbered, first_bad, skipped, sequence = {}, 0, [], [], []
        for name, items in segments:
            if not items:
                continue
            n_numbered += len(items)
            if items[0][1] != 1:
                first_bad.append(f'[{name}] p{items[0][0]} "{visible(items[0][3][:30])}" ({NAMES[items[0][1]]}) — 󰊱 로 시작해야 함')
            counters, current = {}, 0
            for i, level, n, text in items:
                if level > current + 1:
                    skipped.append(f'[{name}] p{i} "{visible(text[:30])}" — {NAMES[current] if current else "시작"} 다음에 {NAMES[level]} (중간 {", ".join(NAMES[x] for x in range(current + 1, level))} 건너뜀)')
                    current = level - 1
                expected = 1 if level > current else counters.get(level, 0) + 1  # 새 하위 목록이면 1부터
                if n != expected:
                    sequence.append(f'[{name}] p{i} "{visible(text[:30])}" — {NAMES[level]} {n}번째인데 {expected} 이어야 함')
                counters[level] = n
                for x in list(counters):
                    if x > level:
                        del counters[x]
                current = level
        if n_numbered == 0:
            checks = {"번호 찾기": TRI}
            notes["번호 찾기"] = "번호가 붙은 문단을 텍스트에서 찾지 못함 — 자동 번호(문단 번호 속성)일 수 있음, 원고 확인"
        else:
            if first_bad:
                checks["첫 수준이 󰊱"], notes["첫 수준이 󰊱"] = X, " / ".join(first_bad[:4])
            if skipped:
                checks["수준 순서(건너뜀 없음)"], notes["수준 순서(건너뜀 없음)"] = X, " / ".join(skipped[:6])
            if sequence:
                checks["같은 수준 연번"], notes["같은 수준 연번"] = X, " / ".join(sequence[:6])
            if table_paragraphs is None:
                notes["표 안 문단"] = "hwp 라 표 안 번호도 함께 셈(표 안 번호가 지적되면 무시)"
        rows.append(row("⑥", region, f"번호 문단 {n_numbered}개", checks, notes, "󰊱 〉 1. 〉 (1) 〉 (가) 〉 1) 〉 가) 〉 ① 〉 ㉠ 순서로 수정"))
    return rows
