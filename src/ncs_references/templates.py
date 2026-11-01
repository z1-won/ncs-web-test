"""F14 참고 자료 서지 양식(참고자료.hwpx) 국내 17종·국외 5종의 골격 정규식과 흔한 위반의 힌트."""

import re

YEAR = r"(?:\d{4}[a-z]?|\[\d{4}\]\s*\d{4}|n\.d\.|작성일 불명)"
DATE = r"\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\."
URL = r"(?:https?://\S+|www\.\S+)"

DOMESTIC = [  # (이름, 정규식) — 구체적인 꼴을 먼저, 일반 꼴을 나중에
    ("공공누리", re.compile(rf"^공공누리\s*홈페이지\(.+?\)에서\s*{DATE}\s*검색\.\s*공공누리\s*제\d유형\.$")),
    ("법령", re.compile(rf"^[^()]+\({DATE}(\s[^)]+)?\)\.$")),
    ("기존 학습모듈(교육부(연도). 학습모듈명(LM코드). 한국직업능력연구원.)", re.compile(rf"^교육부\({YEAR}\)\.\s.+\(LM\d{{10}}_\d{{2}}v\d+\)\.\s*한국직업능력연구원\.$")),
    ("KS 표준", re.compile(rf"^국가기술표준원\({YEAR}\)\.\s*KS\s*[A-Z]?\s*\d+\.\s*한국표준협회\.$")),
    ("기사(기자(보도 연월일). “제목”. 신문사. URL)", re.compile(rf"^[^()]{{1,40}}\({DATE}\)\.\s*[“\"].+?[”\"]\.\s*[^.]+\.\s*{URL}\.?$")),
    ("보도 자료(부처명(연도. 월. 일.). 제목.)", re.compile(rf"^[^()]{{1,40}}\({DATE}\)\.\s.+\.$")),
    ("전자 자료(자료명(연도). 홈페이지명(URL)에서 YYYY. MM. DD. 검색.)", re.compile(rf"^.+?\({YEAR}\)\.\s.+?\(.+?\)에서\s*{DATE}\s*검색\.$")),
    ("번역서(저자([원서 연도] 번역 연도). 『번역서명(원서명)』. 번역자(역). 출판사.)", re.compile(rf"^[^()]+\(\[\d{{4}}\]\s*\d{{4}}\)\.\s*『.+?』\.\s.+\(역\)\.\s*[^.]+\.$")),
    ("학위 논문(저자(연도). 「논문 제목」. ××학위 논문. 대학 대학원.)", re.compile(rf"^[^()]+\({YEAR}\)\.\s*「.+?」\.\s*.+학위\s*논문\.\s*[^.]+\.$")),
    ("학술지 논문(저자(연도). 「제목」. 『학술지명』. 권수(호수). 쪽수.)", re.compile(rf"^[^()]+\({YEAR}\)\.\s*「.+?」\.\s*『.+?』\.\s*\d+(\(\d+\))?\.\s*(pp?\.\s*)?\d+(-\d+)?\.$")),
    ("단행본·교과서(저자(연도). 『책명』. 출판사.)", re.compile(rf"^[^()]+\({YEAR}\)\.\s*『.+?』\.\s*[^.]+\.?$")),
    ("특허(출원자(연도). 특허 제목(국가명 특허 번호). 출원지.)", re.compile(rf"^[^()]+\({YEAR}\)\.\s.+\(.+?특허\s*\S+\)\.\s*[^.]+\.$")),
    ("스크린 숏(프로그램명. YYYY. MM. DD. 스크린 숏.)", re.compile(rf"^.+?\.\s*{DATE}\s*스크린\s*숏\.$")),
    ("보고서·자료집·정기 간행물(저자(연도). 제목. 발행 기관.)", re.compile(rf"^[^()]+\({YEAR}\)\.\s[^.]+\.\s*[^.]+\.$")),
]
FOREIGN = [
    ("국외 기사(기자 (연월일). 제목. 신문사.)", re.compile(rf"^[^()]+\s\({DATE}\)\.\s.+\.\s*[^.]+\.$")),
    ("국외 전자 자료(홈페이지명(연도). 자료명. Retrieved from(URL).)", re.compile(rf"^.+?\({YEAR}\)\.\s.+\.\s*Retrie?ved\s+from\s*\(?.+?\)?\.?$")),
    ("국외 논문 묶음(저자 (연도). 글 제목. In 편자(Ed.), 서명(pp. OO-OO). 출판사.)", re.compile(rf"^.+?\s\({YEAR}\)\.\s.+\.\s*In\s.+\(Eds?\.\),\s.+\(pp\.\s*\d+-\d+\)\.\s*[^.]+\.$")),
    ("국외 학위 논문(저자 (연도). 제목 (Doctoral dissertation|Master’s thesis). 학교. 지명.)", re.compile(rf"^.+?\s\({YEAR}\)\.\s.+\((Doctoral dissertation|Master[’']s thesis)\)\.\s*[^.]+\.\s*[^.]+\.$")),
    ("국외 학술지 논문(저자 (연도). 제목. 학술지. 권수(호수). 쪽수.)", re.compile(rf"^.+?\s\({YEAR}\)\.\s.+\.\s.+?\.\s*\d+\s*(\(\d+\))?\.\s*\d+(-\d+)?\.$")),
    ("국외 단행본(저자 (연도). 서명. 출판지: 출판사.)", re.compile(rf"^.+?\s\({YEAR}\)\.\s.+\.\s*[^.:]+:\s*[^.]+\.$")),
]


def match_template(text: str, script: str):
    """→ 템플릿 이름 또는 None."""
    for name, pattern in (FOREIGN if script == "영문" else DOMESTIC):
        if pattern.match(text):
            return name
    return None


def hints(text: str, script: str) -> list[str]:
    """골격이 맞지 않을 때 흔한 위반을 짚어 준다."""
    out = []
    if script == "국문" and re.match(r"^[^()]+\s\(", text):
        out.append("국문 저자와 연도 괄호 사이를 띄움(붙여 씀)")
    if not re.search(rf"\({YEAR}\)|\({DATE}\)", text):
        out.append("연도 괄호 (YYYY) 없음")
    elif not re.search(rf"\((?:{YEAR}|{DATE})\)\.", text):
        out.append("연도 괄호 뒤 마침표 없음")
    if re.search(r"\)\s*,", text) or re.search(r"[』」]\s*,", text):
        out.append("쉼표로 구분한 곳이 있음(마침표로 구분)")
    if re.search(r"[《》]", text):
        out.append("《 》 사용(학술지·책명은 『 』)")
    if re.search(r"[』」\)]\s*[가-힣A-Za-z]", text) and script == "국문":
        out.append("제목 괄호 뒤 마침표 없이 바로 이어짐")
    if not text.rstrip().endswith((".", "」", "』")) and not re.search(URL + r"$", text):
        out.append("끝에 마침표 없음")
    if re.search(URL, text) and not re.search(rf"{DATE}\s*(검색|스크린\s*숏)", text) and script == "국문":
        out.append("URL이 있는데 검색 연월일(YYYY. MM. DD. 검색.)이 없음")
    if script == "영문" and re.search(URL, text) and not re.search(r"Retrie?ved\s+from", text):
        out.append("국외 전자 자료는 '… Retrieved from(URL).' 꼴")
    if script == "영문" and re.search(r"[“\"].+?[”\"]", text):
        out.append("국외 자료 제목에 따옴표를 쓰지 않음")
    return out
