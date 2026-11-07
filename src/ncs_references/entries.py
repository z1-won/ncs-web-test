"""참고 자료 항목과 본문 출처 줄 읽기.

항목: 참고 자료 구역(section_presence의 k~end, 끝이 없으면 다음 머리(활용 서식·부록·개발 이력)까지)의 글머리(•) 문단 하나 = 항목 하나.
      글머리 없이 이어지는 문단은 앞 항목의 줄바꿈으로 보고 붙인다.
출처: 본문의 '출처: …' 줄(그림·표 출처). 집필진 제작·스크린 숏은 문헌이 아니므로 ①의 대조에서 뺀다.
각 항목·출처에서 저자(연도) 키를 뽑는다: 저자는 첫 괄호 앞 글, 연도는 괄호 안 네 자리(a/b 접미, [원서 연도] 번역 연도, n.d. 허용).
"""

import re

BULLET = re.compile(r"^[•·▪ㆍ‧◦○∙●\-–]\s*")  # ∙(U+2219)·●도 실데이터(SW제품기획 최종본)의 글머리
MEMO = re.compile(r"^[★▶※]|要")
NOT_CONTINUATION = re.compile(r"^(서식|부록|별지|표|그림)\s*\d+")  # 참고 자료 뒤 서식 목록 줄은 이어지는 서지가 아니다
NEXT_HEAD = re.compile(r"^(활\s*용\s*서\s*식|부\s*록|NCS\s*학습모듈\s*개발\s*이력|개발\s*이력)")
SRC_HEAD = re.compile(r"^출\s*처\s*[:：]\s*")
YEAR_IN_PARENS = re.compile(r"^(?P<author>[^()]{1,80}?)\s*\((?P<year>\[\d{4}\]\s*\d{4}|\d{4}[a-z]?|n\.d\.|작성일 불명|\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\)")
SUBHEAD = re.compile(r"^(국내|국외|동양|서양|해외|외국)\s*(자료|문헌)$")  # 참고 자료 안 묶음 제목 — 항목이 아니다
DOT_BULLET = re.compile(r"^[•·▪ㆍ‧◦○∙●]")  # 위로 넓힐 때 쓰는 글머리('-'는 피드백 줄도 써서 뺀다)
# 점 글머리 줄이라도 서지처럼 생겨야 참고 자료로 끌어온다 — 피드백·평가의 '• 평가자 체크리스트' 같은 줄은 제외
BIB_HINT = re.compile(r"\d{4}|[「『《]|https?://|www\.|출판|발행|학회|연구원|진흥원|센터|Press|Inc|Ltd|Publishing", re.IGNORECASE)
GUESSED = "제목은 텍스트가 아님"  # section_presence가 제목 없이 참고문헌 꼴 줄로 구역을 추정했다는 표시
NOT_LITERATURE = re.compile(r"집필진\s*제작|스크린\s*숏")
LM_CODE = re.compile(r"LM(?:\d{10}|\d{8})_\d{2}v\d+")  # 옛 판본은 8자리(LM20010410_14v2)


def key_of(text: str) -> dict | None:
    """'저자(연도). …' → {'author': 정규화 저자, 'year': 네 자리 연도(접미 제거), 'raw_author'}. 못 읽으면 None."""
    m = YEAR_IN_PARENS.match(text.strip())
    if not m:
        return None
    raw = m.group("author").strip()
    year = re.search(r"\d{4}", m.group("year"))
    return {"author": normalize_author(raw), "raw_author": raw, "year": year.group() if year else m.group("year"),
            "year_raw": m.group("year")}


def normalize_author(text: str) -> str:
    """공백·가운뎃점·'외'·'등'·쉼표를 빼고 소문자로 — 본문 출처(3인+외)와 참고 자료(전원) 저자를 느슨하게 맞추기 위해."""
    text = re.sub(r"\s*(외|등)\s*$", "", text.strip())
    return re.sub(r"[\s·･ㆍ‧,&]", "", text).lower()


def script_of(text: str) -> str:
    """항목의 문자 종류: 국문 / 영문 / 중문 / 일문 / 기타 — 첫 글자로 판정하되, 가나가 어디든 있으면 일문(한자 이름 저자)."""
    if any(0x3040 <= ord(ch) <= 0x30FF for ch in text):
        return "일문"
    for ch in text:
        if ch.isspace() or ch in "•·▪ㆍ‧◦○∙●-–『「《(":
            continue
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3 or 0x3131 <= code <= 0x318E:
            return "국문"
        if ch.isascii() and ch.isalpha():
            return "영문"
        if 0x3040 <= code <= 0x30FF:
            return "일문"
        if 0x4E00 <= code <= 0x9FFF:
            return "중문"
        if ch.isdigit():
            continue
        return "기타"
    return "기타"


