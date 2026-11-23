"""원고의 그림 목록 — 캡션([그림 N-M] 그림명)마다 그 위의 출처 줄과 생성형 AI 표기 줄을 함께 읽는다. 판정은 하지 않는다.

권리 증빙 점검(ncs_rights, REQ-02-014)이 쓰고, 이미지 추출(REQ-02-009)이 이어서 쓸 수 있게 공통 코어에 둔다.
hwp·hwpx 모두 된다(문단 글만 본다). 그림 파일 자체는 ncs_core.pictures.picture_records가 읽는다.

그림 한 개의 표기 순서(F14 집필 양식, F08 AI 도구 사용 표기 예):
    (그림)
    출처: 집필진 제작(2026)                       ← 출처 줄
    ChatGPT를 활용하여 생성함. 2026. 7. 20.       ← AI 활용 줄(AI를 쓴 그림만)
    [그림 1-1] 생산 설비 주요 구성 요소           ← 캡션
캡션 위 LOOKBACK개 문단 안에서 출처 줄과 AI 줄을 찾고, 다른 그림의 캡션을 만나면 멈춘다.
AI 줄과 캡션이 한 문단에 붙어 있는 경우(F08 예 4: '…생성함. 2026. 7. 20.[그림 1-] …')도 읽는다.

쓰는 쪽(REQ-02-006 ③ 표기 문구 자동 삽입)도 여기 둔다: ai_line·marking_lines가 만든 줄은 parse_ai_mark가 같은 값으로 다시 읽는다.
출력본 PDF에서 그림이 놓인 쪽(figure_pages)은 권리 증빙 점검과 생성형 AI 결과물 현황 작성이 함께 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

LOOKBACK = 4
_DASH = r"[-–—－‐]"
LABEL = re.compile(rf"[\[〔]\s*그림\s*(\d+)\s*{_DASH}\s*(\d*)\s*[\]〕]")
SOURCE = re.compile(r"^출\s*처\s*[:：]")
AI_MARK = re.compile(
    # 도구 이름 안의 마침표는 숫자 사이(판 번호 'ChatGPT 6.0')일 때만 이름의 일부로 본다 — 그 밖의 마침표는 앞 문장의 끝이다
    r"(?P<tool>[^\s.。,](?:[^.。]|(?<=\d)\.(?=\d)){0,40}?)\s*[을를]\s*활용하여\s*(?P<mode>생성함|수정\s*보완함)"
    r"(?:\s*\.?\s*(?P<y>\d{4})\s*\.\s*(?P<m>\d{1,2})\s*\.\s*(?P<d>\d{1,2})\s*\.?)?")
# 본문에서 그림을 가리키는 문장('[그림 1-1]과 같이 …', '… 나타낸다.')은 캡션이 아니다
REFERENCE_AFTER = re.compile(r"^(은|는|이|가|을|를|과|와|의|에|로|처럼|같이|에서|부터|까지|도|만|참조)(\s|$)")
SENTENCE_END = re.compile(r"(다|요|오|죠|까)\s*[.。?]\s*$")
_FULLWIDTH = str.maketrans("０１２３４５６７８９－", "0123456789-")


@dataclass(frozen=True)
class AiMark:
    """AI 활용 줄 한 개. mode: 'generated'(생성함) / 'modified'(수정 보완함). on: 적힌 날짜(없거나 달력에 없는 날이면 None)."""
    tool: str
    mode: str
    on: date | None
    text: str


@dataclass(frozen=True)
class Figure:
    section: int
    para: int
    major: int
    minor: int | None       # '[그림 1-]'처럼 뒤 번호를 비운 캡션은 None
    title: str
    source_line: str        # 캡션 위의 '출처: …' 줄 그대로(없으면 '')
    ai: AiMark | None

    @property
    def label(self) -> str:
        return f"그림 {self.major}-{self.minor if self.minor is not None else ''}"


def parse_label(text: str) -> tuple[int, int | None, str] | None:
    """'[그림 1-2] 그림명' 꼴 글 → (앞 번호, 뒤 번호 또는 None, 그림명). 그림 번호가 없으면 None."""
    found = LABEL.search((text or "").translate(_FULLWIDTH))
    if not found:
        return None
    title = text.translate(_FULLWIDTH)[found.end():].strip().rstrip(".").strip()
    return int(found.group(1)), (int(found.group(2)) if found.group(2) else None), title


def parse_ai_mark(text: str) -> AiMark | None:
    """'ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.' → AiMark. 그런 표기가 없으면 None."""
    found = AI_MARK.search(text or "")
    if not found:
        return None
    on = None
    if found.group("y"):
        try:
            on = date(int(found.group("y")), int(found.group("m")), int(found.group("d")))
        except ValueError:
            on = None
    mode = "generated" if found.group("mode") == "생성함" else "modified"
    return AiMark(found.group("tool").strip(), mode, on, found.group(0).strip())


MODE_WORDS = {"generated": "생성함", "modified": "수정 보완함"}
TOOL_MAX = 40
# 받침으로 읽히는 끝 글자: 숫자 0(영)·1(일)·3(삼)·6(육)·7(칠)·8(팔), 영문 l(엘)·m(엠)·n(엔). 그 밖의 영문·숫자는 받침 없이 읽힌다
_FINAL_DIGITS, _FINAL_LETTERS = set("013678"), set("lmn")


def object_particle(word: str) -> str:
    """낱말 뒤에 붙는 목적격 조사 '을' 또는 '를' — 끝 글자의 받침으로 정한다('ChatGPT' → '를', 'Real-ESRGAN' → '을').

    괄호 같은 기호는 건너뛰고 마지막 글자·숫자를 본다. 읽는 쪽(AI_MARK)은 둘 다 받으므로 틀려도 다시 읽는 데는 지장이 없다.
    """
    for char in reversed(word or ""):
        if "가" <= char <= "힣":
            return "을" if (ord(char) - 0xAC00) % 28 else "를"
        if char.isdigit():
            return "을" if char in _FINAL_DIGITS else "를"
        if char.isalpha():
            return "을" if char.lower() in _FINAL_LETTERS else "를"
    return "를"


def clean_tool(tool: str) -> str:
    """AI 활용 줄에 쓸 도구 이름 — 앞뒤 공백을 떼고, 다시 읽을 수 없는 꼴이면 ValueError(화면에 그대로 보일 말)."""
    name = re.sub(r"\s+", " ", tool or "").strip()
    if not name:
        raise ValueError("활용한 AI 도구 이름을 적어 주세요")
    if len(name) > TOOL_MAX:
        raise ValueError(f"AI 도구 이름은 {TOOL_MAX}자까지 적을 수 있습니다")
    if re.search(r"[。,]|(?<!\d)\.|\.(?!\d)", name) or name[0] in ".。,":
        raise ValueError("AI 도구 이름에는 쉼표를 쓸 수 없고, 마침표는 판 번호(예: 6.0)의 숫자 사이에만 쓸 수 있습니다")
    return name


def ai_line(tool: str, mode: str, on: date) -> str:
    """AI 활용 줄 — 'ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.' (F08 AI 도구 사용 표기 예). mode: 'generated' | 'modified'."""
    if mode not in MODE_WORDS:
        raise ValueError("활용 방식은 생성함(generated) 또는 수정 보완함(modified)이어야 합니다")
    name = clean_tool(tool)
    return f"{name}{object_particle(name)} 활용하여 {MODE_WORDS[mode]}. {on.year}. {on.month}. {on.day}."


def marking_lines(*, source_line: str, tool: str, mode: str, on: date, label: str, title: str) -> list[str]:
    """그림 한 개의 표기 세 줄: ① 출처 줄 ② AI 활용 줄 ③ 그림 번호와 제목. 출처 줄이 비면 그 줄은 빠진다(지어내지 않는다)."""
    caption = f"[{label}] {title}".strip()
    return [line for line in ((source_line or "").strip(), ai_line(tool, mode, on), caption) if line]


def _caption(text: str) -> tuple[int, int | None, str, AiMark | None] | None:
    """문단이 그림 캡션이면 (앞 번호, 뒤 번호, 그림명, 같은 문단에 붙은 AI 줄)."""
    text = (text or "").strip().translate(_FULLWIDTH)
    found = LABEL.search(text)
    if not found:
        return None
    before, after = text[:found.start()].strip(), text[found.end():].strip()
    inline_ai = parse_ai_mark(before) if before else None
    if before and inline_ai is None:
        return None                                   # 문장 가운데 나온 번호 = 본문의 참조
    if REFERENCE_AFTER.match(after) or SENTENCE_END.search(after):
        return None
    return int(found.group(1)), (int(found.group(2)) if found.group(2) else None), after.rstrip(".").strip(), inline_ai


def caption_label(text: str) -> str | None:
    """글 한 줄이 그림 캡션이면 그림 번호('그림 1-2', 뒤 번호가 비면 '그림 1-'), 아니면 None.

    원고 문단과 같은 기준이다(본문의 참조 문장은 캡션이 아님). 출력본 PDF의 줄에서 그림이 놓인 쪽을 찾을 때 쓴다.
    """
    found = _caption(text)
    if found is None:
        return None
    return f"그림 {found[0]}-{found[1] if found[1] is not None else ''}"


def manuscript_figures(document) -> list[Figure]:
    """문서의 그림 캡션을 문서 순서대로. 메모·머리말·꼬리말·각주 안 문단은 보지 않는다."""
    figures = []
    for s, paragraphs in enumerate(document.sections):
        aside = document.section_aside_paragraphs(s) or frozenset()
        captions = {i: found for i, text in enumerate(paragraphs)
                    if i not in aside and (found := _caption(text)) is not None}
        for i, (major, minor, title, inline_ai) in captions.items():
            source_line, ai, seen = "", inline_ai, 0
            for j in range(i - 1, -1, -1):
                text = (paragraphs[j] or "").strip()
                if j in captions:
                    break
                if j in aside or not text:
                    continue
                seen += 1
                if seen > LOOKBACK:
                    break
                if not source_line and SOURCE.match(text):
                    source_line = text
                elif ai is None and (mark := parse_ai_mark(text)) is not None and len(text) <= len(mark.text) + 12:
                    ai = mark                          # 줄 전체가 AI 표기인 것만(본문 문장 속 '…를 활용하여 생성함'은 제외)
                if source_line and ai is not None:
                    break
            figures.append(Figure(s, i, major, minor, title, source_line, ai))
    return figures


def figure_pages(pdf) -> dict[str, list[dict]]:
    """PdfDocument → {'그림 1-1': [{'쪽': '4' 또는 None, '추정': False, '물리 쪽': 7}, …]} (문서 순서, 같은 쪽은 한 번).

    출력본의 줄 가운데 그림 캡션으로 시작하는 줄을 찾아 그 쪽의 인쇄된 쪽 번호를 모은다. 본문의 참조 문장은 원고 읽기와 같은 기준으로 뺀다.
    """
    found: dict[str, list[dict]] = {}
    for page in pdf.pages:
        for line in page.body:
            label = caption_label(line)
            if label is None:
                continue
            places = found.setdefault(label, [])
            if not any(place["물리 쪽"] == page.number for place in places):
                places.append({"쪽": page.folio, "추정": page.folio_source == "추정", "물리 쪽": page.number})
    return found
