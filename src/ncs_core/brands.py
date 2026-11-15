"""상호·상품명·프로그램명 사전 — 수행 내용 ②(재료·기기 줄)와 기타 ③(본문)이 함께 쓴다(안내서 A-09 제품명 통일).

  NAMES      명확한 제품·서비스·회사명 → 일반 명칭 제안. 걸리면 자동 판정(부적합) 근거가 된다.
  AMBIGUOUS  일반 낱말과 겹치는 이름(한글·워드·윈도우 …) → 뜻을 사람이 확인(판단불가).
  TRADEMARK  ®·™ 표시.
사전은 공식 목록이 아니다. 사전에 없는 이름은 잡지 못한다(LLM 후보 — 판단불가).
어느 문단을 볼지, 어떤 판정을 낼지는 각 엔진의 rules/가 정한다. 여기는 찾기만 한다.
"""

import re

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


def find_brands(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """문단 하나 → (명확한 이름 [(표현, 일반 명칭 제안)], 뜻을 확인할 이름 [(표현, 확인할 점)]).
    명확한 이름이 하나라도 있으면 뜻을 확인할 이름은 돌려주지 않는다(같은 문단을 두 번 지적하지 않는다)."""
    text = text or ""
    clear = [(m.group(), generic) for pattern, generic in NAMES if (m := pattern.search(text))]
    if (m := TRADEMARK.search(text)):
        clear.append((m.group(), "상표 표시(®·™) 삭제"))
    if clear:
        return list(dict(clear).items()), []
    return [], [(m.group(), why) for pattern, why in AMBIGUOUS if (m := pattern.search(text))]
