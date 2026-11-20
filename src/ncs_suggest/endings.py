"""문장 끝 서술어 읽기와 규정 꼴로 바꾸기 — '~합니다/~하세요/~할 것/~함/명사' → '~한다.' / '~할 수 있다.' / '~하기' / 명사.

서술어를 네 갈래로 읽는다.
  하   '…하다' 활용(한다·합니다·함·하기·할 것·했다·할까 …) 또는 행동명사로 끝남('… 확인', '… 설명다.')
  되   '…되다' 활용(된다·됩니다·됨·될 수 있다 …)
  모음 받침 없는 줄기 + ㄴ다/ㄹ 수 있다/ㅂ니다(배운다·배울 수 있다·배웁니다 — ㄹ 줄기 '만든다'도 같은 꼴)
  자음 받침 있는 줄기 + 는다/을 수 있다/습니다(읽는다·읽을 수 있다·읽습니다)
확신 없는 변환은 하지 않는다(None) — 틀린 문장을 추천하는 것이 가장 나쁘다.
  · ㄷ·ㅂ·ㅅ 불규칙이 섞일 수 있는 꼴(듣는다/들을, 돕는다/도울, 짓는다/지을)은 '할 수 있다'·'한다' 사이를 바꾸지 않는다.
  · '하' 앞 낱말이 한 글자(포함·결함·제한의 '포·결·제')이거나 형용사 뿌리(필요·중요·정확 …)면 '하다' 활용으로 읽지 않는다.
  · 모음 줄기는 '-기'·명사형을 만들지 않는다(만든다 ← 만들다/만드다를 가를 수 없음).
  · 행동명사인지 모르는 낱말(목록에 없고 같은 원고에서 'W한다'로 쓰인 적도 없음)로 끝나면 '하다'를 붙이지 않는다.
extra: 같은 원고에서 'W한다'·'W하도록'으로 쓰인 낱말(kinds.action_noun) — 목록에 없는 행동명사를 원고 자신의 용례로 받아들인다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .kinds import action_noun, lexicon

JONG = "ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
N, L, B = 4, 8, 17                       # 받침 번호: ㄴ, ㄹ, ㅂ
IRREGULAR = {JONG.index(c) + 1 for c in "ㄷㅂㅅ"}   # 줄기 끝 받침이 이것이면 '는다' → '을 수 있다' 변환을 하지 않는다
ADJECTIVE_ROOTS = frozenset(
    "필요 중요 가능 불가능 불필요 정확 적합 적절 간단 복잡 다양 충분 확실 유사 동일 명확 안전 편리 유용 용이 부족 원활 신속 "
    "정밀 상이 유리 불리 친숙 깨끗 건강 위험 곤란 공정 투명 철저 엄격 일정 유효 무효 타당 정당 미흡 우수 적당 풍부 정상 "
    "비슷 확고 분명 불분명 불확실 무관 유연 견고 안정 불안정 효율 비효율 저렴 신중 성실 친절 불편 익숙 생소 막대 방대".split())
ADJECTIVE_STEMS = frozenset("좋 많 적 높 낮 같 넓 짧 작 크 있 없 싫 옳 굵 얇 깊 얕 밝 맑 붉 검 희".split())
WOO_VERBS = ("배", "세", "채", "키", "비", "지", "피", "깨", "싸", "외")   # '우' 줄기 동사(배우다 …) — 나머지 '울/운/웁'은 ㅂ 불규칙(돕다 → 도울)일 수 있다
AMBIGUOUS_N = frozenset("안 신 언 얹".split())   # '안다'(알다/안다)처럼 ㄴ다 꼴만으로 줄기를 가를 수 없는 글자
CONNECTIVES = ("면", "고", "며", "지만", "는", "던", "니", "거나", "지")   # '~한다면' 등 — 군더더기가 아니라 이어지는 말

# (끝말, 확신도, 원래 꼴 설명) — 긴 것부터 맞춘다
HA_ENDINGS = (
    ("할 수 있습니다", 0.9, "'~할 수 있습니다'"), ("할 수 있음", 0.9, "'~할 수 있음'"), ("할 수 있다", 1.0, "'~할 수 있다'"),
    ("하였습니다", 0.8, "'~하였습니다'(과거)"), ("했습니다", 0.8, "'~했습니다'(과거)"), ("하십시오", 0.9, "'~하십시오'"),
    ("하였다", 0.8, "'~하였다'(과거)"), ("합니다", 0.95, "'~합니다'"), ("하세요", 0.95, "'~하세요'"), ("하시오", 0.9, "'~하시오'"),
    ("했는가", 0.75, "'~했는가'(질문)"), ("하는가", 0.8, "'~하는가'(질문)"), ("하는 것", 0.7, "'~하는 것'"),
    ("할 것", 0.95, "'~할 것'"), ("할것", 0.95, "'~할것'"), ("했다", 0.8, "'~했다'(과거)"), ("한다", 1.0, "'~한다'"),
    ("하기", 0.95, "'~하기'"), ("하자", 0.9, "'~하자'"), ("해라", 0.9, "'~해라'"), ("하라", 0.9, "'~하라'"),
    ("했나", 0.75, "'~했나'(질문)"), ("할까", 0.75, "'~할까'(질문)"), ("하나", 0.6, "'~하나'(질문)"),
    ("하는", 0.6, "'~하는'(끊긴 문장)"), ("하고", 0.5, "'~하고'(끊긴 문장)"), ("하며", 0.5, "'~하며'(끊긴 문장)"),
    ("하여", 0.5, "'~하여'(끊긴 문장)"), ("한 것", 0.8, "'~한 것'"), ("함", 0.95, "'~함'(명사형)"), ("한", 0.8, "'~한'('다' 빠짐)"),
)
DOE_ENDINGS = (
    ("될 수 있습니다", 0.9, "'~될 수 있습니다'"), ("될 수 있음", 0.9, "'~될 수 있음'"), ("될 수 있다", 1.0, "'~될 수 있다'"),
    ("되었습니다", 0.8, "'~되었습니다'(과거)"), ("되었다", 0.8, "'~되었다'(과거)"), ("됩니다", 0.95, "'~됩니다'"),
    ("됐다", 0.8, "'~됐다'(과거)"), ("된다", 1.0, "'~된다'"), ("되기", 0.95, "'~되기'"), ("될 것", 0.9, "'~될 것'"),
    ("되는가", 0.8, "'~되는가'(질문)"), ("될까", 0.75, "'~될까'(질문)"), ("됨", 0.95, "'~됨'(명사형)"), ("된", 0.8, "'~된'('다' 빠짐)"),
)
HA_JUNK = re.compile(r"^(?P<head>.*\S)[하한](?P<junk>[가-힣])$")        # '정의하늬'·'운영한겨' — '하/한' 뒤 한 글자가 어미가 아님
HAGI_JUNK = re.compile(r"^(?P<head>.*\S)하기(?P<junk>[가-힣]{1,2})$")    # '수집하기기'
NDA_JUNK = re.compile(r"^(?P<keep>.*[가-힣]다)(?P<junk>[가-힣]{1,4})$")   # '설명한다람쥐'·'측정시킨다치이카와' — 'ㄴ다' 뒤 군더더기
DOROK_DA = re.compile(r"^(?P<head>.*\S도록)\s*다?$")                   # '확인할 수 있도록다'·'분석하도록' → '~도록 한다'
PUNCT_END = re.compile(r"[\s.。,，!?！？…~·]+$")
CLOSERS = re.compile(r"[)\"'”’」』]+$")


def syllable(ch: str) -> tuple[int, int, int] | None:
    """한글 음절 → (초성, 중성, 종성 번호). 음절이 아니면 None."""
    code = ord(ch) - 0xAC00 if ch else -1
    if not 0 <= code < 11172:
        return None
    return code // 588, (code % 588) // 28, code % 28


def with_jong(ch: str, jong: int) -> str:
    cho, jung, _ = syllable(ch)
    return chr(0xAC00 + cho * 588 + jung * 28 + jong)


def _woo(ch: str) -> bool:
    """'ㅇ+ㅜ' 음절(우·운·울·웁)인가."""
    parts = syllable(ch)
    return bool(parts) and parts[0] == 11 and parts[1] == 13


def _plain_word(text: str) -> str:
    words = re.split(r"\s+", (text or "").strip())
    return re.sub(r"\(.*?\)$", "", words[-1]) if words and words[-1] else ""


@dataclass(frozen=True)
class Predicate:
    head: str          # 서술어 앞(그대로 둔다). 하·되 갈래는 '하/되' 바로 앞까지
    family: str        # '하' | '되' | '모음' | '자음'
    stem: str          # 모음: 받침 뗀 마지막 줄기 글자, 자음: 받침 있는 마지막 줄기 글자, 하·되: ''
    confidence: float
    source: str        # 사유 표시용 원래 꼴

    def form(self, target: str, extra: frozenset[str] = frozenset()) -> str | None:
        """target: '한다' | '할 수 있다' | '하기' | '명사' | '여부'(평가 항목 '~하는지 여부') | '능력'(평가 항목 '~ 능력')."""
        head, stem = self.head, self.stem
        if self.family in ("하", "되"):
            words = {"하": ("한다", "할 수 있다", "하기", "하는지 여부"), "되": ("된다", "될 수 있다", "되기", "되는지 여부")}[self.family]
            simple = dict(zip(("한다", "할 수 있다", "하기", "여부"), words))
            if target in simple:
                return head + simple[target]
            if self.family == "하" and target in ("명사", "능력") and head == head.rstrip() and action_noun(_plain_word(head), extra):
                if target == "명사":
                    return head
                before = head[: len(head) - len(head.split()[-1])].rstrip()
                return None if re.search(r"[을를이가은는에]$", before) else head + " 능력"
            return None
        if self.family == "모음":
            forms = {"한다": with_jong(stem, N) + "다", "할 수 있다": with_jong(stem, L) + " 수 있다", "여부": stem + "는지 여부"}
            return head + forms[target] if target in forms else None
        if target == "할 수 있다" and syllable(stem)[2] in IRREGULAR:
            return None
        forms = {"한다": stem + "는다", "할 수 있다": stem + "을 수 있다", "하기": stem + "기", "여부": stem + "는지 여부"}
        return head + forms[target] if target in forms else None


def _stem_ok(head: str, extra: frozenset[str]) -> float | None:
    """'하' 앞 낱말이 '하다' 동사의 뿌리로 볼 만한가 → 확신도 배수(None = 아니다)."""
    if not head.strip():
        return None
    if head.endswith(")"):                    # '정의(Definition)한다'
        return 0.9
    if head.rstrip().endswith(("도록", "게")):  # '작성하도록 해라' — 보조 용언 '하다'
        return 0.95
    word = _plain_word(head)
    if not re.fullmatch(r"[가-힣]+", word) or word in ADJECTIVE_ROOTS or word.endswith("적"):
        return None
    known = action_noun(word, extra)
    if head[-1].isspace():                    # '준비 한다'처럼 띄어 쓴 경우는 앞 낱말이 행동명사일 때만
        return 0.9 if known else None
    if len(word) < 2 or known is False:
        return None
    return 1.0 if known else 0.75


def _table(core: str, table, family: str, extra: frozenset[str]) -> Predicate | None:
    for ending, confidence, source in table:
        if core.endswith(ending) and len(core) > len(ending):
            head = core[: -len(ending)]
            if family == "되":
                word = _plain_word(head)
                if len(word) < 2 or not re.fullmatch(r"[가-힣]+", word) or head[-1].isspace():
                    return None    # '안된다'·'잘된다' 같은 한 덩어리 낱말
                return Predicate(head, family, "", confidence * 0.95, source)
            factor = _stem_ok(head, extra)
            return Predicate(head, family, "", confidence * factor, source) if factor else None
    return None


def _generic(core: str) -> Predicate | None:
    """일반 동사 활용(모음·자음 줄기). 형용사로 보이거나 불규칙이 섞일 수 있으면 None."""
    if m := re.fullmatch(r"(?P<head>.*?)(?P<s>[가-힣])\s*수\s*있(다|음|습니다)", core):
        head, s = m.group("head"), m.group("s")
        if s == "을":
            stem = head[-1:] if head else ""
            parts = syllable(stem)
            if not parts or parts[2] in (0, L) or stem in ADJECTIVE_STEMS:
                return None      # 지을(짓다)·들을(듣다)·나을(낫다) — 불규칙일 수 있다
            return Predicate(head[:-1], "자음", stem, 0.75, "'~을 수 있다'")
        if syllable(s)[2] == L and (not _woo(s) or head.endswith(WOO_VERBS)):
            return Predicate(head, "모음", with_jong(s, 0), 0.75, "'~ㄹ 수 있다'")
        return None
    if m := re.fullmatch(r"(?P<head>.*?)(?P<s>[가-힣])(?P<end>는다|습니다)", core):
        stem = m.group("s")
        if syllable(stem)[2] == 0 or stem in ADJECTIVE_STEMS:
            return None
        return Predicate(m.group("head"), "자음", stem, 0.75 if m.group("end") == "는다" else 0.6, f"'~{m.group('end')}'")
    if m := re.fullmatch(r"(?P<head>.*?)(?P<s>[가-힣])(?P<end>니다|다|세요)", core):
        s, end = m.group("s"), m.group("end")
        want = {"니다": B, "다": N, "세요": 0}[end]
        if syllable(s)[2] != want or s in AMBIGUOUS_N or s in "한된합됩" or (_woo(s) and not m.group("head").endswith(WOO_VERBS)):
            return None
        if end == "세요" and s == "으":
            return None
        source = {"니다": "'~ㅂ니다'", "다": "'~ㄴ다'", "세요": "'~세요'"}[end]
        return Predicate(m.group("head"), "모음", with_jong(s, 0), 0.9 if end == "다" else 0.7, source)
    return None


def _bare_noun(core: str, extra: frozenset[str]) -> Predicate | None:
    """행동명사로 끝남('… 확인') / 행동명사 + '다'('… 설명다') / 행동명사 + 군더더기 한 글자('… 설명충')."""
    plain = _plain_word(core)
    known = action_noun(plain, extra)
    if known:
        return Predicate(core, "하", "", 0.85 if plain in lexicon().words else 0.75, "행동명사로 끝남('하다' 빠짐)")
    if len(plain) >= 3 and plain.endswith("다") and action_noun(plain[:-1], extra):
        return Predicate(core[:-1], "하", "", 0.75, "행동명사 + '다'('하' 빠짐)")
    if len(plain) >= 3 and plain[:-1] in lexicon().words:
        return Predicate(core[:-1], "하", "", 0.4, f"끝 글자 '{plain[-1]}'가 군더더기로 보임")
    return None


def read_predicate(body: str, extra: frozenset[str] = frozenset()) -> Predicate | None:
    """본문 끝 서술어를 읽는다(끝 문장부호·닫는 따옴표는 떼고 본다). 못 읽으면 None."""
    core = PUNCT_END.sub("", CLOSERS.sub("", PUNCT_END.sub("", body or ""))).strip()
    if not core:
        return None
    if m := DOROK_DA.match(core):
        return Predicate(m.group("head") + " ", "하", "", 0.9, "'~도록다'('하' 빠짐)")
    if (m := NDA_JUNK.match(core)) and not m.group("junk").startswith(CONNECTIVES):
        parts = syllable(m.group("keep")[-2])
        if parts and parts[2] == N and (inner := read_predicate(m.group("keep"), extra)) is not None:
            return Predicate(inner.head, inner.family, inner.stem, inner.confidence * 0.65,
                             f"'~{m.group('keep')[-2:]}' 뒤 군더더기 '{m.group('junk')}'")
    if m := HAGI_JUNK.match(core):
        factor = _stem_ok(m.group("head"), extra)
        if factor:
            return Predicate(m.group("head"), "하", "", 0.7 * factor, f"'~하기' 뒤 군더더기 '{m.group('junk')}'")
    for table, family in ((HA_ENDINGS, "하"), (DOE_ENDINGS, "되")):
        if found := _table(core, table, family, extra):
            return found
    if m := HA_JUNK.match(core):
        factor = _stem_ok(m.group("head"), extra)
        if factor:
            return Predicate(m.group("head"), "하", "", 0.45 * factor, f"'하' 뒤 '{m.group('junk')}'가 어미가 아님")
    return _generic(core) or _bare_noun(core, extra)
