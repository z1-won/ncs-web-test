"""F02 필요지식 ⑥: 본문 번호 체계 󰊱 〉 1. 〉 (1) 〉 (가) 〉 1) 〉 가) 〉 ① 〉 ㉠ 〉 ⓐ (F11 p.43).

학습 내용(N-M)당 1행. 안에서 '필요 지식 / 수행 내용 / 수행 순서 / 재료 / 안전…' 머리말마다 번호가 새로 시작한다고 본다.
규칙 3개: 첫 수준이 󰊱 / 수준은 +1만(건너뜀 X) / 같은 수준은 연번.
수준은 "보이는 번호"로 판정한다: hwpx는 한글 자동 번호(문단 번호 속성)를 Document.numbers로 복원해 텍스트 앞에 붙여 보고,
타이핑한 번호는 텍스트 첫 글자로 본다(둘이 섞인 원고가 흔하다). hwp는 자동 번호를 복원할 수 없어 텍스트만 본다 → 비고에 명시.
번호 문단 0개면 △.
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


HEAD1_STYLE = re.compile(r"^[\U000F02B1-\U000F02C9]제목$")  # 첫 수준 제목의 문단 스타일(󰊱제목)


def check_numbering(body: dict, units: list[dict], table_paragraphs: set[int] | None,
                    numbers: list[str | None] | None = None, styles: list[str] | None = None) -> list[dict]:
    """numbers: 본문 섹션 문단별 자동 번호(Document.section_numbers). hwp면 None.
    styles: 문단별 스타일 이름. 󰊱제목 스타일인데 텍스트에 󰊱 기호가 없는 제목(기호를 지운 원고)도 첫 수준으로 세어
    아래 '1.'이 새로 시작하는 것을 알아보고, 기호 누락은 따로 지적한다. 없으면(hwp) 텍스트만 본다."""
    rows, lines = [], body["lines"]

    def shown(i: int, text: str) -> str:
        """화면에 보이는 문단 — 자동 번호가 있으면 그 번호를 앞에 붙인다."""
        label = numbers[i] if numbers is not None and i < len(numbers) else None
        return f"{label} {text}" if label else text

    for unit in units:
        key = f"{unit['no']}-{unit['sub']}"
        region = f"section1 > 학습 {unit['lesson']} > {key}. {visible(unit['text'])}"
        segments, segment, name, empties, unmarked = [], [], "제목 아래", [], []
        for k in range(unit["k0"] + 1, unit["k1"]):
            i, text = lines[k]
            # 이 줄 앞에서 건너뛴 문단(본문 줄 목록은 빈 문단을 빼고 만든다) 중 자동 번호만 달린 빈 문단:
            # 화면에는 번호가 찍히므로 연번에 넣고, 빈 번호 문단 자체를 지적한다.
            if numbers is not None:
                for j in range(lines[k - 1][0] + 1, i):
                    label = numbers[j] if j < len(numbers) else None
                    if label and (table_paragraphs is None or j not in table_paragraphs) and (found := level_of(label)):
                        segment.append((j, found[0], found[1], f"{label} (빈 문단)"))
                        empties.append(f"[{name}] p{j} {label} — 번호만 있고 내용이 없는 문단")
            if head := mark(text):
                segments.append((name, segment))
                segment, name = [], head
                continue
            if table_paragraphs is not None and i in table_paragraphs:
                continue
            if MEMO_LINE.match(text):
                continue
            if found := level_of(shown(i, text)):
                segment.append((i, found[0], found[1], shown(i, text)))
            elif styles and i < len(styles) and HEAD1_STYLE.match(styles[i] or ""):
                segment.append((i, 1, None, text))  # 기호 없는 󰊱 제목: 번호는 모름(None) — 연번 검사에서 건너뜀
                unmarked.append(f'[{name}] p{i} "{visible(text[:30])}" — 󰊱 제목 스타일인데 기호가 없음')
        segments.append((name, segment))
        checks = {"첫 수준이 󰊱": O, "수준 순서(건너뜀 없음)": O, "같은 수준 연번": O}
        if empties:
            checks["빈 번호 문단"], notes_empty = X, " / ".join(empties[:6])
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
                if n is None:
                    n = expected  # 기호 없는 󰊱 제목: 번호를 알 수 없어 기대값으로 두고 넘어간다
                elif n != expected:
                    sequence.append(f'[{name}] p{i} "{visible(text[:30])}" — {NAMES[level]} {n}번째인데 {expected} 이어야 함')
                counters[level] = n
                for x in list(counters):
                    if x > level:
                        del counters[x]
                current = level
        if empties:
            notes["빈 번호 문단"] = notes_empty
        if n_numbered == 0:
            checks = {"번호 찾기": TRI}
            notes["번호 찾기"] = ("번호가 붙은 문단을 찾지 못함 — 원고 확인" if numbers is not None
                              else "번호가 붙은 문단을 텍스트에서 찾지 못함 — hwp는 자동 번호(문단 번호 속성)가 보이지 않음, hwpx로 변환 권장")
        elif numbers is None and not any(level == 1 for _, items in segments for _, level, _, _ in items):
            # hwp인데 첫 수준(󰊱) 기호가 텍스트에 하나도 없다: 양식의 󰊱 제목은 자동 번호라 보이지 않는 것이 보통이므로
            # '󰊱로 시작해야 함'·건너뜀·연번(󰊱마다 다시 1.)은 전부 가짜가 된다. 판정하지 않고 사람 확인(△)으로 둔다.
            checks = {"첫 수준이 󰊱": TRI, "수준 순서(건너뜀 없음)": TRI, "같은 수준 연번": TRI}
            notes["자동 번호"] = ("hwp 라 자동 번호(문단 번호 속성)가 보이지 않고 텍스트에 󰊱 기호도 없음 — 󰊱 기준의 시작·건너뜀·연번은 "
                              "판정할 수 없음, hwpx로 변환해 다시 검사")
            if unmarked:
                checks["󰊱 기호 표시"], notes["󰊱 기호 표시"] = X, " / ".join(unmarked[:6])
            if table_paragraphs is None:
                notes["표 안 문단"] = "hwp 라 표 안 번호도 함께 셈"
        else:
            if first_bad:
                checks["첫 수준이 󰊱"], notes["첫 수준이 󰊱"] = X, " / ".join(first_bad[:4])
            if skipped:
                checks["수준 순서(건너뜀 없음)"], notes["수준 순서(건너뜀 없음)"] = X, " / ".join(skipped[:6])
            if sequence:
                checks["같은 수준 연번"], notes["같은 수준 연번"] = X, " / ".join(sequence[:6])
            if unmarked:
                checks["󰊱 기호 표시"], notes["󰊱 기호 표시"] = X, " / ".join(unmarked[:6])
            if table_paragraphs is None:
                notes["표 안 문단"] = "hwp 라 표 안 번호도 함께 셈(표 안 번호가 지적되면 무시)"
            if numbers is None:
                notes["자동 번호"] = "hwp 라 자동 번호(문단 번호 속성)는 보이지 않음 — 건너뜀·연번 지적이 가짜일 수 있음, hwpx로 변환 권장"
        rows.append(row("⑥", region, f"번호 문단 {n_numbered}개", checks, notes, "󰊱 〉 1. 〉 (1) 〉 (가) 〉 1) 〉 가) 〉 ① 〉 ㉠ 순서로 수정"))
    return rows
