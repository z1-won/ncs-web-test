"""행동 문장 종결 판정 — 수행 순서(수행 내용 ④)·교수 방법(교수·학습 ②)·학습 방법(교수·학습 ④)이 함께 쓴다.

  O  현재형 서술 종결 '…ㄴ다.' — '다' 앞 글자에 받침 ㄴ(한·된·킨·는·친·운·힌·본…) + (괄호·따옴표) + '.'
     예: ~지도한다.  ~제공된다.  ~가르친다.  ~배운다.  ~익힌다.  ~한다).
  X  그 외 — '~이다/~있다/~없다.', 마침표 없음, 쉼표 종결, 명사형('~하기', '~함'), 형용사('크다.'), 질문형 …
  '~할 수 있다.'는 부르는 쪽이 정한다(allow_can): 수행 순서(수행 내용 ④)는 O, 교수·학습 방법 ②④는 X.
  판단불가(△)는 내지 않는다 — 안내서 A-04(문장 종결)는 자동 판정 CASE다.
"""

import re

from .text import O, X

BOX_GLYPH = re.compile(r"^[\U000F02B0-\U000F02CF]\s*")           # 네모 번호 글꼴 글자
BULLET = re.compile(r"^[•·▪ㆍ‧◦○\-–]\s*")                        # 글머리표
ENDS_DA = re.compile(r"([가-힣])다\s*[)\"'”’]*\s*\.\s*$")
ENDS_IDA = re.compile(r"(이|있|없)다\s*[)\"'”’]*\s*\.\s*$")
ENDS_CAN = re.compile(r"수\s*있다\s*[)\"'”’]*\s*\.\s*$")
CLOSING_AFTER_HANDA = re.compile(r"다\s*[)\"'”’]+\s*\.\s*$")


def _has_nieun(syllable: str) -> bool:
    """한글 음절의 받침이 ㄴ인가 — 현재형 서술 어미 '-ㄴ다/-는다'의 표지."""
    code = ord(syllable) - 0xAC00
    return 0 <= code < 11172 and code % 28 == 4


def judge_action_sentence(text: str, *, allow_can: bool = False) -> tuple[str, str | None]:
    """문장 하나 → (O/X, 사유 또는 None). 앞의 네모 번호·글머리표는 떼고 본다.
    allow_can: '~할 수 있다.' 종결을 적합으로 볼지(수행 순서는 True, 교수·학습 방법은 False)."""
    body = BULLET.sub("", BOX_GLYPH.sub("", text or "")).strip()
    if not body:
        return X, "번호만 있고 문장이 없음"
    if ENDS_CAN.search(body):
        return (O, None) if allow_can else (X, "'~할 수 있다.'로 끝남 — '~한다.'로 종결")
    if ENDS_IDA.search(body):
        return X, "'~이다/있다/없다.'로 끝남 — 행동 문장이 아님"
    if (m := ENDS_DA.search(body)) and _has_nieun(m.group(1)):
        return O, "마침표 앞에 괄호·따옴표가 있음" if CLOSING_AFTER_HANDA.search(body) else None
    if re.search(r"다\s*$", body):
        return X, "마침표 없음"
    if re.search(r"[,，]\s*$", body):
        return X, "쉼표로 끝남"
    return X, "'~한다.'로 종결되지 않음(명사형·기타)"
