"""기타 ③: 본문 텍스트 및 그림에 특정 상호, 상품명, 제품 모델명, 모델 번호, 특정 프로그램명, 인물 등이 노출되지는 않았는가.

체크리스트가 직접 금지하고 예시까지 든다("엑셀, 아래아 한글 → 스프레드시트 프로그램") → 본문에 나오면 X.
  - 사전(아래 NAMES)의 명확한 제품·서비스·회사명, ®·™ 표시 → X(일반 명칭 제안을 붙임)
  - 일반 낱말과 겹치는 이름(AMBIGUOUS: 한글·워드·윈도우·오피스·줌 …) → △(뜻이 제품명인지 사람 확인)
  - 제외: '출처:' 줄(F14가 스크린 숏 출처에 프로그램명을 쓰게 함, F08 AI 도구 표기), 참고 자료 구역(서지), 메모
  - 그림 속 노출(로고·상품·인물)은 볼 수 없다 → 그림이 있으면 '그림 N개 사람 확인' △를 함께 둔다
SW제품기획 최종본(사람 검수 통과)에도 본문 제품명이 많다(엑셀 14, Windows 11 …) — 체크리스트 문구를 따라 X로 둔다(결정 2026-11-05).
사전은 공식 목록이 아니다. 사전에 없는 이름은 잡지 못한다(LLM 후보).
"""

import re

from ncs_core import O, TRI, X, visible

from ..images import picture_records
from .common import row

CHECK = "③ 본문 상호·상품명·프로그램명"
PICTURES = "③ 그림 속 노출(사람 확인)"
SRC = re.compile(r"^\s*출\s*처\s*[:：]")

# (정규식, 일반 명칭 제안) — 한글 이름 뒤에는 조사가 붙으므로 뒤쪽 경계는 영문자·숫자만 막는다
_GENERIC = {
    "스프레드시트 프로그램": ["엑셀", "Excel", "MS\\s*엑셀"],
    "프레젠테이션 프로그램": ["파워\\s*포인트", "PowerPoint"],
    "문서 작성 프로그램": ["아래아\\s*한글", "한컴\\s*오피스", "한글\\s*오피스", "MS\\s*워드", "MS\\s*Word", "Microsoft\\s*Word"],
    "이미지 편집 프로그램": ["포토샵", "Photoshop", "일러스트레이터", "Illustrator"],
    "메신저": ["카카오톡", "카톡", "KakaoTalk", "슬랙", "Slack", "텔레그램", "Telegram"],
    "화상 회의 서비스": ["Zoom", "MS\\s*Teams", "Microsoft\\s*Teams", "웹엑스", "Webex"],
    "동영상 공유 서비스": ["유튜브", "YouTube"],
    "소셜 미디어": ["페이스북", "Facebook", "인스타그램", "Instagram", "트위터", "Twitter"],
    "검색 포털": ["네이버", "NAVER", "Naver", "다음\\s*카카오"],
    "생성형 AI 서비스": ["챗\\s*GPT", "ChatGPT", "제미나이", "Gemini", "코파일럿", "Copilot", "클로바\\s*X", "뤼튼"],
    "협업 도구": ["노션", "Notion", "지라", "Jira", "트렐로", "Trello", "깃허브", "GitHub", "깃랩", "GitLab", "컨플루언스", "Confluence"],
    "클라우드 서비스": ["AWS", "Amazon\\s*Web\\s*Services", "애저", "Azure", "구글\\s*클라우드", "Google\\s*Cloud"],
    "운영체제": ["Windows", "윈도우즈", "윈도\\s*10", "윈도\\s*11", "macOS", "맥\\s*OS", "iOS", "안드로이드", "Android"],
    "데이터베이스 관리 시스템": ["오라클\\s*DB", "Oracle\\s*DB", "MySQL", "MS\\s*SQL", "MSSQL"],
    "기업명(일반화 필요)": ["구글", "Google", "마이크로소프트", "Microsoft", "애플(?!리케이션)", "Apple", "아마존", "Amazon",
                     "오라클", "Oracle", "삼성", "Samsung", "카카오", "SAP", "IBM", "한컴", "한글과컴퓨터"],
    "스마트폰": ["아이폰", "iPhone", "갤럭시", "Galaxy"],
    "기업명(일반화 필요) ": ["삼성\\s*전자", "LG\\s*전자", "SK\\s*텔레콤", "KT", "현대\\s*자동차", "네이버\\s*클라우드"],
}
# 한글 이름 뒤에는 조사만 올 수 있다 — '메타데이터'의 '메타', '애플리케이션'의 '애플', '삼성전자'의 '삼성'처럼
# 더 긴 낱말의 앞부분은 이름이 아니다(SW제품기획 최종본·테스트 원본에서 확인). 영문 이름 뒤에는 영문자·숫자가 오지 않으면 된다.
_KO_AFTER = (r"(?=$|[^가-힣]|(?:은|는|이|가|을|를|의|에|에서|에게|와|과|로|으로|도|만|등|이나|나|처럼|사|이며|이고|이다|에는|과의|와의)"
             r"(?![가-힣]))")
