"""의견서 읽기 — 1·2차 검토의견서와 심의의견서(PDF 줄 또는 hwp/hwpx 표)를 의견 항목 목록으로 바꾼다. I/O 없음(읽기는 pipeline이 한다).

심의의견서는 F25 양식(「NCS학습모듈 소위원회 심의의견서」, hwp)을 읽는다: 머리 표(심의 위원·심의 분야·학습모듈 원고명) 뒤
표 `심의 항목 | 세분류 | 심의 의견`, 항목은 ① 학습모듈과 NCS 능력단위와의 정합성 ② 학습모듈의 적정성 ③ 교육현장 활용의 용이성
④ 기타 소위원회 상정 안건 ⑤ 총 평. 쪽수·학습 구분 칸이 없으므로 구분은 '심의 항목: …'(총 평은 종합 의견)으로, 차수는 '심의'로 두고,
의견 글에 '학습 N'이 있으면 그 학습으로 범위를 좁힌다. 양식의 PDF는 표 칸을 가를 수 없어 받지 않는다(hwp/hwpx만).
검토의견서와 같은 표에 칸 이름만 '심의의견'인 경우도 읽는다.

의견 항목 = (차수, 구분, 학습 번호, 구성, 쪽, 의견 문장). 판정·유형은 여기서 정하지 않는다.

PDF는 표 구조가 없어 줄만 온다. 실물 의견서(한글 → PDF)에서 본 모양
- 칸 글이 같은 높이면 한 줄로 붙는다: '수행 내용17확대에 따라 …'(구성 + 쪽 + 이어지는 의견), '필요지식 67 -<표 4-1> …'.
- 구분·쪽수 칸 글은 칸 높이의 가운데에 찍혀 의견 줄 사이에 끼어 있다('학습1', '19'). 그래서 쪽·구성 표시는 그 줄이
  속한 의견(바로 앞에서 시작한 의견)에 붙이고, 의견 안에 표시가 없으면 가장 가까운 표시를 쓰되 '추정'으로 남긴다.
- 쪽 숫자가 의견 줄 머리에 붙기도 한다('527701(Privacy)' = 쪽 5 + '27701(Privacy)'). 의견 안에 다른 쪽 표시가 없을 때만,
  앞 의견의 쪽 이상·40쪽 이내인 숫자만 떼어 쓴다.
- 학습 N 칸은 네 구성(필요지식~평가)에 걸친 칸 가운데에 찍힌다. 구성 순서가 되돌아가면(평가 → 필요지식) 다음 학습으로 본다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import OTHER, OVERVIEW, PARTS, PLAN, SUMMARY


@dataclass
class Opinion:
    round: str                    # '1차' | '2차' | '심의' | ''
    source: str                   # 의견서 파일 이름
    group: str                    # 학습모듈 개요 | 학습 N | 기타 | 종합 의견 | 개발계획서 | 심의 항목 이름
    lesson: int | None            # 학습 번호
    part: str | None              # 필요 지식 | 수행 내용 | 교수·학습 방법 | 평가
    page: str | None              # '4', '3-6' — 의견서의 쪽(초고본·완성본 기준)
    text: str
    notes: list[str] = field(default_factory=list)   # 읽으면서 추정한 것(구성·쪽·학습)


@dataclass
class OpinionSheet:
    source: str
    round: str
    module_name: str
    opinions: list[Opinion]


# --- 공통 ---------------------------------------------------------------------

DOT = r"[･·ㆍ・‧∙⋅.]"
PART_PATTERNS = (
    ("필요 지식", re.compile(r"^필요\s*지식(?=\s|\d|-|$)")),
    ("수행 내용", re.compile(r"^수행\s*내용(?=\s|\d|-|$)")),
    ("교수·학습 방법", re.compile(rf"^교수\s*{DOT}?\s*-?\s*학습\s*방법(?=\s|\d|-|$)")),
    ("교수·학습 방법", re.compile(rf"^교수\s*{DOT}\s*학습$")),     # 칸이 좁아 '교수･학습' / '방법' 두 줄로 나뉜 경우
    ("평가", re.compile(r"^평\s*가(?=\s|\d|-|$)")),
)
OVERVIEW_LABEL = re.compile(r"^(학습\s*모듈\s*개요|\(\s*선수\s*학습\s*,\s*내용\s*체계\s*\))")
OTHER_LABEL = re.compile(r"^기타(?=\s|\d|-|$)")
LESSON_LABEL = re.compile(r"^학습\s*(\d{1,2})(?:\s*-\s*\d+)?(?=$|\s*-(?!>)|\s*(?:필요|수행|교수|평\s*가))")
LESSON_CELL = re.compile(r"^학습\s*(\d{1,2})(?:\s*-\s*\d+)?$")
METHOD_TAIL = re.compile(r"^방법$")
TABLE_HEAD = re.compile(r"^구분\s*쪽\s*수\s*(?:검토|심의)\s*의견$")
TITLE = re.compile(r"(?:검토|심의)\s*의견서$")
ROUND = re.compile(r"([1-3])\s*차\s*검토")
DELIBERATION_TITLE = re.compile(r"(?:([1-3])\s*차\s*)?심의\s*의견서")   # 제목 줄·칸: '심의의견서', '2차 심의의견서'
DELIBERATION_CELL = re.compile(r"^(?:([1-3])\s*차\s*)?심의$")              # hwp 표의 차수 칸: '심의', '1차 심의'
DELIBERATION = "심의"
DELIBERATION_HEAD = re.compile(r"^심의\s*항목\s*(?:세분류\s*)?심의\s*의견$")      # F25 표 머리
DELIBERATION_ITEM = re.compile(r"^[①-⑩]\s*")
DELIBERATION_ITEM_PREFIX = "심의 항목: "
MANUSCRIPT_NAME = re.compile(r"학습\s*모듈\s*원고\s*명")
LESSON_IN_TEXT = re.compile(r"학습\s*(\d{1,2})(?!\d)")
MODULE_NAME = re.compile(r"^학습\s*모듈\s*명\s*(.*)$")
HEADER_LINE = re.compile(r"^(세분류\s*명|검토진|심의\s*위원|심의진|학습\s*모듈\s*명)|\(인\)$|(?:검토|심의)\s*의견서$|^검토진$")
NOTE_LINE = re.compile(r"^※")
TABLE_END = re.compile(r"^※\s*학습이\s*추가될")
SUMMARY_HEAD = re.compile(r"^종합\s*의견$")
PLAN_HEAD = re.compile(r"^개발\s*계획서$")
PLAN_TEXT_HEAD = re.compile(r"^(?:검토|심의)\s*의견$")
PAGE_ONLY = re.compile(r"^(\d{1,3}(?:\s*[-~]\s*\d{1,3})?)$")
PAGE_HEAD = re.compile(r"^(\d{1,3}(?:\s*[-~]\s*\d{1,3})?)(?!\d)\s*")
EMPTY_PAGE = re.compile(r"^-(?:\s+(?=-)|\s*$)")
BULLET = re.compile(r"^-(?!>)\s*")
SUB_ITEM = re.compile(r"^[(\[]?\s*(?:수정|변경)\s*[전후]\s*[)\]]?\s*[:：]")
NOT_OPINION = re.compile(r"^[-\s]*((의견\s*)?없음)?[.\s]*$")
PAGE_CELL = re.compile(r"^\d{1,3}(?:\s*(?:[-~,]|\s)\s*\d{1,3})*$")   # hwp 쪽수 칸: '3-6', '5 9', '51~56 60'


def clean(text: str) -> str:
    """공백 정리 + 짝 잃은 서로게이트(일부 hwp 글꼴 문자) 정리 — JSON으로 내보낼 수 있게."""
    text = str(text).encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    return " ".join(text.split())


def join_lines(lines: list[str]) -> str:
    """PDF 칸 안에서 줄이 바뀐 글을 잇는다. 실물 의견서는 글자 단위로 줄을 나눠('추'/'가되면', '라'/'이선스')
    한글끼리 맞닿은 줄 바꿈은 붙이고, 그 밖에는 띄운다."""
    out = ""
    for line in (l.strip() for l in lines):
        if not line:
            continue
        if out and re.search(r"[가-힣]$", out) and re.match(r"[가-힣]", line):
            out += line
        else:
            out = f"{out} {line}" if out else line
    return out


def is_opinion(text: str) -> bool:
    return not NOT_OPINION.match(text)


def norm_part(label: str) -> str | None:
    for name, pattern in PART_PATTERNS:
        if pattern.match(label.strip()):
            return name
    return None


def sub_item(text: str) -> bool:
    """앞 의견에 딸린 '-' 줄인가 — '수정전: …'·'수정 후: …'처럼 앞 문장이 든 고칠 문장의 전후 예시."""
    return bool(SUB_ITEM.match(BULLET.sub("", text.strip(), count=1)))


def split_bullets(text: str) -> list[str]:
    """한 칸 글 → '-'로 시작하는 의견들. '-'가 없으면 통째로 한 의견. '교수-학습', '->'는 나누지 않는다.
    '- 수정전: …', '- 수정후: …' 줄은 따로 의견이 아니라 앞 의견에 붙인다(실물 1차 의견서의 개발계획서 칸 — 한 의견이 셋으로 읽혔다)."""
    text = " ".join(text.split())
    parts = re.split(r"(?:^|\s)-(?!>)\s*(?=\S)", text)
    out: list[str] = []
    for part in (p.strip() for p in parts):
        if not part:
            continue
        if out and sub_item(part):
            out[-1] = f"{out[-1]} - {part}"
        else:
            out.append(part)
    return [p for p in out if is_opinion(p)]


def _round(text: str) -> str:
    """제목 줄·차수 칸 → '1차'·'2차'(검토), '심의'·'N차 심의'(심의의견서). 아니면 ''."""
    match = ROUND.search(text)
    if match:
        return f"{match.group(1)}차"
    match = DELIBERATION_TITLE.search(text) or DELIBERATION_CELL.match(text.strip())
    if match:
        return f"{match.group(1)}차 {DELIBERATION}" if match.group(1) else DELIBERATION
    return ""


# --- PDF 줄 -------------------------------------------------------------------

@dataclass
class _Item:
    start: int
    lines: list[str]
    last: int
    glued_page: str | None = None


@dataclass
class _Event:
    line: int
    kind: str              # 'part' | 'lesson' | 'page'
    value: object
    closed: bool = False   # 한 줄로 끝난 칸('평가 - -', '수행 내용 - -의견없음') — 뒤 의견을 이 칸에 붙이지 않는다


REF = re.compile(r"[<\[〈]\s*(표|그림)\s*(\d+)\s*-\s*(\d+)\s*[>\]〉]")
SENTENCE_END = re.compile(r"(됨|음|임|함|다|요|짐|\.|\))$")
PAGE_BULLET = re.compile(r"^(\d{1,3})\s+(?=-(?!>))")


def _strip_labels(line: str) -> tuple[str, list[tuple[str, int | None]]]:
    """줄 머리의 구분 표시(개요·구성·기타·학습 N)를 떼어 낸다 → (나머지, [(종류, 학습 번호)])."""
    found: list[tuple[str, int | None]] = []
    for _ in range(3):
        if (m := OVERVIEW_LABEL.match(line)):
            found.append((OVERVIEW, None))
            line = line[m.end():].strip()
            continue
        if (m := LESSON_LABEL.match(line)):
            found.append(("학습", int(m.group(1))))
            line = line[m.end():].strip()
            continue
        if (m := OTHER_LABEL.match(line)):
            found.append((OTHER, None))
            line = line[m.end():].strip()
            continue
        part = None
        for name, pattern in PART_PATTERNS:
            if (m := pattern.match(line)):
                part = name
                line = line[m.end():].strip()
                break
        if part:
            found.append((part, None))
            continue
        break
    return line, found


def _glued_page(line: str, last_page: int) -> tuple[str | None, str]:
    """의견 줄 머리에 붙은 쪽 숫자('527701(…)' → '5')를 찾는다. 앞 의견의 쪽 이상·40쪽 이내만."""
    match = re.match(r"^(\d+)", line)
    if not match:
        return None, line
    run = match.group(1)
    if len(run) <= 3 and len(line) > len(run) and not line[len(run)].isdigit():
        candidate = run
    elif 6 <= len(run) <= 8:
        candidate = run[:-5]
    else:
        return None, line
    if not last_page <= int(candidate) <= last_page + 40:
        return None, line
    return candidate, line[len(candidate):].strip()


def _page_number(page: str | None) -> int | None:
    match = re.match(r"\d+", page or "")
    return int(match.group(0)) if match else None


def _table_items(lines: list[str], source: str, round_: str) -> list[Opinion]:
    """표 부분(구분 쪽수 검토의견 ~ ※ 학습이 추가될 …)의 줄 → 의견 목록."""
    items: list[_Item] = []
    events: list[_Event] = []
    current: _Item | None = None
    last_page = 0
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line or TABLE_HEAD.match(line) or HEADER_LINE.search(line) or NOTE_LINE.match(line):
            continue
        rest, labels = _strip_labels(line)
        new = [_Event(index, "lesson" if kind == "학습" else "part", number if kind == "학습" else kind) for kind, number in labels]
        events += new
        if METHOD_TAIL.match(rest):
            events.append(_Event(index, "part", "교수·학습 방법"))
            continue
        page, empty_row = None, False
        if (m := PAGE_BULLET.match(rest)):
            page, rest = m.group(1), rest[m.end():]
        elif labels or PAGE_ONLY.match(rest):
            if (m := EMPTY_PAGE.match(rest)) and labels:
                rest, empty_row = rest[m.end():].strip(), True
            elif (m := PAGE_HEAD.match(rest)):
                page = m.group(1).replace(" ", "")
                rest = rest[m.end():].strip()
        if page:
            events.append(_Event(index, "page", page))
            last_page = max(last_page, _page_number(page) or 0)
        if labels and (empty_row or (rest and not is_opinion(rest))):
            for event in new:
                event.closed = True
            continue
        if not rest:
            continue
        starts_ref = REF.match(rest) and current is not None and SENTENCE_END.search(current.lines[-1])
        if (BULLET.match(rest) and not (current is not None and sub_item(rest))) or current is None or starts_ref:
            current = _Item(index, [BULLET.sub("", rest, count=1)], index)
            items.append(current)
            continue
        if not labels and current.glued_page is None and not any(e.kind == "page" and e.line >= current.start for e in events):
            glued, stripped = _glued_page(rest, last_page)
            if glued:
                current.glued_page, rest = glued, stripped
                last_page = max(last_page, int(glued))
        current.lines.append(rest)
        current.last = index
    return _assign(items, events, len(lines), source, round_)


def _merge_parts(events: list[_Event]) -> list[_Event]:
    """같은 구성 표시가 2줄 안에 다시 나오면(두 줄로 나뉜 칸) 하나로."""
    parts: list[_Event] = []
    for event in events:
        if event.kind != "part":
            continue
        if parts and parts[-1].value == event.value and event.line - parts[-1].line <= 2:
            parts[-1].closed = parts[-1].closed and event.closed
            continue
        parts.append(event)
    return parts


def _blocks(parts: list[_Event]) -> list[int]:
    """구성 표시마다 학습 묶음 번호. 개요·기타는 묶음 밖(-1). 구성 순서가 되돌아가면 새 묶음."""
    order = {name: i for i, name in enumerate(PARTS)}
    block, previous, out = -1, None, []
    for event in parts:
        if event.value not in order:
            out.append(-1)
            previous = None
            continue
        if previous is None or order[event.value] <= previous:
            block += 1
        previous = order[event.value]
        out.append(block)
    return out


def _block_lessons(parts: list[_Event], blocks: list[int], events: list[_Event]) -> dict[int, tuple[int, bool]]:
    """묶음 → (학습 번호, 표시를 읽었나). 묶음의 구성 표시 줄 범위에 가장 가까운 '학습 N' 표시, 없으면 앞 묶음 + 1."""
    lessons = [e for e in events if e.kind == "lesson"]
    spans: dict[int, list[int]] = {}
    for event, block in zip(parts, blocks):
        if block >= 0:
            spans.setdefault(block, []).append(event.line)
    out: dict[int, tuple[int, bool]] = {}
    used: set[int] = set()
    for block, lines_ in sorted(spans.items()):
        low, high = min(lines_), max(lines_)
        best = min(((max(low - e.line, e.line - high, 0), i) for i, e in enumerate(lessons) if i not in used), default=None)
        if best is not None and best[0] <= max(6, high - low + 2):
            used.add(best[1])
            out[block] = (int(lessons[best[1]].value), True)
        else:
            before = out.get(block - 1)
            out[block] = ((before[0] + 1) if before else 1, False)
    return out


def _nearest_part(item: _Item, parts: list[_Event]) -> int | None:
    """의견 안에 구성 표시가 없을 때: 가장 가까운 열린 칸(한 줄로 끝난 칸 제외). 거리가 같으면 앞 칸."""
    best = None
    for i, event in enumerate(parts):
        if event.closed:
            continue
        distance = item.start - event.line if event.line < item.start else event.line - item.last
        key = (distance, event.line > item.start)
        if best is None or key < best[0]:
            best = (key, i)
    return best[1] if best else None


def _assign(items: list[_Item], events: list[_Event], n_lines: int, source: str, round_: str) -> list[Opinion]:
    parts = _merge_parts(events)
    blocks = _blocks(parts)
    block_lesson = _block_lessons(parts, blocks, events)
    pages = [e for e in events if e.kind == "page"]
    out = []
    for position, item in enumerate(items):
        end = items[position + 1].start - 1 if position + 1 < len(items) else n_lines - 1
        notes = []
        inside = [i for i, e in enumerate(parts) if item.start <= e.line <= end and not e.closed]
        k = inside[0] if inside else _nearest_part(item, parts)
        if not inside and k is not None:
            notes.append("구성: 표 위치로 추정")
        label = parts[k].value if k is not None else None
        block = blocks[k] if k is not None else -1
        page_inside = [e.value for e in pages if item.start <= e.line <= end]
        if page_inside:
            page = page_inside[0]
        elif item.glued_page:
            page = item.glued_page
            notes.append("쪽: 의견 줄 머리에 붙은 숫자로 추정")
        else:
            near = [(abs(e.line - item.start), e.value) for e in pages if k is not None and _cell_of(e.line, parts) == k]
            page = min(near)[1] if near else None
            if page:
                notes.append("쪽: 같은 칸의 가장 가까운 쪽 표시로 추정")
        text = join_lines(item.lines)
        if not is_opinion(text):
            continue
        ref = REF.search(text)
        lesson, part = None, None
        if label in PARTS:
            lesson, known = block_lesson.get(block, (None, False))
            part = label
            if not known:
                notes.append("학습 번호: 표시가 없어 순서로 추정")
        if ref and label != OTHER and int(ref.group(2)) != lesson:
            notes.append(f"학습 번호: {ref.group(0)}의 번호로 정함")
            lesson = int(ref.group(2))
            if label == OVERVIEW or label is None:
                label, part = "학습", None
        if label in PARTS or label == "학습":
            group = f"학습 {lesson}" if lesson else "학습"
        elif label == OTHER:
            group = OTHER
        else:
            group = OVERVIEW
            if label is None:
                notes.append("구분을 읽지 못함")
        out.append(Opinion(round_, source, group, lesson if group.startswith("학습") else None, part, page, text, notes))
    return out


def _cell_of(line: int, parts: list[_Event]) -> int | None:
    """줄이 속한(가장 가까운) 구성 표시 번호."""
    if not parts:
        return None
    return min(range(len(parts)), key=lambda i: abs(parts[i].line - line))


def _block_text(lines: list[str]) -> list[str]:
    """종합 의견·개발계획서 칸 글 → 의견들('-' 줄이 있으면 그 단위, 없으면 통째로)."""
    body = [l.strip() for l in lines if l.strip() and not NOTE_LINE.match(l.strip()) and not PLAN_HEAD.match(l.strip())]
    if not body:
        return []
    if not any(BULLET.match(l) for l in body):
        return [t for t in [join_lines(body)] if is_opinion(t)]
    items: list[list[str]] = []
    for line in body:
        if items and sub_item(line):
            items[-1].append(line)
        elif BULLET.match(line) or not items:
            items.append([BULLET.sub("", line, count=1)])
        else:
            items[-1].append(line)
    return [t for t in (join_lines(i) for i in items) if is_opinion(t)]


def parse_lines(lines: list[str], source: str = "", round_: str = "") -> OpinionSheet:
    """의견서 PDF의 줄(위에서 아래, 여러 쪽을 이어 붙임) → OpinionSheet."""
    lines = [clean(l) for l in lines]
    round_ = next((_round(l) for l in lines[:6] if _round(l)), "") or round_   # 제목의 'N차 검토' 표기가 지정 차수보다 앞선다
    module = next((MODULE_NAME.match(l).group(1).strip() for l in lines if MODULE_NAME.match(l)), "")
    head = next((i for i, l in enumerate(lines) if TABLE_HEAD.match(l)), None)
    if head is None and any(DELIBERATION_TITLE.search(l) or DELIBERATION_HEAD.match(l) for l in lines):
        raise ValueError(f"심의의견서는 hwp, hwpx 파일로 올려 주세요. PDF에서는 표 칸(심의 항목, 세분류, 심의 의견)을 가를 수 없습니다: {source}")
    if head is None:
        raise ValueError(f"의견서 표(구분, 쪽수, 검토의견 또는 심의의견)를 찾지 못했습니다: {source}")
    end = next((i for i in range(head, len(lines)) if TABLE_END.match(lines[i]) or SUMMARY_HEAD.match(lines[i])), len(lines))
    opinions = []
    plan_start = next((i for i in range(head) if PLAN_TEXT_HEAD.match(lines[i])), None)
    if plan_start is not None:
        plan_lines = [l for l in lines[plan_start + 1:head] if not NOTE_LINE.match(l)]
        opinions += [Opinion(round_, source, PLAN, None, None, None, t) for t in _block_text(plan_lines)]
    opinions += _table_items(lines[head + 1:end], source, round_)
    summary = next((i for i in range(end, len(lines)) if SUMMARY_HEAD.match(lines[i])), None)
    if summary is not None:
        tail = []
        for l in lines[summary + 1:]:
            if NOTE_LINE.match(l):
                break
            tail.append(l)
        opinions += [Opinion(round_, source, SUMMARY, None, None, None, t) for t in _block_text(tail)]
    return OpinionSheet(source, round_, module, opinions)


# --- hwp/hwpx 표 ----------------------------------------------------------------

def parse_tables(tables: list[dict], source: str = "", round_: str = "") -> OpinionSheet:
    """의견서 hwp/hwpx의 표(ncs_core Document.tables, 문서 순서) → OpinionSheet. 쪽을 넘긴 표는 이어서 읽는다.

    round_(지정 차수)는 'N차 검토' 표기가 없는 표에만 쓴다 — 실물 2차 의견서 파일에는 1차 표가 함께 들어 있어, 지정 차수를
    앞세우면 그 1차 의견이 '2차'로 붙어 1차 파일의 같은 의견과 겹쳐 세어진다. 결과의 차수는 지정 차수(없으면 마지막 표의 표기)."""
    rows: list[list[str]] = []
    for table in tables:
        by_row: dict[int, list[tuple[int, str]]] = {}
        for (r, c), text in table["cells"].items():
            by_row.setdefault(r, []).append((c, clean(text)))
        rows += [[t for _, t in sorted(cells)] for _, cells in sorted(by_row.items())]
    fixed_round = round_
    module = ""
    for row in rows:
        if row and MODULE_NAME.match(row[0]):
            module = (MODULE_NAME.match(row[0]).group(1) or (row[1] if len(row) > 1 else "")).strip()
            break
    if not module:      # F25: '학습모듈 원고명' 칸 아래 줄의 마지막 칸
        for i, row in enumerate(rows[:-1]):
            if any(MANUSCRIPT_NAME.search(c) for c in row):
                module = next((c for c in reversed(rows[i + 1]) if c), "")
                break
    opinions: list[Opinion] = []
    state = "head"
    lesson: int | None = None
    width = 0
    for row in rows:
        cells = [c for c in row if c]
        if not cells:
            continue
        first = cells[0]
        if DELIBERATION_HEAD.match(" ".join(cells)):
            round_, state, width = DELIBERATION, "deliberation", len(row)      # 심의의견서 표는 지정 차수와 관계없이 '심의'
            continue
        if state == "deliberation" and not DELIBERATION_TITLE.search(first):
            if not NOTE_LINE.match(first):
                opinions += _deliberation_row(row, width, round_, source)
            continue
        if ROUND.match(first) or DELIBERATION_CELL.match(first) or DELIBERATION_TITLE.search(first):
            # 2차 의견서 파일 안에 1차 의견서 표가 앞에 함께 든 경우가 있다 → 표마다 차수를 다시 읽는다(심의의견서도 같다)
            read = _round(first)                    # 표의 'N차 검토' 표기가 지정 차수보다 앞선다
            if read == DELIBERATION and DELIBERATION in (fixed_round or ""):
                read = fixed_round                  # 표에는 '심의'뿐이고 밖에서 'N차 심의'로 정했으면 그 차수(더 자세한 쪽)
            round_, state = read or fixed_round, "head"
            continue
        if HEADER_LINE.search(first):
            continue
        if TABLE_HEAD.match(" ".join(cells)) or (first == "구분" and any(k in c.replace(" ", "") for c in cells for k in ("검토의견", "심의의견"))):
            state = "table"
            continue
        if PLAN_HEAD.match(first):
            state = "plan"
            continue
        if SUMMARY_HEAD.match(first):
            state = "summary"
            rest = cells[1:]
            opinions += [Opinion(round_, source, SUMMARY, None, None, None, t) for c in rest for t in split_bullets(c)]
            continue
        if NOTE_LINE.match(first):
            if state == "plan":
                state = "head"
            continue
        if state == "plan":
            texts = [c for c in cells if not PLAN_TEXT_HEAD.match(c)]
            opinions += [Opinion(round_, source, PLAN, None, None, None, t) for c in texts for t in split_bullets(c)]
            continue
        if state == "summary":
            opinions += [Opinion(round_, source, SUMMARY, None, None, None, t) for c in cells for t in split_bullets(c)]
            continue
        if state != "table":
            continue
        group, part, page, texts = None, None, None, []
        for cell in cells:
            if (m := LESSON_CELL.match(cell)) and group is None:
                lesson = int(m.group(1))
                group = f"학습 {lesson}"
            elif OVERVIEW_LABEL.match(cell) and group is None:
                group, lesson = OVERVIEW, None
            elif OTHER_LABEL.match(cell) and group is None and len(cell) <= 3:
                group, lesson = OTHER, None
            elif part is None and norm_part(cell) and len(cell) <= 12:
                part = norm_part(cell)
            elif page is None and not texts and (PAGE_CELL.match(cell) or cell == "-"):
                page = None if cell == "-" else re.sub(r"\s*,\s*|\s+", ",", re.sub(r"\s*([-~])\s*", r"\1", cell))
            else:
                texts.append(cell)
        if group is None:
            group = f"학습 {lesson}" if (part and lesson) else OTHER if not part else "학습"
        for text in texts:
            for t in split_bullets(text):
                opinions.append(Opinion(round_, source, group, lesson if group.startswith("학습") else None,
                                        part, page, t))
    if state == "head" and not opinions:      # 심의의견서 표(F25)는 의견 칸이 비어 있어도 읽은 것으로 본다
        raise ValueError(f"의견서 표(구분, 쪽수, 검토의견 또는 심의의견)를 찾지 못했습니다: {source}")
    return OpinionSheet(source, round_ if state == "deliberation" else (fixed_round or round_), module, opinions)


GUIDE_LINE = re.compile(r"^\s*(※|\*|\(?\s*(작성\s*(요령|방법|예시)|예시\s*\)))")


def _deliberation_row(row: list[str], width: int, round_: str, source: str) -> list[Opinion]:
    """F25 표의 한 줄(심의 항목 | 세분류 | 심의 의견) → 의견들. ④·⑤처럼 세분류 칸이 없는(합쳐진) 줄은 항목 뒤가 모두 의견이다."""
    label = DELIBERATION_ITEM.sub("", row[0]).strip()
    rest = row[1:]
    has_subclass = len(row) >= width and len(rest) > 1
    subclass = rest[0] if has_subclass else ""
    group = SUMMARY if re.search(r"총\s*평", label) else DELIBERATION_ITEM_PREFIX + label
    out = []
    for cell in (rest[1:] if has_subclass else rest):
        for text in split_bullets(cell):
            if GUIDE_LINE.match(text):          # 양식의 안내 줄(※ 작성 요령 …)은 의견이 아니다
                continue
            notes = [f"세분류: {subclass}"] if subclass else []
            match = LESSON_IN_TEXT.search(text) if group != SUMMARY else None
            if match:
                notes.append(f"학습 번호: 의견 글의 '학습 {match.group(1)}'로 정함")
            out.append(Opinion(round_, source, group, int(match.group(1)) if match else None, None, None, text, notes))
    return out


def flipped(lines: list[str]) -> bool:
    """PDF 첫 쪽의 줄 순서가 아래→위로 뒤집혔는가(실물 의견서 PDF는 좌표계가 뒤집혀 있어 ncs_core.pdf가 거꾸로 낸다).
    제목('… 검토의견서')·표 머리가 '※ …'·종합 의견보다 뒤에 있으면, 그것이 없으면 제목이 뒤쪽 절반에 있으면 뒤집힌 것으로 본다."""
    title = next((i for i, l in enumerate(lines) if TITLE.search(l)), None)
    if title is None:
        title = next((i for i, l in enumerate(lines) if TABLE_HEAD.match(" ".join(l.split()))), None)
    tail = next((i for i, l in enumerate(lines) if SUMMARY_HEAD.match(l.strip()) or l.strip().startswith("※ 형식적")), None)
    if tail is None:
        tail = next((i for i, l in enumerate(lines) if l.strip().startswith("※")), None)
    if title is None:
        return False
    if tail is not None:
        return title > tail
    return title > len(lines) / 2
