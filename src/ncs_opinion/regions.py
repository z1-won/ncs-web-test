"""원고에서 의견이 가리키는 범위 찾기 — 문단마다 (학습, 구성)을 붙이고, 표·그림 캡션과 출력본 쪽을 찾는다. I/O 없음.

문단 위치 붙이기(원고 표기 기준)
- '차 례' 앞(NCS학습모듈의 이해 — 양식 예시 글)은 찾지 않는다. 차례부터 첫 학습 내용 제목 앞까지가 학습모듈 개요.
- 'N-M.' 학습 내용 제목(끝에 쪽 번호가 없는 것) → 학습 N, 이어서 '필요 지식'·'수행 내용' 머리말로 구성을 바꾼다.
  '교수·학습 방법'·'평가' 제목도 같은 학습 안에서 구성을 바꾼다(ncs_core.manuscript.mark).
- 학습이 시작된 뒤 '참고 자료'·'활용 서식'·'부록' 제목 → 기타.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from ncs_core.manuscript import mark
from ncs_core.manuscript.patterns import BODY_SUB

from .config import OTHER, OVERVIEW, DEFAULT_CONFIG, OpinionConfig
from .keys import Ref, compact

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


def find(manuscript: Manuscript, key: str, within: list[int] | None = None, config: OpinionConfig = DEFAULT_CONFIG) -> list[int]:
    """핵심어가 든 문단 번호. 긴 핵심어(문장)는 글자 일치율로 찾는다(오탈자를 고친 경우)."""
    target = compact(key)
    if not target:
        return []
    indexes = within if within is not None else manuscript.everything
    hits = [i for i in indexes if target in manuscript.compacts[i]]
    if hits:
        return hits
    words = [compact(w) for w in key.split() if len(compact(w)) >= 2]
    if len(words) >= 2 and len(target) < config.long_key:
        # 여러 낱말 핵심어: 이웃한 문단 셋(표는 칸마다 문단이 나뉜다) 안에 낱말이 모두 있으면 찾은 것으로
        inside = set(indexes)
        out = []
        for i in indexes:
            near = "".join(manuscript.compacts[j] for j in range(i, i + 3) if j in inside)
            if all(w in near for w in words) and any(w in manuscript.compacts[i] for w in words):
                out.append(i)
        return out
    if len(target) < config.long_key:
        return []
    out = []
    for i in indexes:
        text = manuscript.compacts[i]
        if len(text) < 0.6 * len(target):
            continue
        matcher = difflib.SequenceMatcher(None, target, text, autojunk=False)
        if sum(block.size for block in matcher.get_matching_blocks()) / len(target) >= config.fuzzy:
            out.append(i)
    return out


def print_pages(pdf) -> list[tuple[str, str]]:
    """출력본 PDF(ncs_core.pdf.PdfDocument) → [(쪽 표시, 대조용 본문)]. 쪽 번호를 못 읽은 쪽은 물리 쪽으로."""
    return [(page.folio or f"{page.number}(물리)", compact("".join(page.body))) for page in pdf.pages]


def print_page(pages: list[tuple[str, str]], text: str) -> str | None:
    """문단 글이 실린 출력본 쪽(문단 앞 24글자로 찾는다)."""
    probe = compact(text)[:24]
    if len(probe) < 6:
        return None
    return next((folio for folio, body in pages if probe in body), None)
