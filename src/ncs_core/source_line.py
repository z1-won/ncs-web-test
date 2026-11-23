"""그림·표 '출처:' 줄과 AI 활용 표기 줄 읽기 — 필요 지식 ⑧, 참고 자료, 그림 태깅(009)·검수(005)가 함께 쓰는 유일한 원본.

판정 정책은 두지 않는다. source_check는 F14 골격과 맞는지를 (체크값, 비고)로 돌려줄 뿐이고, 그 값을 어느 항목에서
어떻게 쓸지는 각 엔진·기능 패키지가 정한다. 표준 라이브러리만 쓴다.

  출처 줄      "출처: 교육부(2015). 기업 내부 환경 분석(LM2001010401_14v2). 한국직업능력개발원. p.25."
  AI 활용 줄   "ChatGPT를 활용하여 생성함. 2026. 7. 20."   (직능연 「AI활용기준_도구사용표기예」(2026-09):
               출처 줄 → AI 활용 줄 → 캡션 순서. '생성함' 또는 '수정 보완함' + 날짜)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import O, TRI, X

SRC_HEAD = re.compile(r"^출\s*처\s*[:：]\s*")
YEAR = r"(?:\d{4}|\[\d{4}\]\s*\d{4}|\d{4}[a-z])"
DATE = r"\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\."
TEMPLATES = [  # (이름, 정규식) — F14 '출처' 예시 14종의 골격
    ("집필진 제작", re.compile(rf"^집필진\s*제작\s*\({YEAR}\)\.?$")),
    ("전자 자료·검색", re.compile(rf"^.+?\(.+?\)에서\s*{DATE}\s*검색\.(\s*공공누리\s*제\d유형\.)?$")),
    ("스크린 숏", re.compile(rf"^.+?(\(.+?\)에서|\.)\s*{DATE}\s*스크린\s*숏\.$")),
    ("법령", re.compile(rf"^[^()]+\({DATE}(\s[^)]+)?\)\.?$")),
    ("기사(기자명(보도 연월일). “제목”. 신문사. URL.)", re.compile(rf"^[^()]{{1,40}}\({DATE}\)\.\s.+\.\s*\S+\.$")),
    ("문헌(저자(연도). 제목. 발행처. p.00.)", re.compile(rf"^[^()]{{1,80}}\({YEAR}\)\.\s.+\.\s*(pp?\.\s*\d+(-\d+)?\.|.*\.)$")),  # 끝 마침표 필수(F02: 마침표 표기 유의)
]
AI_MARK = re.compile(r"(AI|GPT|gpt|LM\b|Banana|Gemini|도식화|생성)")  # 출처 줄 안에 섞인 AI 표기 — source_check는 △로 둔다
OLD_AGENCY = re.compile(r"한국직업능력개발원")
CAPTION_START = re.compile(r"^[\[〈<]\s*(그림|표)")
FIGURE_CAPTION = re.compile(r"^\[\s*그림")
LM_CODE = re.compile(r"LM(?:\d{10}|\d{8})_\d{2}v\d+")      # 옛 판본은 8자리(LM20010410_14v2)가 정상
PAGE = re.compile(r"\bpp?\.\s*(\d+)")
URL = re.compile(r"https?://[^\s)]+|www\.[^\s)]+")
CHECKED_DATE = re.compile(rf"({DATE})\s*(검색|스크린\s*숏|스크린샷)")
KOGL = re.compile(r"공공누리\s*(?:제\s*(\d)\s*유형|(AI)\s*유형)")
AUTHOR_YEAR = re.compile(rf"^(?P<author>[^()]{{1,80}}?)\s*\((?P<year>{YEAR}|{DATE[:-2]}\.?)\)")
AI_LINE = re.compile(r"^(?P<tool>.+?)\s*(?:을|를)\s*활용하여\s*(?P<action>생성|수정\s*보완)\s*함\s*\.?\s*"
                     r"(?P<date>\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)?")

AI_LINE_EXAMPLE = "‘ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.’"      # 표기 예(F08)의 AI 활용 줄 — 안내 문구에 쓴다

SOURCE_KINDS = ("집필진 제작", "기존 학습모듈", "공공누리", "웹·검색", "스크린숏", "문헌", "법령", "AI 표기", "알 수 없음")


@dataclass(frozen=True)
class SourceInfo:
    """출처 줄 하나를 읽은 결과. 못 읽은 칸은 None(추측하지 않음)."""

    text: str
    kind: str                                  # SOURCE_KINDS 중 하나
    template: str | None                       # F14 골격과 맞으면 템플릿 이름
    author: str | None = None
    year: str | None = None
    url: str | None = None
    checked_date: str | None = None
    kogl_type: str | None = None               # "0"~"4" 또는 "AI"
    cited_module: str | None = None            # 출처 속 학습모듈 코드
    cited_page: int | None = None
    format_issues: tuple[str, ...] = field(default_factory=tuple)   # 빈 튜플 = F14 골격 일치


@dataclass(frozen=True)
class AiMarker:
    """AI 활용 표기 줄 하나. action은 '생성'·'수정 보완'. ai_type은 하나로 정할 수 있을 때만(지금은 제3자 원본 보정 = 3)."""

    raw: str
    tool: str | None
    action: str | None
    date: str | None


def source_check(text: str) -> tuple[str, str]:
    """출처 줄 한 개 → (체크값, 비고 또는 템플릿 이름)."""
    if not SRC_HEAD.match(text):
        return X, '"출처:" 로 시작하지 않음'
    body = SRC_HEAD.sub("", text).strip()
    if not re.match(r"^출처:\s", text):
        return X, '"출처:" 뒤 띄어쓰기·콜론 모양이 양식과 다름(출처: ␣)'
    if AI_MARK.search(body) and not TEMPLATES[0][1].match(body):
        return TRI, (f'AI 활용 표기 "{body}" — 출처 줄에는 집필진 제작(연도) 또는 원 출처만 적고, AI 활용은 그 아래 줄에 '
                     f'{AI_LINE_EXAMPLE} 꼴로 따로 적는 것이 표기 예입니다. 확인 필요')
    for name, pattern in TEMPLATES:
        if pattern.match(body):
            return O, name
    hints = []
    if re.search(r"\)\s*,", body):
        hints.append("연도 괄호 뒤가 쉼표 — 마침표로 구분")
    if not re.search(rf"\({YEAR}\)", body) and not re.search(DATE, body):
        hints.append("연도 괄호 (YYYY) 없음")
    if not body.endswith(".") and not TEMPLATES[0][1].match(body):
        hints.append("끝에 마침표 없음")
    if re.search(r"집필진\s*제작", body):
        hints.append("'집필진 제작(연도)' 꼴이 아님")
    return X, "F14 출처 템플릿과 골격이 다름" + (": " + ", ".join(hints) if hints else "")


def find_source_line(paragraphs: list[str], caption_para: int, *, lookback: int = 3) -> int | None:
    """그림 캡션 바로 위 lookback 문단 안의 '출처:' 줄 인덱스. 다른 그림 캡션을 만나면 멈춘다(그 그림의 출처이므로)."""
    for i in range(caption_para - 1, max(caption_para - 1 - lookback, -1), -1):
        text = paragraphs[i]
        if text and SRC_HEAD.match(text):
            return i
        if text and FIGURE_CAPTION.match(text):
            return None
    return None


def parse_source(text: str) -> SourceInfo:
    """출처 줄 → SourceInfo. 종류는 F14 템플릿 + 기존 학습모듈 패턴으로만 정한다."""
    body = SRC_HEAD.sub("", text).strip()
    value, note = source_check(text)
    template = note if value == O else None
    issues: list[str] = [] if value == O else [note]
    module = LM_CODE.search(body)
    cited_module = module.group(0) if module else None     # 옛 판본(…_14v2 등)은 LM 뒤 8자리가 정상 — 오류로 보지 않는다
    page = PAGE.search(body)
    kogl = KOGL.search(body)
    kogl_type = (kogl.group(1) or kogl.group(2)) if kogl else None
    checked = CHECKED_DATE.search(body)
    url = URL.search(body)
    who = AUTHOR_YEAR.match(body)
    if re.match(r"^집필진\s*제작", body):
        kind = "집필진 제작"
    elif cited_module:
        kind = "기존 학습모듈"
    elif kogl_type:
        kind = "공공누리"
    elif template == "스크린 숏" or re.search(r"스크린\s*숏|스크린샷", body):
        kind = "스크린숏"
    elif template and template.startswith("기사"):
        kind = "문헌"                                         # 기사는 URL이 있어도 보도 연월일이 날짜 — 확인 일자 요건 없음
    elif template == "전자 자료·검색" or url:
        kind = "웹·검색"                                      # URL이 있으면 확인 일자가 있어야 하는 웹 자료(계약서 제4조 3항)
    elif template == "법령":
        kind = "법령"
    elif value == TRI:
        kind = "AI 표기"
    elif template or who:
        kind = "문헌"
    else:
        kind = "알 수 없음"
    return SourceInfo(
        text=text, kind=kind, template=template,
        author=who.group("author").strip() if who else None, year=who.group("year") if who else None,
        url=url.group(0).rstrip(".") if url else None, checked_date=checked.group(1) if checked else None,
        kogl_type=kogl_type, cited_module=cited_module, cited_page=int(page.group(1)) if page else None,
        format_issues=tuple(issues),
    )


def parse_ai_marker(text: str) -> AiMarker | None:
    """'{도구}를 활용하여 생성함/수정 보완함. 날짜' 줄 → AiMarker. 아니면 None. 날짜 뒤에 캡션이 붙어 있어도 읽는다."""
    match = AI_LINE.match((text or "").strip())
    if not match:
        return None
    action = re.sub(r"\s+", " ", match.group("action"))
    date = re.sub(r"\s+", "", match.group("date")) if match.group("date") else None
    return AiMarker(raw=text.strip(), tool=match.group("tool").strip() or None, action=action, date=date)


def find_ai_marker(paragraphs: list[str], caption_para: int, source_para: int | None, *, window: int = 3) -> int | None:
    """AI 활용 줄 인덱스. 양식대로면 출처 줄과 캡션 사이, 아니면 캡션 위 window 문단 안. 캡션 문단 자체에 붙은 경우도 본다.
    출처 줄 위에 적은 것도 찾는다(순서가 양식과 다르다고 알리려면 찾아야 한다) — 앞 그림·표의 캡션을 넘어가지는 않는다."""
    start = source_para + 1 if source_para is not None else max(0, caption_para - window)
    for i in range(start, min(caption_para + 1, len(paragraphs))):
        if parse_ai_marker(paragraphs[i] or ""):
            return i
    if source_para is not None:
        for i in range(source_para - 1, max(source_para - window, 0) - 1, -1):
            text = paragraphs[i] or ""
            if CAPTION_START.match(text):
                break
            if parse_ai_marker(text):
                return i
    return None


def ai_date_is_real(marker: AiMarker | None) -> bool | None:
    """AI 활용 줄의 일자가 달력에 있는 날인가. 일자가 없으면 None. (parse_ai_marker는 숫자 꼴만 읽고 날짜인지는 보지 않는다.)"""
    if marker is None or not marker.date:
        return None
    from datetime import date

    numbers = [int(n) for n in re.findall(r"\d+", marker.date)]
    if len(numbers) != 3:
        return False
    try:
        date(*numbers)
    except ValueError:
        return False
    return True


# 출처 줄 안에 AI 활용을 섞어 쓴 표기 — 도구 이름이나 'AI 활용/생성'처럼 분명한 것(strong)과, '생성'·'도식화'처럼 문헌 제목일 수도 있는 낱말뿐인 것(weak)
AI_IN_SOURCE = re.compile(r"활용하여\s*(?:생성|수정\s*보완)|활용(?:한|하여)?\s*도식화|GPT|Gemini|제미나이|Notebook\s*LM|Copilot|코파일럿|Claude|클로드|"
                          r"Midjourney|미드저니|DALL|Banana|바나나|생성형\s*AI|AI\s*(?:로|으로|를|을)?\s*(?:생성|제작|수정|보정|활용)|"
                          r"인공\s*지능\s*(?:으로|을)?\s*(?:생성|제작|활용)", re.IGNORECASE)


def ai_in_source_line(body: str) -> str | None:
    """'출처:' 뒤의 글에 AI 활용 표기가 섞였는가 → 'strong'(분명함) / 'weak'(낱말만 — 확인 후보) / None. '집필진 제작(연도)' 꼴은 None."""
    body = (body or "").strip()
    if TEMPLATES[0][1].match(body):
        return None
    if AI_IN_SOURCE.search(body):
        return "strong"
    return "weak" if AI_MARK.search(body) else None


def ai_type_candidates(source: SourceInfo | None, marker: AiMarker | None) -> tuple[int, ...]:
    """F08 표기 예 1~5 중 출처 종류 + '생성/수정 보완'으로 남는 후보. 표기가 없으면 ()."""
    if marker is None:
        return ()
    own = source is not None and source.kind == "집필진 제작"
    if marker.action == "수정 보완":
        return (2, 5) if own else (3,)
    return (1, 2, 4) if own else (1, 4)


# 원고 집필 계약서 제4조 3·4항 — 저작자명과 출처(URL 주소, 자료 확인 일자, 페이지 수, 사용 요건 등).
# 출처 종류마다 꼭 있어야 할 요소. 그림 검수(005)와 출처 검토(008)가 같은 표를 쓴다(2026-11-21 하나로 합침).
REQUIRED_ELEMENTS = {
    "웹·검색": ("author", "url", "checked_date"),
    "스크린숏": ("checked_date",),
    "기존 학습모듈": ("cited_page",),
    "문헌": ("author", "cited_page"),
    "공공누리": ("kogl_type",),
}
ELEMENT_NAMES = {"author": "저작자명", "url": "URL", "checked_date": "확인 일자", "cited_page": "쪽",
                 "kogl_type": "사용 요건(공공누리 유형)"}


def has_element(source: SourceInfo, element: str) -> bool:
    """요소가 있나. 웹 출처의 저작자는 '한국관광공사 홈페이지(URL)에서 …'처럼 괄호 앞 기관·누리집 이름이다."""
    if getattr(source, element):
        return True
    if element == "author" and source.kind == "웹·검색":
        body = re.sub(r"^출\s*처\s*[:：]\s*", "", source.text)
        return bool(re.match(r"^[^()]{2,}\(", body))
    return False


def missing_elements(source: SourceInfo) -> tuple[tuple[str, ...], list[str]]:
    """(필요한 요소, 빠진 요소의 이름). 필요한 요소가 없는 종류(집필진 제작 등)면 ((), [])."""
    needed = REQUIRED_ELEMENTS.get(source.kind, ())
    return needed, [ELEMENT_NAMES[e] for e in needed if not has_element(source, e)]
