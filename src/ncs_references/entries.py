"""참고 자료 항목과 본문 출처 줄 읽기.

항목: 참고 자료 구역(section_presence의 k~end, 끝이 없으면 다음 머리(활용 서식·부록·개발 이력)까지)의 글머리(•) 문단 하나 = 항목 하나.
      글머리 없이 이어지는 문단은 앞 항목의 줄바꿈으로 보고 붙인다.
출처: 본문의 '출처: …' 줄(그림·표 출처). 집필진 제작·스크린 숏은 문헌이 아니므로 ①의 대조에서 뺀다.
각 항목·출처에서 저자(연도) 키를 뽑는다: 저자는 첫 괄호 앞 글, 연도는 괄호 안 네 자리(a/b 접미, [원서 연도] 번역 연도, n.d. 허용).
"""

import re

BULLET = re.compile(r"^[•·▪ㆍ‧◦○\-–]\s*")
MEMO = re.compile(r"^[★▶※]|要")
NOT_CONTINUATION = re.compile(r"^(서식|부록|별지|표|그림)\s*\d+")  # 참고 자료 뒤 서식 목록 줄은 이어지는 서지가 아니다
NEXT_HEAD = re.compile(r"^(활\s*용\s*서\s*식|부\s*록|NCS\s*학습모듈\s*개발\s*이력|개발\s*이력)")
SRC_HEAD = re.compile(r"^출\s*처\s*[:：]\s*")
YEAR_IN_PARENS = re.compile(r"^(?P<author>[^()]{1,80}?)\s*\((?P<year>\[\d{4}\]\s*\d{4}|\d{4}[a-z]?|n\.d\.|작성일 불명|\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\)")
NOT_LITERATURE = re.compile(r"집필진\s*제작|스크린\s*숏")
LM_CODE = re.compile(r"LM\d{10}_\d{2}v\d+")


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
        if ch.isspace() or ch in "•·▪ㆍ‧◦○-–『「《(":
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
    entries = []
    for i in range(start, min(end + 1, len(paragraphs))):
        text = (paragraphs[i] or "").strip()
        if not text or i in aside or MEMO.search(text) or re.fullmatch(r"참\s*고\s*자\s*료", text):
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
