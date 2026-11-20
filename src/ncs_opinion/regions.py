"""원고에서 의견이 가리키는 범위 찾기 — 문단마다 (학습, 구성)을 붙이고, 표·그림 캡션과 출력본 쪽을 찾고, LLM에 보낼 문단을 고른다. I/O 없음.

문단 위치 붙이기(원고 표기 기준)
- '차 례' 앞(NCS학습모듈의 이해 — 양식 예시 글)은 찾지 않는다. 차례부터 첫 학습 내용 제목 앞까지가 학습모듈 개요.
- 'N-M.' 학습 내용 제목(끝에 쪽 번호가 없는 것) → 학습 N, 이어서 '필요 지식'·'수행 내용' 머리말로 구성을 바꾼다.
  '교수·학습 방법'·'평가' 제목도 같은 학습 안에서 구성을 바꾼다(ncs_core.manuscript.mark).
- 학습이 시작된 뒤 '참고 자료'·'활용 서식'·'부록' 제목 → 기타.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ncs_core.manuscript import mark
from ncs_core.manuscript.patterns import BODY_SUB

from .config import DEFAULT_CONFIG, NO_PLACE, OTHER, OVERVIEW, PLAN, SUMMARY, WHOLE, OpinionConfig
from .keys import Ref, compact, refs_of
from .sheet import Opinion

TOC = re.compile(r"^차\s*례$")
TAIL = re.compile(r"^(참고\s*자료|활용\s*서식|부\s*록|국내\s*자료|국외\s*자료|해외\s*자료|인터넷\s*자료)$")   # 제목이 그림 배너인 원고는 참고 자료 첫 묶음 제목으로
CAPTION = re.compile(r"^\s*[<\[〈]\s*(표|그림)\s*(\d+)\s*-\s*(\d+)\s*[>\]〉]")


@dataclass(frozen=True)
class Para:
    index: int
    text: str
    lesson: int | None
    part: str | None      # 학습모듈 개요 | 필요 지식 | 수행 내용 | 교수·학습 방법 | 평가 | 기타

    @property
    def where(self) -> str:
        if self.lesson:
            return f"학습 {self.lesson} {self.part or ''}".strip()
        return self.part or "원고"


@dataclass
class Manuscript:
    name: str
    paras: list[Para]
    compacts: list[str]
    captions: dict[tuple[str, str], int]   # (종류, 'N-M') → 문단 번호

    @property
    def everything(self) -> list[int]:
        return list(range(len(self.paras)))


def map_manuscript(name: str, sections: list[list[str]]) -> Manuscript:
    """Document.sections(구역별 문단) → 위치를 붙인 문단 목록."""
    flat = [text for section in sections for text in section if text and text.strip()]
    start = next((i for i, t in enumerate(flat) if TOC.match(t)), 0)
    paras: list[Para] = []
    lesson, part, started = None, OVERVIEW, False
    for text in flat[start:]:
        head = BODY_SUB.match(text)
        if head and len(text) < 60 and not re.search(r"\s\d+$", text):
            lesson, part, started = int(head.group(1)), "필요 지식", True
        elif started and TAIL.match(text):
            lesson, part = None, OTHER
        elif started and lesson and (name_ := mark(text)) in ("필요 지식", "수행 내용", "교수·학습 방법", "평가"):
            part = name_
        paras.append(Para(len(paras), text, lesson, part))
    captions: dict[tuple[str, str], int] = {}
    for para in paras:
        if (m := CAPTION.match(para.text)) and len(para.text) < 120:
            captions.setdefault((m.group(1), f"{int(m.group(2))}-{int(m.group(3))}"), para.index)
    return Manuscript(name, paras, [compact(p.text) for p in paras], captions)


def ref_region(manuscript: Manuscript, ref: Ref, config: OpinionConfig = DEFAULT_CONFIG) -> list[int] | None:
    """<표 N-M>: 캡션부터 다음 캡션 앞까지(최대 table_window 문단). [그림 N-M]: 캡션 앞뒤 figure_window 문단. 캡션이 없으면 None."""
    at = manuscript.captions.get((ref.kind, ref.number))
    if at is None:
        return None
    if ref.kind == "그림":
        return list(range(max(0, at - config.figure_window), min(len(manuscript.paras), at + config.figure_window + 1)))
    following = sorted(i for i in manuscript.captions.values() if i > at)
    end = min(following[0] if following else len(manuscript.paras), at + config.table_window)
    return list(range(at, end))


def part_region(manuscript: Manuscript, lesson: int | None, part: str | None, group: str) -> list[int]:
    """의견서의 구분·구성 → 문단 번호. 학습모듈 개요·기타는 그 부분, 학습 N은 (구성이 있으면 그 구성만)."""
    if group == OVERVIEW:
        return [p.index for p in manuscript.paras if p.part == OVERVIEW]
    if group == OTHER:
        return [p.index for p in manuscript.paras if p.part == OTHER]
    if lesson:
        same = [p.index for p in manuscript.paras if p.lesson == lesson]
        if part:
            narrow = [i for i in same if manuscript.paras[i].part == part]
            return narrow or same
        return same
    return []


def find(manuscript: Manuscript, term: str, within: list[int] | None = None) -> list[int]:
    """낱말(용어)이 든 문단 번호 — 공백·가운뎃점·괄호를 뺀 글자 대조. 판정이 아니라 '몇 곳에 있나'를 셀 때 쓴다."""
    target = compact(term)
    if not target:
        return []
    indexes = within if within is not None else manuscript.everything
    return [i for i in indexes if target in manuscript.compacts[i]]


def locate(opinion: Opinion, manuscript: Manuscript, config: OpinionConfig = DEFAULT_CONFIG) -> tuple[list[int], str, list[str], int | None]:
    """의견이 가리키는 범위 → (문단 번호, 범위 이름, 알림, 캡션 문단 번호).

    표·그림 참조가 있으면 캡션 범위, 없으면 의견서의 학습·구성 구간, 그것도 못 찾으면 원고 전체(WHOLE).
    개발계획서·종합 의견은 가리키는 자리가 없다(빈 범위, NO_PLACE).
    """
    notes: list[str] = []
    if opinion.group in (SUMMARY, PLAN):
        return [], NO_PLACE, notes, None
    found: list[int] = []
    labels = []
    caption = None
    for ref in refs_of(opinion.text):
        region = ref_region(manuscript, ref, config)
        if region is None:
            notes.append(f"원고에 {ref.label} 캡션이 없음 — 번호가 바뀌었거나 빠졌을 수 있음")
            continue
        if caption is None:
            caption = manuscript.captions[(ref.kind, ref.number)]
        found += [i for i in region if i not in found]
        labels.append(f"{ref.label} 캡션 주변")
    if found:
        return found, ", ".join(labels), notes, caption
    region = part_region(manuscript, opinion.lesson, opinion.part, opinion.group)
    if region:
        where = opinion.group + (f" {opinion.part}" if opinion.part else "")
        return region, f"{where} 구간", notes, None
    where = (opinion.group + " " + (opinion.part or "")).strip()
    notes.append(f"원고에서 '{where}' 구간을 찾지 못함 — 원고 전체에서 의견과 겹치는 문단만 보냄")
    return manuscript.everything, WHOLE, notes, None


def _bigrams(text: str) -> set[str]:
    text = compact(text)
    return {text[i:i + 2] for i in range(len(text) - 1)}


def pick_paragraphs(opinion_text: str, manuscript: Manuscript, region: list[int], *, caption: int | None = None,
                    config: OpinionConfig = DEFAULT_CONFIG) -> list[int]:
    """의견 하나를 위해 LLM에 보낼 문단 번호(문서 순서). 범위가 작으면 전체, 크면 의견과 글자가 겹치는 문단.

    겹침 점수 = 의견과 같은 두 글자 조각마다 1/(그 조각이 든 범위 문단 수) — 범위 곳곳에 흔한 조각('한다', '있다')보다
    그 의견에만 있는 조각('CS', 'SA')이 무겁다. 점수가 llm_min_overlap 이상인 문단을 높은 순으로 llm_per_opinion개까지 고르고,
    상위 세 문단의 앞뒤 문단(표는 칸마다 문단이 나뉜다)과 캡션 문단을 더한다.
    """
    if len(region) <= config.llm_per_opinion:
        return list(region)
    wanted = _bigrams(opinion_text)
    grams = {i: _bigrams(manuscript.paras[i].text) & wanted for i in region}
    df: dict[str, int] = {}
    for shared in grams.values():
        for gram in shared:
            df[gram] = df.get(gram, 0) + 1
    scored = sorted(((sum(1 / df[g] for g in shared), -i) for i, shared in grams.items() if shared), reverse=True)
    top = [-minus for score, minus in scored if score >= config.llm_min_overlap][: config.llm_per_opinion]
    inside = set(region)
    chosen = set(top)
    for i in top[:3]:
        chosen.update(j for j in (i - 1, i + 1) if j in inside)
    if caption is not None:
        chosen.add(caption)
    return sorted(chosen)


def print_pages(pdf) -> list[tuple[str, str]]:
    """출력본 PDF(ncs_core.pdf.PdfDocument) → [(쪽 표시, 대조용 본문)]. 쪽 번호를 못 읽은 쪽은 물리 쪽으로."""
    return [(page.folio or f"{page.number}(물리)", compact("".join(page.body))) for page in pdf.pages]


def print_page(pages: list[tuple[str, str]], text: str) -> str | None:
    """문단 글이 실린 출력본 쪽(문단 앞 24글자로 찾는다)."""
    probe = compact(text)[:24]
    if len(probe) < 6:
        return None
    return next((folio for folio, body in pages if probe in body), None)
