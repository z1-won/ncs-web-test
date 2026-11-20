"""의견 문장 읽기 — 유형(용어·형식·그림·내용·의견 아님)과 원고에서 찾을 핵심어를 뽑는다. I/O 없음.

LLM 없이 도는 1차 판정의 재료다. 뽑는 것
- 참조: <표 1-3>, [그림 1-6], '표 5-2' → (종류, 'N-M')
- 용어 변경 쌍(옛 → 새): 'A는 B로 (명칭) 변경됨/개정됨', 'A ⇒ B', "'A'를 'B'로 수정", "'A','B' 표현을 'C','D'로"
- 추가·보완 요청의 대상: 'X(도|을|가) 추가', 'X 내용 추가', '(GPL, MIT, Apache 등)', 'SaaS, 구독 모델 같은 …', 영문 약어·표준 번호
- 문장 수정 의견의 새 문장: '"A" -> "B" 로 수정'
뽑지 못하면 빈 목록을 돌려주고, 판정은 '확인 필요'가 된다(모르면 단정하지 않는다).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import KIND_CONTENT, KIND_FIGURE, KIND_FORM, KIND_NONE, KIND_TERM

REF = re.compile(r"[<\[〈(]?\s*(표|그림)\s*(\d+)\s*-\s*(\d+)\s*[>\]〉)]?")
ARROW = re.compile(r"\s*(?:->|→|⇒|=>)\s*")
QUOTE = re.compile(r"['‘’\"“”]([^'‘’\"“”]{1,80})['‘’\"“”]")
TERM_CHANGE = re.compile(
    r"(?:^|\s)(?P<old>[^\s]+?(?:\s[0-9][0-9.:]*)?)(?:은|는|이|가)\s+(?:현재\s*|최근\s*)?(?P<new>[^,.]+?)(?:으로|로)\s*"
    r"(?:명칭\s*)?(?:변경|개정|통합\s*[·ㆍ･]?\s*개정)")
NEW_NAME = re.compile(r"(?P<new>(?:\S+\s){0,1}\S+?)(?:으로|로)\s*(?:명칭\s*)?(?:변경|개정)됨")
REQUEST = re.compile(r"필요|권고|수정|추가|보완|보충|바람|바랍니다|좋겠|좋을|요망|반영|변경|개정|누락|오류|오타|오탈자|불일치|"
                     r"못한|아니라고|최신화|개선|조정|명시|확인|검토|제시|포함|소개|빠져|업데이트|상향|병기|통일|삭제|분리|구분하면|명확")
POSITIVE = re.compile(r"적합|적절|준용|부합|잘\s|확인함|확인하였|작성되어\s*있|구성되어\s*있|구성하고\s*있|반영하고\s*있|되었음|"
                      r"설명하고\s*있|우수|충분|유용|체계적|사료됩니다|기대됨|기대됩니다|수정되었|반영되어|반영이\s*되어|보완되었|높인\s*것|개선된\s*것|돕고자|고려되었")
# 긍정 문장 안에도 이 말이 있으면 조치 요구로 본다('필요 지식'·'필요한 지식'의 '필요'는 아니다)
STRONG_REQUEST = re.compile(r"필요(?=$|[해함하가성할]|\s*(?:있|보|$))|권고|바람|바랍니다|좋겠|좋을|요망|되면|하면|변경됨|개정됨|통합\s*[·ㆍ･]?\s*개정|"
                            r"누락|오류|오타|오탈자|불일치|못한|아니라고|빠져|가능해\s*보|보완\s*가능|상향|검토\s*필요")
VERB_TAIL = re.compile(r"(하나|하고|되어|있어|하면|되면|이며|으며|지만|는데|없이|하여|해서|됨|함|임|음|있음|보임|짐)$")
FORM = re.compile(r"정렬|줄\s*바꿈|자간|행간|가운데|공백\s*상태|페이지\s*정렬|글꼴|서식|띄어\s*쓰기|들여\s*쓰기|레이아웃|쪽수\s*확인|페이지\s*확인")
TYPO = re.compile(r"오타|오탈자")
ADD = re.compile(r"(?P<np>(?:[^\s,:.]+\s){0,3}[^\s,:.]+?)(?:도|을|를|이|가|은|는|에\s*대한\s*내용이|\s*내용이?|\s*부분도?)?\s*"
                 r"(?:추가|포함|보완|보충|소개|명시|반영|최신화|업데이트)")
LIST_BEFORE = re.compile(r"(?P<list>[^:()]+?)\s*(?:같은|등의|등이|등을|등도|등)\s")
PAREN = re.compile(r"\(([^()]{2,80})\)")
LATIN = re.compile(r"(?:KS\s?X\s)?(?:ISO/IEC(?:/IEEE)?\s?\d{4,5}(?::\d{4})?|[A-Za-z][A-Za-z0-9+]*(?:[-/][A-Za-z0-9]+)*)")
URL = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)", re.I)
STOP_LATIN = {"SW", "IT", "HW", "p", "tip", "TIP", "Tip", "UX", "UI", "PDF", "NCS", "URL", "OK", "vs", "etc", "e", "g", "http", "https", "www"}
STOP_WORDS = {"내용", "방식", "부분", "사항", "것", "등", "등의", "요소", "필요", "정보", "예시", "학습", "최신", "용어", "기준", "관련",
              "추가", "보완", "설명", "이해", "항목", "세부항목", "자료", "형태", "트렌드", "모델", "중요한", "학습자", "기본",
              "좀", "더", "이", "그", "및", "또는", "외에", "외에도", "현재", "시장에서", "널리", "쓰이는", "신설", "국제표준", "표",
              "그림", "최근", "중", "대한", "통해", "위한", "있는", "있음", "보임", "해당", "같은", "경우", "추가내용", "참고자료",
              "참고 자료"}
PARTICLE_TAIL = re.compile(r"(으로|에서|에는|에게|과의|와의|이라는|라는|이며|으며|이고|하고|에|의|을|를|이|가|은|는|도|와|과|로|만)$")


@dataclass(frozen=True)
class Ref:
    kind: str      # '표' | '그림'
    number: str    # '1-3'

    @property
    def label(self) -> str:
        return f"<표 {self.number}>" if self.kind == "표" else f"[그림 {self.number}]"


@dataclass
class Reading:
    kind: str
    refs: list[Ref] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)        # 원고에 있어야 반영으로 보는 말
    old_terms: list[str] = field(default_factory=list)   # 용어 변경 — 없어져야 하는 말
    new_terms: list[str] = field(default_factory=list)   # 용어 변경 — 새로 들어가야 하는 말
    sentences: list[str] = field(default_factory=list)   # 문장 수정 — 새 문장


def compact(text: str) -> str:
    """대조용: 공백·하이픈·가운뎃점·따옴표·괄호 없이, 영문은 소문자."""
    return re.sub(r"[\s\-‐–—·ㆍ･‧∙⋅'‘’\"“”「」『』()<>\[\]〈〉]", "", text).lower()


def refs_of(text: str) -> list[Ref]:
    out: list[Ref] = []
    for match in REF.finditer(text):
        ref = Ref(match.group(1), f"{int(match.group(2))}-{int(match.group(3))}")
        if ref not in out:
            out.append(ref)
    return out


def _trim(phrase: str) -> str:
    """구절 → 핵심어: 앞뒤 일반어·조사를 떼어 낸다."""
    words = [w for w in re.split(r"\s+", re.sub(r"[()]", " ", phrase).strip(" ,.:;·")) if w]
    words = [PARTICLE_TAIL.sub("", w) if len(w) > 2 else w for w in words]
    while words and (words[0] in STOP_WORDS or REF.fullmatch(words[0]) or words[0].endswith("에는")):
        words.pop(0)
    while words and words[-1] in STOP_WORDS:
        words.pop()
    return " ".join(words).strip(" ,.:;·")


def _usable(key: str) -> bool:
    plain = compact(key)
    if len(plain) < 2 or len(plain) > 30 or key in STOP_WORDS or key in STOP_LATIN:
        return False
    if VERB_TAIL.search(key) or re.search(r"있어|빠져|되면|하면", key):
        return False
    return not re.fullmatch(r"[\d.\-]+", plain)


def _latin(text: str) -> list[str]:
    out = []
    for match in LATIN.finditer(URL.sub(" ", REF.sub(" ", text))):
        token = match.group(0).strip()
        if token in STOP_LATIN or len(token) < 3 or re.fullmatch(r"p\d+", token):
            continue
        out.append(token)
    return out


def _term_pairs(text: str) -> tuple[list[str], list[str]]:
    olds, news = [], []
    for match in TERM_CHANGE.finditer(text):
        old, new = _trim(match.group("old")), _trim(match.group("new"))
        if old and new and _usable(old) and _usable(new):
            olds.append(old)
            news.append(new.split()[-1] if len(new.split()) > 3 else new)
    if not news and (match := NEW_NAME.search(text)):
        new = _trim(match.group("new"))
        if _usable(new):
            news.append(new)
    # 'A ⇒ B', 'A → B' (짧은 낱말 쌍만 용어로 본다)
    for match in re.finditer(r"([^\s(:]+(?:\s[^\s(:⇒→]+)?)\s*(?:⇒|→|->|=>)\s*([^\s,)/<]+(?:\s[^\s,)/<⇒→]+)?)", text):
        old, new = _trim(match.group(1)), _trim(match.group(2))
        if old and new and old != new and len(old) <= 20 and len(new) <= 20 and not QUOTE.search(match.group(0)):
            olds.append(old)
            news.append(new)
    # "'재무적','정성적' 표현을 '정량적','정성적'으로 수정" — 따옴표 묶음 둘 중 바뀐 것만
    if not olds and re.search(r"(으로|로)\s*(수정|변경|바꾸|통일)|보다는", text):
        groups: list[list[str]] = []
        last_end = None
        for match in QUOTE.finditer(text):
            if last_end is not None and re.fullmatch(r"[\s,·]*", text[last_end:match.start()]):
                groups[-1].append(match.group(1).strip())
            else:
                groups.append([match.group(1).strip()])
            last_end = match.end()
        if len(groups) >= 2:
            before, after = groups[0], groups[1]
            olds += [w for w in before if w not in after]
            news += [w for w in after if w not in before]
    return _dedupe(olds), _dedupe(news)


def _dedupe(values: list[str]) -> list[str]:
    out = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _add_keys(text: str) -> list[str]:
    keys: list[str] = []
    body = REF.sub(" ", text)
    for match in PAREN.finditer(body):
        inner = match.group(1)
        if "," in inner:
            keys += [_trim(re.sub(r"\s*등$", "", p)) for p in inner.split(",")]
    for match in LIST_BEFORE.finditer(body):
        pieces = match.group("list").split(",")[-4:]
        if len(pieces) > 1:   # 'SW제품 판매는 최근 SaaS, 조달청 …' — 첫 조각은 문장 머리가 붙어 있어 끝 낱말만
            keys += [_trim(pieces[0]).split()[-1:][0] if _trim(pieces[0]) else ""] + [_trim(p) for p in pieces[1:]]
        else:                 # '구독형 라이선스 등 최신 트렌드' — 끝 두 낱말
            keys.append(" ".join(_trim(pieces[0]).split()[-2:]))
    for match in ADD.finditer(body):
        acronym = re.search(r"\(([A-Za-z][A-Za-z0-9/\- ]{1,20})\)", match.group("np"))
        if acronym:           # '클라우드 보안 인증(CSAP)' → 'CSAP'
            keys.append(acronym.group(1).strip())
            continue
        key = _trim(match.group("np"))
        if key:
            keys.append(" ".join(key.split()[-3:]))
    keys += [m.group(1) for m in URL.finditer(text) if "." in m.group(1) and not re.fullmatch(r"[\d.]+", m.group(1))]
    keys += _latin(text)
    return [k for k in _dedupe(keys) if _usable(k)]


def read_opinion(text: str, *, max_keys: int = 6) -> Reading:
    """의견 문장 하나 → 유형·참조·핵심어."""
    refs = refs_of(text)
    strong = STRONG_REQUEST.search(text)
    if not strong and (POSITIVE.search(text) or not REQUEST.search(text)):
        return Reading(KIND_NONE, refs)
    sentences = []
    for match in re.finditer(r"[\"“]([^\"”]{15,})[\"”]\s*(?:->|→|⇒)\s*[\"“]([^\"”]{15,})[\"”]", text):
        sentences.append(match.group(2).strip())
    if sentences:
        return Reading(KIND_CONTENT, refs, sentences[:1], sentences=sentences)
    olds, news = _term_pairs(text)
    if news and not TYPO.search(text):
        return Reading(KIND_TERM, refs, news[:max_keys], olds[:max_keys], news[:max_keys])
    if TYPO.search(text) and news:
        return Reading(KIND_FORM, refs, news[:max_keys], olds[:max_keys], news[:max_keys])
    if FORM.search(text) or TYPO.search(text):
        return Reading(KIND_FORM, refs, [])
    keys = _add_keys(text)[:max_keys]
    if refs and refs[0].kind == "그림":       # 그림 속 글은 원고 글에 없다 — 캡션·주변 글만 볼 수 있다
        return Reading(KIND_FIGURE, refs, keys)
    return Reading(KIND_CONTENT, refs, keys)
