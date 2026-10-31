"""F02 필요지식 ⑧: 그림·표 출처 표기 — 존재(그림 필수, 표 선택) · '출처:' 머리말 · F14 템플릿 골격 · 마침표 구분."""

import re

from ncs_core import NA, O, TRI, X, visible

from .common import row

SRC_HEAD = re.compile(r"^출\s*처\s*[:：]\s*")
YEAR = r"(?:\d{4}|\[\d{4}\]\s*\d{4}|\d{4}[a-z])"
DATE = r"\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\."
TEMPLATES = [  # (이름, 정규식) — F14 '출처' 예시 14종의 골격
    ("집필진 제작", re.compile(rf"^집필진\s*제작\s*\({YEAR}\)\.?$")),
    ("전자 자료·검색", re.compile(rf"^.+?\(.+?\)에서\s*{DATE}\s*검색\.(\s*공공누리\s*제\d유형\.)?$")),
    ("스크린 숏", re.compile(rf"^.+?(\(.+?\)에서|\.)\s*{DATE}\s*스크린\s*숏\.$")),
    ("법령", re.compile(rf"^[^()]+\({DATE}(\s[^)]+)?\)\.?$")),
    ("문헌(저자(연도). 제목. 발행처. p.00.)", re.compile(rf"^[^()]{{1,80}}\({YEAR}\)\.\s.+\.\s*(pp?\.\s*\d+(-\d+)?\.?|.*\.)$")),
]
AI_MARK = re.compile(r"(AI|GPT|gpt|LM\b|Banana|Gemini|도식화|생성)")
OLD_AGENCY = re.compile(r"한국직업능력개발원")
CAPTION_START = re.compile(r"^[\[〈<]\s*(그림|표)")


def source_check(text: str) -> tuple[str, str]:
    """출처 줄 한 개 → (체크값, 비고 또는 템플릿 이름)."""
    if not SRC_HEAD.match(text):
        return X, '"출처:" 로 시작하지 않음'
    body = SRC_HEAD.sub("", text).strip()
    if not re.match(r"^출처:\s", text):
        return X, '"출처:" 뒤 띄어쓰기·콜론 모양이 양식과 다름(출처: ␣)'
    if AI_MARK.search(body) and not TEMPLATES[0][1].match(body):
        return TRI, f'AI 활용 표기 "{body}" — 지정 형식(집필진 제작(연도) 또는 직능연 AI 표기 양식)인지 확인'
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


def check_sources(body_raw: list[str], body_section: int, caps: list[dict], table_paragraphs: set[int] | None, *, lookback: int, lookahead: int) -> list[dict]:
    """caps: figtab.collect_labels 의 캡션 목록. 그림: 캡션 바로 위 '출처' 줄. 표: 표 아래 첫 '출처' 줄(선택)."""
    rows, used = [], set()
    in_table = lambda i: table_paragraphs is not None and i in table_paragraphs
    for cap in caps:
        if cap["sec"] != body_section:
            continue
        p, kind = cap["para"], cap["kind"]
        src_i = None
        if kind == "그림":
            for i in range(p - 1, max(p - 1 - lookback, -1), -1):
                if body_raw[i] and SRC_HEAD.match(body_raw[i]):
                    src_i = i
                    break
                if body_raw[i] and re.match(r"^\[그림", body_raw[i]):
                    break
        else:
            for i in range(p + 1, min(p + 1 + lookahead, len(body_raw))):
                if body_raw[i] and CAPTION_START.match(body_raw[i]):
                    break
                if body_raw[i] and SRC_HEAD.match(body_raw[i]) and not in_table(i):
                    src_i = i
                    break
        region = f"section1 > {cap['label']}"
        checks, notes = {}, {}
        if src_i is None:
            checks["출처 줄 존재"] = X if kind == "그림" else NA
            notes["출처 줄 존재"] = (
                '그림 바로 위에 출처 줄이 없음 — 집필진 제작도 "출처: 집필진 제작(연도)" 필수' if kind == "그림"
                else "표 아래 출처 없음 — 직접 작성한 표면 생략 가능(인용이면 필수)"
            )
            rows.append(row("⑧", region, cap["text"], checks, notes, "출처: 집필진 제작(연도) 또는 인용 문헌 형식으로 추가" if kind == "그림" else None))
            continue
        used.add(src_i)
        checks["출처 줄 존재"] = O
        if kind == "그림" and src_i != p - 1:
            notes["출처 줄 위치"] = f"출처 줄(p{src_i})과 캡션(p{p}) 사이에 다른 문단이 있음"
        value, note = source_check(body_raw[src_i])
        checks["출처 형식 골격"] = value
        if value == O:
            notes["템플릿"] = note
        else:
            notes["출처 형식 골격"] = note
        if OLD_AGENCY.search(body_raw[src_i]):
            checks["기관명"], notes["기관명"] = TRI, "'한국직업능력개발원' → 현재 명칭 '한국직업능력연구원'(F14) 인지 확인"
        rows.append(row("⑧", region, visible(body_raw[src_i]), checks, notes,
                        "출처: 집필진 제작(연도) / 출처: 저자(연도). 제목. 발행처. p.00. 꼴로 수정" if value == X else None, 캡션=cap["text"]))
    for i, line in enumerate(body_raw):  # 캡션과 짝이 없는 출처 줄
        if line and SRC_HEAD.match(line) and i not in used and not in_table(i):
            rows.append(row("⑧", f"section1 > p{i}", visible(line), {"캡션과 연결": TRI}, {"캡션과 연결": "이 출처 줄 앞뒤에 그림·표 캡션이 없음 — 캡션 누락 또는 떨어진 출처"}))
    return rows