def collect_entries(paragraphs: list[str], presence: dict, aside=frozenset()) -> list[dict]:
    """→ [{'idx', 'text'(글머리 뗀 본문), 'raw', 'key', 'script', 'translated'}]"""
    found = presence.get("참고 자료") or {}
    if not found.get("있음") or found.get("k") is None:
        return []
    start = found["k"]
    end = found.get("end")
    if end is None:
        # 끝을 모르면 다음 꼬리 영역(활용 서식·부록 — 배너만 있어도 presence가 위치를 안다)이나 다음 머리 글 앞까지
        later = [v["k"] for name, v in presence.items() if name != "참고 자료" and isinstance(v, dict) and v.get("k") is not None and v["k"] > start]
        head = next((i for i in range(start + 1, len(paragraphs)) if NEXT_HEAD.match((paragraphs[i] or "").strip())), len(paragraphs))
        end = min(later + [head]) - 1
    if GUESSED in (found.get("근거") or ""):
        start = extend_upward(paragraphs, start, aside)
    entries = []
    for i in range(start, min(end + 1, len(paragraphs))):
        text = (paragraphs[i] or "").strip()
        if not text or i in aside or MEMO.search(text) or re.fullmatch(r"참\s*고\s*자\s*료", text) or SUBHEAD.match(text):
            continue
        if BULLET.match(text) or not entries or key_of(text) is not None or NOT_CONTINUATION.match(text):
            # 글머리 항목, 저자(연도)로 시작하는 줄, 서식·부록 머리 = 새 항목(또는 구역 밖 글)
            body = BULLET.sub("", text).strip()
            entries.append({"idx": i, "raw": text, "text": body})
        else:  # 저자(연도) 없이 이어지는 줄 → 앞 항목에 붙임(긴 서지의 줄바꿈)
            entries[-1]["text"] = (entries[-1]["text"] + " " + text).strip()
    for n, entry in enumerate(entries, 1):
        entry["n"] = n
        entry["key"] = key_of(entry["text"])
        entry["script"] = script_of(entry["text"])
        entry["translated"] = bool(re.match(r"^[^()]+\(\[\d{4}\]\s*\d{4}\)", entry["text"]))
    return entries


def extend_upward(paragraphs: list[str], start: int, aside=frozenset()) -> int:
    """제목이 이미지라 구역을 '참고문헌 꼴 줄이 가장 길게 이어진 곳'으로 추정한 경우, 그 앞의 같은 덩어리까지 시작을 당긴다.

    추정은 '(2021. 1)'처럼 연도 표기가 다르거나 연도가 없는 국외 자료 줄에서 끊겨, 참고 자료 끝부분만 잡기도 한다
    (SW제품기획 0405: 국내 5건·국외 3건을 빼고 ISO 3건만 잡힘). 빈 줄, 묶음 제목('국내 자료'), 점 글머리 줄,
    저자(연도) 줄이 이어지는 동안 올라가고, 그 밖의 글(피드백 '- …' 줄 등)을 만나면 멈춘다.
    점 글머리 줄은 서지처럼 생긴 줄(BIB_HINT: 연도·「」·URL·발행처 낱말)만 끌어온다 — 피드백을 '•'로 쓴 원고에서
    피드백 줄을 참고 자료 항목으로 잘못 읽지 않도록.
    """
    j = start - 1
    while j >= 0:
        text = (paragraphs[j] or "").strip()
        if not text or j in aside:
            j -= 1
            continue
        if SUBHEAD.match(text) or (DOT_BULLET.match(text) and BIB_HINT.search(text)) or key_of(text) is not None:
            start = j
            j -= 1
            continue
        break
    return start


MIN_SHORT_RUN = 2  # 코어는 제목 없는 참고 자료를 '참고문헌 꼴 줄 3개 연속'부터 인정한다 — 2개짜리를 엔진에서 보조로 찾는다


def is_reference_line(text: str) -> bool:
    """참고 자료 항목처럼 생긴 줄 — 점 글머리 + 서지 단서, 또는 저자(연도)로 시작. '출처:' 줄은 아니다."""
    text = (text or "").strip()
    if not text or SRC_HEAD.match(text):
        return False
    body = BULLET.sub("", text)
    return key_of(body) is not None or bool(DOT_BULLET.match(text) and BIB_HINT.search(text))


def find_short_reference_run(paragraphs: list[str], aside=frozenset(), in_table=frozenset()) -> dict | None:
    """코어(section_presence)가 참고 자료를 못 찾았을 때의 보조 탐색 — 표·메모 밖에서 참고 자료 항목 줄이
    MIN_SHORT_RUN개 이상 이어진 마지막 덩어리. SW제품기획 0404: 제목이 이미지이고 항목이 2개뿐이라 코어 기준(3개)에 못 미쳐
    참고 자료 ①②③이 모두 '항목을 찾지 못함' △였다(한글 PDF 94쪽에 실제로 있음). 결과는 코어와 같은 모양의 presence 항목."""
    runs, run = [], []
    for i, text in enumerate(paragraphs):
        if i in aside or i in in_table:
            if run and i in in_table:
                runs.append(run)
                run = []
            continue
        if not (text or "").strip():
            continue
        if is_reference_line(text):
            run.append(i)
        else:
            if run:
                runs.append(run)
            run = []
    if run:
        runs.append(run)
    runs = [r for r in runs if len(r) >= MIN_SHORT_RUN]
    if not runs:
        return None
    best = runs[-1]
    return {"있음": True, "근거": f"참고문헌 꼴 줄 {len(best)}개 연속 (section1 p{best[0]}~p{best[-1]}) — {GUESSED}(이미지일 가능성), 엔진 보조 탐색",
            "k": best[0], "end": best[-1]}


def collect_citations(paragraphs: list[str], end: int | None, aside=frozenset()) -> list[dict]:
    """본문(참고 자료 구역 앞)의 '출처:' 줄 → [{'idx', 'text', 'key', 'literature'(문헌인가), 'lm_code'}]"""
    stop = end if end is not None else len(paragraphs)
    out = []
    for i in range(0, min(stop, len(paragraphs))):
        text = (paragraphs[i] or "").strip()
        if not text or i in aside or not SRC_HEAD.match(text):
            continue
        body = SRC_HEAD.sub("", text).strip()
        code = LM_CODE.search(body)
        out.append({"idx": i, "text": body, "key": key_of(body), "literature": not NOT_LITERATURE.search(body),
                    "lm_code": code.group() if code else None})
    return out
