"""문장 종류별 규정 꼴 판정 — AI 출력 검증에만 쓴다: AI 정정 후보가 규정을 지키는지, '종결형 위반'이라 한 원문이 정말 어겼는지.

종결 판정은 엔진과 같은 코어 도우미를 쓴다: 행동 문장 '~한다.'는 ncs_core.sentences.judge_action_sentence,
행동명사는 ncs_core.lexicon(저장 목록만 — 추천 중에는 사전 API를 부르지 않고 목록 파일에도 쓰지 않는다).
판정이 None이면 '확인 못 함'(예: 목록에 없는 낱말) — 그 AI 후보는 버린다.
"""

from __future__ import annotations

import re
from functools import lru_cache

from ncs_core import O
from ncs_core.lexicon import ActionNounLexicon
from ncs_core.sentences import judge_action_sentence

from .config import KINDS

GOAL_END = re.compile(r"[가-힣]\s*수\s*있다\s*\.$")
GOAL_SUBJECT = re.compile(r"^(학습자|학생|훈련생|수강생|교육생)(은|는|이|가)\s+")
TEACH_SUBJECT = re.compile(r"^(교수자|교사|강사)(은|는|이|가)\s+")
HAGI_END = re.compile(r"하기$")
EVAL_NOUN = re.compile(r"(여부|능력|수준|정도)$")
SENTENCE_END = re.compile(r"(다|[?？!！])\s*[)\"'”’]*\s*[.。]?$")
TRAILING_PUNCT = re.compile(r"[\s.。,!?！？…~]+$")
HANGUL_WORD = re.compile(r"^[가-힣]+$")
ACTION_SENTENCE_KINDS = {"수행 순서": True, "교수 방법": False, "학습 방법": False, "안전·유의 사항": False}   # 값: '~할 수 있다.' 허용


@lru_cache(maxsize=1)
def lexicon() -> ActionNounLexicon:
    """행동명사 저장 목록(읽기 전용 — resolver 없음이라 조회·기록을 하지 않는다)."""
    return ActionNounLexicon(resolver=None)


def action_noun(word: str, extra: frozenset[str] = frozenset()) -> bool | None:
    """행동명사인가 → True / False(목록이 아니라고 기록) / None(목록에 없음 — 모름).
    '~화'(명세화·정량화)와 extra(같은 원고에서 'W한다'·'W하도록'으로 쓰인 낱말, pipeline.verbs_in)는 행동명사로 본다."""
    word = re.sub(r"\(.*?\)$", "", word or "").strip()
    if not HANGUL_WORD.match(word):
        return None
    mark, _ = lexicon().judge(word)
    if mark == O or word in extra:
        return True
    if len(word) >= 3 and word.endswith("화"):
        return True
    return False if mark == "X" else None


def last_word(text: str) -> str:
    words = (text or "").split()
    return words[-1] if words else ""


def check(kind: str, body: str, extra: frozenset[str] = frozenset()) -> tuple[bool | None, list[str]]:
    """문장(번호·글머리 뗀 본문) → (규정에 맞는가, 사유 목록). None = 판정할 수 없음(후보를 만들지 않음). extra: action_noun 참고."""
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 문장 종류: {kind} (가능: {', '.join(KINDS)})")
    text = (body or "").strip()
    if not text:
        return False, ["문장이 비어 있음"]
    reasons: list[str] = []
    if kind == "학습 목표":
        if not GOAL_END.search(text):
            reasons.append("'~할 수 있다.'로 끝나지 않음")
        if GOAL_SUBJECT.match(text):
            reasons.append(f"주어 '{GOAL_SUBJECT.match(text).group(0).strip()}'가 남아 있음(목표는 주어 없이)")
        return not reasons, reasons
    if kind in ACTION_SENTENCE_KINDS:
        value, why = judge_action_sentence(text, allow_can=ACTION_SENTENCE_KINDS[kind])
        if value != O:
            reasons.append(why or "'~한다.'로 끝나지 않음")
        if kind == "교수 방법" and TEACH_SUBJECT.match(text):
            reasons.append(f"주어 '{TEACH_SUBJECT.match(text).group(0).strip()}'가 남아 있음")
        return not reasons, reasons
    if kind == "평가 항목":
        if EVAL_NOUN.search(text):
            return True, []
        if EVAL_NOUN.search(TRAILING_PUNCT.sub("", text)):
            return False, ["끝에 문장부호가 있음 — 개조식(명사형)은 마침표 없이 끝냄"]
        if SENTENCE_END.search(text):
            return False, ["서술형 문장으로 끝남 — '~여부·~능력·~수준·~정도' 등 명사형으로"]
        return True, []   # 그 밖의 명사형('~이해' 등)은 F02가 '등'으로 열어 두었다 — 추천하지 않는다
    if kind in ("학습명", "수행 내용 제목"):
        if HAGI_END.search(text) and not re.search(r"하기기$", text):
            return True, []
        if HAGI_END.search(TRAILING_PUNCT.sub("", text)):
            return False, ["제목 끝에 문장부호가 있음"]
        return False, ["'~하기'로 끝나지 않음"]
    # 학습 내용명
    if TRAILING_PUNCT.search(text):
        return False, ["끝에 문장부호가 있음"]
    word = last_word(text)
    if word.endswith("하기") and action_noun(word[:-2], extra) is not False and len(word) > 2:
        return False, ["'~하기'로 끝남 — 학습 내용명은 행동명사로 끝냄(학습명만 '~하기')"]
    known = action_noun(word, extra)
    if known is None:
        return None, [f"끝 낱말 '{word}'가 행동명사 목록에 없어 확인하지 못함"]
    return (True, []) if known else (False, [f"끝 낱말 '{word}'가 행동명사가 아님"])
