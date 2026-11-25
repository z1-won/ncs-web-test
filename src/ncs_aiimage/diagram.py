"""도표·표의 명세(REQ-02-006 ① AI 생성) — 생성형 AI는 그림이 아니라 이 명세(JSON)를 쓰고, 그림은 draw.py가 그린다.

명세의 모양(kind마다 쓰는 칸이 다르다):
  sequence  순서      items: [{label, note?}]                 2~8칸, 앞에서 뒤로 화살표
  cycle     순환      items: [{label, note?}]                 3~6칸, 마지막에서 처음으로 돌아온다
  structure 구성      root: 맨 위 칸의 이름, items: [{label, children?: [글]}]   2~6갈래
  compare   비교      items: [{label, children: [글]}]        2~4열, 열마다 1~6줄
  table     표        header: [글], rows: [[글]]              2~6열, 1~10행
  title은 그림 안에 그리지 않는다. 원고의 그림 제목 줄('[그림 1-1] …', '<표 1-1> …')에 쓸 글이다.

두 가지를 따로 본다.
  read_spec  모양 — 칸 수, 글 길이, 겹치는 이름. 어기면 SpecError(그릴 수 없다). 사람이 고친 명세도 이 검사는 거친다.
  grounding  근거 — 명세의 글이 집필자가 쓴 글(문단, 수행준거)에 있는 말인가. 새 수치·영문·상표가 들어왔는가.
             생성형 AI가 낸 후보는 지적이 하나라도 있으면 쓰지 않는다(candidates). 사람이 고친 명세에는 알림으로만 쓴다.
낱말 대조는 형태소 분석이 아니라 어림이다: 낱말에서 조사·어미를 떼어 가며 글(띄어쓰기 없앤 것)에 있는지 본다.
"""

import re
from dataclasses import dataclass, field

from ncs_core.brands import find_brands

KINDS = ("sequence", "cycle", "structure", "compare", "table")
KIND_NAMES = {"sequence": "순서", "cycle": "순환", "structure": "구성", "compare": "비교", "table": "표"}
ITEM_RANGE = {"sequence": (2, 8), "cycle": (3, 6), "structure": (2, 6), "compare": (2, 4)}
MAX_TITLE = 40
MAX_LABEL = 24
MAX_NOTE = 40
MAX_CHILDREN = 6
MAX_CHILD = 40
COLUMN_RANGE = (2, 6)
ROW_RANGE = (1, 10)
MAX_CELL = 60
MAX_CANDIDATES = 3

# 그림의 틀을 이루는 말 — 글에 없어도 받는다(대상·사실을 더하지 않는 말)
FRAME_WORDS = frozenset("절차 과정 단계 순서 흐름 구성 구조 체계 비교 구분 종류 유형 항목 내용 특징 차이 요소 개요 예시 관계 분류 기준 순환 표 도표 "
                        "비고 및 등 또는 그리고 와 과 의 대 별 간 후 전 중 시 내 외".split())
SUFFIXES = ("으로부터", "에서는", "으로써", "으로서", "에서의", "이라는", "하도록", "하면서", "에서", "으로", "에게", "까지", "부터", "하여", "하고", "하는",
            "한다", "하며", "하기", "되는", "된다", "이다", "이며", "에는", "와의", "과의", "처럼", "보다", "마다", "이나", "하게", "해야", "들을", "들이",
            "들은", "들의", "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "로", "도", "만", "나", "들", "함", "됨", "임", "기",
            "별", "용", "상", "적", "화")       # 종류별·작업용·계약상처럼 뒤에 붙는 말(두 글자 이상의 줄기가 글에 있을 때만)
WORD = re.compile(r"[0-9A-Za-z가-힣]+")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9]*")
HANGUL = re.compile(r"[가-힣]+")


class SpecError(ValueError):
    """명세의 모양이 틀려 그릴 수 없다."""


@dataclass(frozen=True)
class Item:
    label: str
    note: str = ""
    children: tuple[str, ...] = ()


@dataclass(frozen=True)
class Spec:
    kind: str
    title: str = ""
    root: str = ""
    items: tuple[Item, ...] = ()
    header: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()

    def as_dict(self) -> dict:
        out: dict = {"kind": self.kind, "title": self.title}
        if self.kind == "table":
            out.update(header=list(self.header), rows=[list(row) for row in self.rows])
            return out
        if self.kind == "structure":
            out["root"] = self.root
        out["items"] = [{"label": item.label, **({"note": item.note} if item.note else {}),
                         **({"children": list(item.children)} if item.children else {})} for item in self.items]
        return out

    def texts(self) -> list[tuple[str, str]]:
        """(칸 이름, 글) — 근거 대조와 화면 표시에 쓴다."""
        out = [("title", self.title)] if self.title else []
        if self.root:
            out.append(("root", self.root))
        for i, item in enumerate(self.items):
            out.append((f"items[{i}].label", item.label))
            if item.note:
                out.append((f"items[{i}].note", item.note))
            out += [(f"items[{i}].children[{j}]", child) for j, child in enumerate(item.children)]
        out += [(f"header[{i}]", cell) for i, cell in enumerate(self.header)]
        out += [(f"rows[{r}][{c}]", cell) for r, row in enumerate(self.rows) for c, cell in enumerate(row) if cell]
        return out


