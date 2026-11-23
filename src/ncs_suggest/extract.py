"""원고에서 추천 대상 문장 모으기 — 종결 규정이 있는 자리만, 구성 순서대로. 판정은 하지 않는다(I/O 없음).

  학습모듈의 개요  학습모듈의 목표(학습 목표)                       ← ncs_core.manuscript.parse_overview
  차례            학습명(학습명) · 학습 내용명(학습 내용명)            ← parse_toc
  필요 지식        학습 내용(N-M)별 '학습 목표' 문장(학습 목표)         ← parse_body + unit_regions
  수행 내용        수행 내용 제목 · 수행 순서 네모 번호 줄([1] …)       ← 이 모듈(아래)
  교수·학습 방법   교수 방법 · 학습 방법 글머리 항목                    ← 이 모듈(아래)
  평가            평가 방법 표(학습 내용 | 평가 항목 | 성취수준)의 평가 항목
수행 내용·교수·학습 방법 블록 읽기는 ncs_perform.blocks·ncs_teaching.blocks와 같은 양식 가정을 줄여 옮긴 것이다
(기능 패키지는 검수 엔진을 import하지 않는다 — tests/contract/test_layering.py). 코어로 올리는 것은 팀장 요청 이슈.
수행 순서는 엔진처럼 네모 번호(수준 1) 줄만 본다 — 하위 번호·설명 문단은 종결 규정이 없다.
수행 내용 제목·수행 순서 문장에는 같은 학습 내용(N-M)의 학습 목표 본문을 goals로 싣는다 — AI가 낱말을 고를 때 볼 문맥이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ncs_core import Document, visible
from ncs_core.manuscript import parse_body, parse_overview, parse_toc, unit_regions

PERFORM_HEAD = re.compile(r"^수행\s*내용(?:\s*(\d+))?$")
UNIT_HEAD = re.compile(r"^(\d+)\s*-\s*(\d+)\s*\.\s*(.*)$")
SUBHEAD = {"재료": re.compile(r"^재\s*료"), "기기": re.compile(r"^기\s*기"), "안전": re.compile(r"^안\s*전"),
           "수행순서": re.compile(r"^수\s*행\s*순\s*서$")}
TEACH_HEAD = re.compile(r"^교수\s*\W{0,3}\s*학습\s*방법$")
TEACH_PARTS = (("교수 방법", re.compile(r"^교수\s*방법$")), ("학습 방법", re.compile(r"^학습\s*방법$")))
LESSON_LINE = re.compile(r"^학습\s*(\d+)(?:\s*[.．]?\s*(\S.*))?$")
EVAL_HEAD = re.compile(r"^평\s*가$")
BOX_NUMBER = re.compile(r"^[\U000F02B0-\U000F02CF]")
BULLET_TEXT = re.compile(r"^[•·▪ㆍ‧◦○\-–]\s*")
MEMO = re.compile(r"^[★▶※]|要")
SURROGATE_PAIR = re.compile("[\ud800-\udbff][\udc00-\udfff]")
PREFIX = re.compile(r"^(?:[\U000F02B0-\U000F02CF]|[•·▪ㆍ‧◦○\-–]|\(?\d{1,2}[.)]|[①-⑳]|[가-하]\))\s*")


@dataclass(frozen=True)
class Sentence:
    kind: str          # config.KINDS의 이름
    part: str          # 구성(학습모듈의 개요 · 차례 · 필요 지식 · 수행 내용 · 교수·학습 방법 · 평가)
    where: str         # 사람이 찾아갈 자리
    text: str          # 원문 그대로(번호 포함)
    prefix: str        # 앞 번호·글머리(보이는 글자)
    body: str          # 번호 뗀 본문 — 추천은 여기에 한다
    before: str = ""   # 앞 문단(AI 후보 문맥)
    after: str = ""    # 뒤 문단
    goals: tuple[str, ...] = ()   # 그 문장이 속한 학습 내용(N-M)의 학습 목표 본문 — 수행 내용 제목·수행 순서에만(문맥)


def join_surrogates(text: str) -> str:
    """hwp 본문에서 갈라져 온 서로게이트 쌍(네모 번호 글자)을 한 글자로 합친다."""
    return SURROGATE_PAIR.sub(lambda m: m.group().encode("utf-16-le", "surrogatepass").decode("utf-16-le"), text or "")


def split_prefix(text: str) -> tuple[str, str]:
    """'[1] 요구사항을 확인한다.' → ('[1]', '요구사항을 확인한다.'). 번호·글머리가 없으면 ('', 원문)."""
    text = join_surrogates(text).strip()
    m = PREFIX.match(text)
    if not m:
        return "", text
    return visible(m.group(0).strip()), text[m.end():].strip()


def _sentence(kind, part, where, text, before="", after="", goals=()) -> Sentence:
    prefix, body = split_prefix(text)
    return Sentence(kind, part, where, visible(join_surrogates(text)), prefix, body, visible(before)[:400], visible(after)[:400], tuple(goals))


def _list(kind, part, where_of, items: list[str], goals=()) -> list[Sentence]:
    return [_sentence(kind, part, where_of(n), t, items[n - 1] if n > 0 else "", items[n + 1] if n + 1 < len(items) else "", goals)
            for n, t in enumerate(items)]


def perform_blocks(paragraphs: list[str], styles: list[str] | None, in_table: frozenset[int], aside: frozenset[int]) -> list[dict]:
    """수행 내용 블록 → [{'unit','no','title','title_idx','steps':[(idx, text)]}] (ncs_perform.blocks의 줄인 꼴)."""
    texts = [join_surrogates(t).strip() for t in paragraphs]
    heads = [i for i, t in enumerate(texts) if PERFORM_HEAD.match(t) and i not in aside]
    out = []
    for n, head in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(texts)
        for j in range(head + 1, end):
            if j not in aside and (TEACH_HEAD.match(texts[j]) or EVAL_HEAD.match(texts[j])
                                   or (UNIT_HEAD.match(texts[j]) and len(texts[j]) < 60 and not re.search(r"\s\d+$", texts[j]))):
                end = j
                break
        marks = [(j, key) for j in range(head + 1, end) if j not in aside and j not in in_table and len(texts[j]) <= 20
                 for key, pattern in SUBHEAD.items() if pattern.match(texts[j])]
        if not marks:
            continue    # 소제목이 하나도 없으면 본문 표의 열 제목 '수행 내용'이다
        unit = next((f"{m.group(1)}-{m.group(2)}" for j in range(head - 1, -1, -1)
                     if (m := UNIT_HEAD.match(texts[j])) and len(texts[j]) < 60 and not re.search(r"\s\d+$", texts[j])), "?")
        title_idx = next((j for j in range(head + 1, min(head + 6, marks[0][0])) if texts[j] and j not in aside
                          and not re.fullmatch(r"[/／|│]+", texts[j])), None)
        steps = []
        for order, (j, key) in enumerate(marks):
            if key != "수행순서":
                continue
            stop = marks[order + 1][0] if order + 1 < len(marks) else end
            for k in range(j + 1, stop):
                if k in aside or k in in_table or not texts[k]:
                    continue
                style = (styles[k] if styles and k < len(styles) else "") or ""
                level1 = (style.startswith("\U000F02B1") and "제목" in style) if style else bool(BOX_NUMBER.match(texts[k]))
                if level1:
                    steps.append((k, texts[k]))
        number = PERFORM_HEAD.match(texts[head]).group(1)
        out.append({"unit": unit, "no": number, "title": texts[title_idx] if title_idx is not None else "", "title_idx": title_idx,
                    "steps": steps})
    return out


def teaching_items(paragraphs: list[str], styles, numbers, in_table: frozenset[int], aside: frozenset[int]) -> list[dict]:
    """교수·학습 방법 블록 → [{'lesson'(순번), '교수 방법': [text], '학습 방법': [text]}] (ncs_teaching.blocks의 줄인 꼴)."""
    blocks, current, part = [], None, None
    for i, raw in enumerate(paragraphs):
        text = (raw or "").strip()
        if not text:
            continue
        if TEACH_HEAD.match(text):
            current = {"lesson": len(blocks) + 1, "교수 방법": [], "학습 방법": []}
            blocks.append(current)
            part = None
            continue
        if current is None:
            continue
        if EVAL_HEAD.match(text) or (LESSON_LINE.match(text) and i not in in_table):
            current, part = None, None
            continue
        if i in in_table or i in aside or MEMO.search(text):
            continue
        matched = next((name for name, pattern in TEACH_PARTS if pattern.match(text)), None)
        if matched:
            part = matched
            continue
        bullet = BULLET_TEXT.match(text) or (numbers and i < len(numbers) and numbers[i]) or (styles and i < len(styles) and "불릿" in (styles[i] or ""))
        if part and bullet:
            current[part].append(text)
    return blocks


def eval_items(document: Document, section: int) -> list[tuple[str, str]]:
    """평가 방법 표(머리 '학습 내용 | 평가 항목')의 (학습 내용, 평가 항목) 목록. 학습 내용 칸이 비면 위 칸을 잇는다."""
    out = []
    for table in document.section_tables(section):
        cells = table["cells"]
        if re.sub(r"\s", "", cells.get((0, 0), "")) != "학습내용" or re.sub(r"\s", "", cells.get((0, 1), "")) != "평가항목":
            continue
        name = ""
        for row in range(1, table["rows"]):
            name = cells.get((row, 0), "").strip() or name
            item = cells.get((row, 1), "").strip()
            if item and item not in ("상", "중", "하"):
                out.append((name, item))
    return out


def collect(document: Document) -> list[Sentence]:
    """원고 → 추천 대상 문장(구성 순서). 구역 0 = 앞부분, 1 = 본문(ncs_core.documents.normalize_sections)."""
    sentences: list[Sentence] = []
    overview = parse_overview(document, 0)
    if overview.get("목표"):
        sentences.append(_sentence("학습 목표", "학습모듈의 개요", "학습모듈의 목표", overview["목표"]["text"]))
    toc = parse_toc(document.sections) or {"학습": [], "내용": []}
    sentences += [_sentence("학습명", "차례", f"차례 학습 {item['no']}", item["text"]) for item in toc["학습"]]
    sentences += [_sentence("학습 내용명", "차례", f"차례 {item['no']}-{item['sub']}", item["text"]) for item in toc["내용"]]
    if len(document.sections) < 2:
        return sentences
    in_table = document.section_table_paragraphs(1) or frozenset()
    aside = document.section_aside_paragraphs(1) or frozenset()
    styles = document.section_styles(1)
    body = parse_body(document.sections, max(1, len(toc["학습"])), table_paragraphs=in_table, aside_paragraphs=aside, styles=styles)
    unit_goals: dict[str, tuple[str, ...]] = {}      # '1-2' → 그 학습 내용의 학습 목표 본문들(수행 내용 문장의 문맥)
    for unit in unit_regions(body):
        goals = unit["goal"]
        sentences += _list("학습 목표", "필요 지식", lambda n, u=unit: f"{u['no']}-{u['sub']} 학습 목표 {n + 1}", goals)
        unit_goals[f"{unit['no']}-{unit['sub']}"] = tuple(body for goal in goals if (body := split_prefix(goal)[1]))   # 글머리만 있는 빈 줄은 뺀다
    paragraphs = document.sections[1]
    for block in perform_blocks(paragraphs, styles, in_table, aside):
        where = f"{block['unit']} 수행 내용{(' ' + block['no']) if block['no'] else ''}"
        goals = unit_goals.get(block["unit"], ())
        if block["title"]:
            sentences.append(_sentence("수행 내용 제목", "수행 내용", f"{where} 제목", block["title"], goals=goals))
        steps = [text for _, text in block["steps"]]
        sentences += _list("수행 순서", "수행 내용", lambda n, w=where: f"{w} 수행 순서 {n + 1}", steps, goals)
    for block in teaching_items(paragraphs, styles, document.section_numbers(1), in_table, aside):
        for part in ("교수 방법", "학습 방법"):
            sentences += _list(part, "교수·학습 방법", lambda n, b=block, p=part: f"학습 {b['lesson']} {p} {n + 1}", block[part])
    items = eval_items(document, 1)
    sentences += _list("평가 항목", "평가", lambda n: f"평가 표 {items[n][0] or '?'} · 평가 항목 {n + 1}", [item for _, item in items])
    return sentences


def verbs_in(document: Document) -> frozenset[str]:
    """원고 전체에서 'W한다'·'W하도록'·'W하여야'로 쓰인 한글 낱말 W(두 글자 이상) — 목록에 없는 행동명사를 원고 용례로 받는다."""
    words = set()
    for section in document.sections:
        for line in section:
            words.update(re.findall(r"(?<![가-힣])([가-힣]{2,6})(?:한다|하도록|하여야|해야\s*한다)(?![가-힣])", line))
    return frozenset(words)