_EN_AFTER = r"(?![A-Za-z0-9])"


def _name(p: str) -> re.Pattern:
    after = _KO_AFTER if re.search(r"[가-힣]", p) else _EN_AFTER
    return re.compile(rf"(?<![A-Za-z가-힣]){p}{after}")


NAMES = [(_name(p), generic.strip()) for generic, pats in _GENERIC.items() for p in pats]
COLOPHON = re.compile(r"^(?:NCS\s*학습모듈\s*)?개발\s*이력")  # 개발 이력·판권: 집필진·검토진 소속(회사명)을 적게 되어 있다
TRADEMARK = re.compile(r"[®™]")
# 일반 낱말과 겹쳐 뜻을 사람이 봐야 하는 이름 — △
AMBIGUOUS = [(_name(p), why) for p, why in (
    ("한글", "'한글'이 문자(한국어 글자)인지 프로그램인지"),
    ("워드", "'워드'가 낱말(단어)인지 프로그램인지"),
    ("윈도우", "'윈도우'가 창(window)인지 운영체제인지"),
    ("오피스", "'오피스'가 사무실인지 사무용 프로그램인지"),
    ("줌", "'줌'이 확대인지 화상 회의 서비스인지"),
    ("팀즈", "'팀즈'가 화상 회의 서비스인지"),
    ("LG", "LG가 회사명으로 노출되었는지"),
    ("MS", "MS가 회사명(마이크로소프트)인지"),
    ("GPT", "GPT가 기술 일반 용어인지 특정 서비스인지"),
    ("메타", "'메타'가 접두어(메타 데이터·메타 정보)인지 회사명인지"),
)]


def _reference_range(context) -> tuple[int, int] | None:
    found = context.presence.get("참고 자료") or {}
    if not found.get("있음") or found.get("k") is None:
        return None
    return found["k"], found.get("end") or len(context.manuscript.sections[context.config.body_section])


def check_brand_names(context) -> list[dict]:
    manuscript, config = context.manuscript, context.config
    body = manuscript.sections[config.body_section]
    aside = manuscript.section_aside_paragraphs(config.body_section) or frozenset()
    refs = _reference_range(context)
    colophon = next((i for i, t in enumerate(body) if COLOPHON.match((t or "").strip())), len(body))
    rows, hard, soft = [], 0, 0
    for i, text in enumerate(body[:colophon]):
        text = text or ""
        if not text.strip() or i in aside or SRC.match(text) or (refs and refs[0] <= i <= refs[1]):
            continue
        found = []
        for pattern, generic in NAMES:
            m = pattern.search(text)
            if m:
                found.append((m.group(), generic))
        if TRADEMARK.search(text):
            found.append((TRADEMARK.search(text).group(), "상표 표시(®·™) 삭제"))
        if found:
            hard += 1
            names = ", ".join(f"「{n}」→{g}" for n, g in dict(found).items())
            rows.append(row("③", f"section1 > 문단 {i}", f"문단 {i}", visible(text.strip())[:120], {CHECK: X},
                            {CHECK: f"문단 {i} {names}: 「{visible(text.strip())[:50]}」"},
                            "특정 상호·상품명·프로그램명을 일반 명칭으로 바꿈(예: 엑셀 → 스프레드시트 프로그램)"))
            continue
        unsure = [(m.group(), why) for pattern, why in AMBIGUOUS if (m := pattern.search(text))]
        if unsure:
            soft += 1
            rows.append(row("③", f"section1 > 문단 {i}", f"문단 {i}", visible(text.strip())[:120], {CHECK: TRI},
                            {CHECK: f"문단 {i} " + " / ".join(f"「{n}」 {why} 사람 확인" for n, why in unsure)
                                    + f": 「{visible(text.strip())[:50]}」"},
                            "제품·프로그램명이면 일반 명칭으로 바꿈"))
    pictures = len(picture_records(manuscript)) if manuscript.format == "hwpx" else None
    if pictures is None or pictures:
        note = "hwp는 그림을 읽을 수 없음" if pictures is None else f"그림 {pictures}개"
        rows.append(row("③", "section1 > 그림", "", {"그림": pictures}, {PICTURES: TRI},
                        {PICTURES: f"{note} — 그림 속 상호·상품·로고·인물 노출은 사람 확인(블러·삭제 필요 여부)"}))
    if not hard and not soft:
        rows.append(row("③", "section1", "", None, {CHECK: O}, {CHECK: "본문에서 사전에 있는 상호·상품명·프로그램명을 찾지 못함"}))
    return rows