def _text(value, name: str, limit: int, *, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise SpecError(f"{name}은(는) 글이어야 합니다")
    text = " ".join(str(value).split())
    if required and not text:
        raise SpecError(f"{name}이(가) 비었습니다")
    if len(text) > limit:
        raise SpecError(f"{name}이(가) {limit}자를 넘습니다({len(text)}자): {text[:20]}…")
    return text


def _items(raw, kind: str) -> tuple[Item, ...]:
    low, high = ITEM_RANGE[kind]
    if not isinstance(raw, list) or not low <= len(raw) <= high:
        raise SpecError(f"{KIND_NAMES[kind]} 도표의 items는 {low}~{high}개여야 합니다")
    items = []
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            entry = {"label": entry}
        if not isinstance(entry, dict):
            raise SpecError(f"items[{i}]는 객체여야 합니다")
        children = entry.get("children") or []
        if not isinstance(children, list) or len(children) > MAX_CHILDREN:
            raise SpecError(f"items[{i}].children은 {MAX_CHILDREN}줄까지입니다")
        if kind == "compare" and not children:
            raise SpecError(f"비교 도표의 items[{i}]에는 children이 한 줄 이상 있어야 합니다")
        if kind in ("sequence", "cycle") and children:
            raise SpecError(f"{KIND_NAMES[kind]} 도표의 칸에는 children을 쓰지 않습니다(note를 씁니다)")
        items.append(Item(_text(entry.get("label"), f"items[{i}].label", MAX_LABEL),
                          _text(entry.get("note"), f"items[{i}].note", MAX_NOTE, required=False),
                          tuple(_text(child, f"items[{i}].children[{j}]", MAX_CHILD) for j, child in enumerate(children))))
    labels = [squash(item.label) for item in items]
    if len(set(labels)) != len(labels):
        raise SpecError("이름이 같은 칸이 있습니다")
    return tuple(items)


def read_spec(raw) -> Spec:
    """JSON에서 읽은 값 → Spec. 모양이 틀리면 SpecError."""
    if isinstance(raw, Spec):
        return raw
    if not isinstance(raw, dict):
        raise SpecError("명세는 JSON 객체여야 합니다")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise SpecError(f"kind는 {', '.join(KINDS)} 가운데 하나여야 합니다")
    title = _text(raw.get("title"), "title", MAX_TITLE, required=False)
    if kind == "table":
        header, rows = raw.get("header"), raw.get("rows")
        if not isinstance(header, list) or not COLUMN_RANGE[0] <= len(header) <= COLUMN_RANGE[1]:
            raise SpecError(f"표의 header는 {COLUMN_RANGE[0]}~{COLUMN_RANGE[1]}칸이어야 합니다")
        if not isinstance(rows, list) or not ROW_RANGE[0] <= len(rows) <= ROW_RANGE[1]:
            raise SpecError(f"표의 rows는 {ROW_RANGE[0]}~{ROW_RANGE[1]}줄이어야 합니다")
        head = tuple(_text(cell, f"header[{i}]", MAX_LABEL) for i, cell in enumerate(header))
        if len({squash(cell) for cell in head}) != len(head):
            raise SpecError("이름이 같은 열이 있습니다")
        body = []
        for r, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(head):
                raise SpecError(f"rows[{r}]의 칸 수가 header와 다릅니다")
            cells = tuple(_text(cell, f"rows[{r}][{c}]", MAX_CELL, required=False) for c, cell in enumerate(row))
            if not any(cells):
                raise SpecError(f"rows[{r}]이 비었습니다")
            body.append(cells)
        return Spec(kind, title, header=head, rows=tuple(body))
    root = _text(raw.get("root"), "root", MAX_LABEL) if kind == "structure" else ""
    return Spec(kind, title, root=root, items=_items(raw.get("items"), kind))


def squash(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


# 명사형으로 줄인 말 → 글에서 찾을 꼴. 생성형 AI는 '정하고'를 '정함'으로, '쓰지 않는다'를 '쓰지 않음'으로 줄여 쓴다(2026-11-24 실제 응답에서 확인).
# (명세의 끝말, 글에서 줄기 뒤에 올 수 있는 말) — 줄기가 한 글자여도 뒤에 이 말이 붙은 꼴이 글에 있으면 같은 말로 본다
NOMINAL = (
    (("함", "하기", "한", "하는", "할"), ("하", "한", "할", "해", "했")),
    (("됨", "되기", "된", "되는", "될"), ("되", "된", "될", "돼", "됐")),
    (("음", "기", "는", "은", "을"), ("다", "는", "고", "으", "지", "아", "어", "게", "을", "은", "았", "었", "며", "면")),
)


def _conjugated(word: str, flat: str) -> bool:
    for endings, follows in NOMINAL:
        for ending in endings:
            stem = word[:-len(ending)]
            if word.endswith(ending) and stem and any(stem + follow in flat for follow in follows):
                return True
    return False


def _in_source(word: str, flat: str) -> bool:
    """낱말(한글)이 글에 있는가 — 그대로, 조사·어미를 하나 뗀 것이 두 글자 이상으로, 또는 명사형으로 줄이기 전의 꼴로 있으면 있다고 본다."""
    if word in flat or word in FRAME_WORDS:
        return True
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2 and word[:-len(suffix)] in flat:
            return True
    return _conjugated(word, flat)


@dataclass
class Grounding:
    problems: list[dict] = field(default_factory=list)      # [{"field", "text", "reason"}]

    @property
    def ok(self) -> bool:
        return not self.problems


def grounding(spec: Spec, source: str) -> Grounding:
    """명세의 글마다 집필자가 쓴 글(source: 문단과 수행준거)에 근거가 있는지 본다.

    지적하는 것: 글에 없는 낱말, 글에 없는 수, 글에 없는 영문, 상표·상품명(글에 있어도 그림에 넣지 않는다).
    """
    flat = squash(source)
    numbers = {n.replace(",", "") for n in NUMBER.findall(source or "")}
    result = Grounding()

    def add(name: str, text: str, reason: str) -> None:
        result.problems.append({"field": name, "text": text, "reason": reason})

    for name, text in spec.texts():
        clear, _unsure = find_brands(text)
        for brand, generic in clear:
            add(name, text, f"상표·상품명 '{brand}' — {generic}")
        for number in NUMBER.findall(text):
            if number.replace(",", "") not in numbers:
                add(name, text, f"글에 없는 수 '{number}'")
        for word in LATIN.findall(text):
            if word.lower() not in flat:
                add(name, text, f"글에 없는 영문 '{word}'")
        if squash(text) in flat:
            continue                                   # 글에 그대로 있는 구절
        missing = [word for token in WORD.findall(text) for word in HANGUL.findall(token) if len(word) >= 2 and not _in_source(word, flat)]
        if missing:
            add(name, text, "글에 없는 말 " + ", ".join(f"'{word}'" for word in dict.fromkeys(missing)))
    return result


SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
CLAUSE = re.compile(r"[,;]|(?<=[고며나])\s")
CAUTION = re.compile(r"않|금지|금한다|안\s*된다|안\s*됨|말아야|말\s*것|못한다|못\s*함|주의|유의|제외|삼간다|피한다|피해야")
UNUSED_SHARE = 0.34          # 문장의 낱말 가운데 명세에 쓰인 몫이 3분의 1에 못 미치면 "쓰이지 않은 문장"
MIN_SENTENCE_WORDS = 3


def _content_words(text: str) -> list[str]:
    return [word for word in HANGUL.findall(text) if len(word) >= 2 and word not in FRAME_WORDS]


def omissions(spec: Spec, text: str) -> list[dict]:
    """문단(text)의 내용 가운데 명세에 빠진 듯한 것 — [{"sentence", "reason"}]. 알림일 뿐이고 후보를 떨어뜨리지 않는다.

    근거 검사는 '글에 없는 말이 들어왔는가'만 본다. 여기서는 반대쪽을 어림한다.
      하지 말라는 내용  문장의 한 토막에 '않는다·금지·주의' 같은 말이 있는데, 명세에는 그런 말이 든 칸이 없거나 그 토막의 낱말과 겹치지 않는다
      쓰이지 않은 문장  문장의 낱말이 명세에 거의 나오지 않는다
    (2026-11-24 실제 응답: '유류 화재에는 … 물 소화기는 쓰지 않는다'가 표에서 빠졌다.)
    """
    texts = [value for name, value in spec.texts() if name != "title"]
    flat = squash(" ".join(texts))
    cautions = [squash(value) for value in texts if CAUTION.search(value)]
    found = []
    for match in SENTENCE.finditer(text or ""):
        sentence = " ".join(match.group().split())
        words = _content_words(sentence)
        if len(words) < MIN_SENTENCE_WORDS:
            continue
        missed = False
        for clause in CLAUSE.split(sentence):
            if not CAUTION.search(clause):
                continue
            stems = [word for word in _content_words(clause) if not CAUTION.search(word)]
            if not any(_in_source(word, caution) for word in stems for caution in cautions):
                found.append({"sentence": sentence, "reason": f"하지 말라거나 조심하라는 내용이 명세에 없습니다: '{clause.strip()}'"})
                missed = True
                break
        if missed:
            continue
        used = sum(1 for word in words if _in_source(word, flat))
        if used / len(words) < UNUSED_SHARE:
            found.append({"sentence": sentence, "reason": "이 문장의 내용이 명세에 쓰이지 않았습니다"})
    return found + _thin_groups(spec, text, {entry["sentence"] for entry in found})


VERB_END = re.compile(r"(다|고|며|면|서|야|여|해|하여|지|게|는|은|을|한|된|할|될)$")


def _groups(spec: Spec) -> list[tuple[str, str]]:
    """(묶음의 이름, 그 묶음에 적힌 글 전부) — 표의 줄, 그 밖에는 칸 하나와 그 설명·아래 줄."""
    if spec.kind == "table":
        return [(row[0], " ".join(row)) for row in spec.rows if row[0]]
    return [(item.label, " ".join((item.label, item.note, *item.children))) for item in spec.items]


def _thin_groups(spec: Spec, text: str, skip: set[str]) -> list[dict]:
    """묶음(표의 줄, 도표의 칸)마다 — 문단에서 그 이름이 나온 문장에 있는 말이 묶음에 빠졌는가.

    (2026-11-24 실제 응답: '유류 화재에는 분말 소화기와 이산화탄소 소화기를 쓰고 …'인데 표의 유류 화재 줄에 이산화탄소 소화기가 없었다.)
    이름이 둘 이상 나오는 문장(전체를 소개하는 문장)은 보지 않는다. 다른 묶음에 적힌 말, 서술어로 보이는 말은 세지 않는다.
    """
    groups = _groups(spec)
    names = [squash(name) for name, _ in groups]
    found = []
    for match in SENTENCE.finditer(text or ""):
        sentence = " ".join(match.group().split())
        flat_sentence = squash(sentence)
        here = [i for i, name in enumerate(names) if name and name in flat_sentence]
        if len(here) != 1 or sentence in skip:
            continue
        name, body = groups[here[0]]
        own = squash(body + " " + spec.root + " " + " ".join(spec.header))
        missing = [word for word in _content_words(sentence)
                   if not VERB_END.search(word) and not CAUTION.search(word) and not _in_source(word, own) and not _in_source(_strip(word), own)]
        if missing:
            found.append({"sentence": sentence, "reason": f"'{name}'에 빠진 듯한 말: " + ", ".join(dict.fromkeys(_strip(word) for word in missing))})
    return found


def _strip(word: str) -> str:
    """조사 하나를 뗀 꼴(두 글자 이상 남을 때만)."""
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            return word[:-len(suffix)]
    return word


def candidates(raw_list, source: str, text: str = "") -> list[dict]:
    """생성형 AI가 낸 명세 후보들 → [{"spec": dict | None, "ok": bool, "problems": [...], "error": str, "omissions": [...]}].

    source: 근거로 삼는 글(수행준거 + 문단). text: 빠진 내용을 볼 문단(없으면 source). omissions는 알림이고 ok에 영향을 주지 않는다.

    ok인 것만 그릴 후보다. 모양이 틀린 것(error)과 근거가 없는 것(problems)은 까닭과 함께 남겨 화면이 '왜 뺐는지' 보일 수 있게 한다.
    """
    out = []
    for raw in (raw_list if isinstance(raw_list, list) else [])[:MAX_CANDIDATES]:
        try:
            spec = read_spec(raw)
        except SpecError as error:
            out.append({"spec": None, "ok": False, "problems": [], "error": str(error), "omissions": []})
            continue
        found = grounding(spec, source)
        out.append({"spec": spec.as_dict(), "ok": found.ok, "problems": found.problems, "error": "", "omissions": omissions(spec, text or source)})
    return out


def table_html(spec: Spec) -> str:
    """표 명세 → HTML 표(한글 프로그램에 붙여 넣으면 표가 된다)."""
    from html import escape

    if spec.kind != "table":
        raise SpecError("표 명세가 아닙니다")
    head = "".join(f"<th>{escape(cell)}</th>" for cell in spec.header)
    body = "".join("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>" for row in spec.rows)
    return f'<table border="1"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def table_tsv(spec: Spec) -> str:
    if spec.kind != "table":
        raise SpecError("표 명세가 아닙니다")
    return "\n".join("\t".join(cell.replace("\t", " ") for cell in row) for row in (spec.header, *spec.rows)) + "\n"
