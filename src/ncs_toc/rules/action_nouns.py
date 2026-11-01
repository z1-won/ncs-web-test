"""F02 차례 ②: ‘학습 내용명’은 행동명사로 종결하였는가?

행동명사 = ‘~하다’를 붙였을 때 뜻이 통하는 단어(예: 제시·파악·이해·분석). 글자 모양으로는 판정할 수 없어
패키지에 실린 행동명사 목록(ncs_core/data/action_nouns.txt)을 쓴다. 3단 판정:
  O  마지막 어절(또는 복합어의 뒷부분)이 목록에 있음
  X  비행동명사 목록(non_action_nouns.txt)에 있음, 또는 동사형으로 끝남(하기·되기·한다·된다·하는·되는)
  △  그 외 — 목록에 없음(사람 확인 후 목록에 추가), 또는 함·됨·것·다로 끝나 서술형일 수 있음
목록 조회가 먼저이므로 '포함'·'역할'처럼 함·할로 끝나는 정상 명사는 목록에 있으면 O다.
"""

import re

from ncs_core import O, TRI, X, verdict, visible
from ncs_core.lexicon import action_nouns, non_action_nouns

ITEM_ID = "F02-차례-②"
CHECK = "행동명사 종결"
# 명백한 동사형 종결 → X. (함·됨·것·다는 정상 명사와 겹칠 수 있어 △로만 둔다: 포함, 결함, 사다리)
PREDICATE_END = re.compile(r"(하기|되기|한다|된다|하는|되는)$")
MAYBE_PREDICATE_END = re.compile(r"(함|됨|것|다)$")
TRAILING_NOTE = re.compile(r"\s*[\(（][^)）]*[\)）]\s*$")  # 끝의 괄호 보충 설명 "(실습)"


def last_word(name: str) -> str:
    """학습 내용명의 마지막 어절. 끝의 괄호 설명과 문장부호는 뗀다."""
    text = TRAILING_NOTE.sub("", name).strip().rstrip(".。·,")
    return text.split()[-1] if text.split() else text


def classify(word: str, lexicon: frozenset[str], rejected: frozenset[str] = frozenset()) -> tuple[str, str | None, str | None]:
    """→ (체크값, 비고, 판정에 쓴 단어). 복합어는 뒤에서 2~3글자를 다시 찾아본다('안전관리' → '관리')."""
    if not word:
        return TRI, "학습 내용명이 비어 있음", None
    if word in lexicon:
        return O, None, word
    if word in rejected:
        return X, f"'{word}' — 행동명사가 아님(‘{word}하다’ 불성립, 확인된 단어). 행동명사로 고칠 것", word
    for n in (3, 2):
        tail = word[-n:]
        if len(word) > n and tail in lexicon:
            return O, f"복합어 '{word}'의 뒷부분 '{tail}'로 판정", tail
    if PREDICATE_END.search(word):
        return X, f"'{word}' — 동사형 종결(행동명사 아님). 명사형으로 고칠 것", word
    if MAYBE_PREDICATE_END.search(word):
        return TRI, f"'{word}' — 서술형 종결일 수 있음(함·됨·것·다). 명사면 목록에 추가, 아니면 명사형으로 고칠 것", word
    return TRI, f"'{word}' — 행동명사 목록에 없음. 사람 확인 후 목록에 추가(scripts/build_action_nouns.py)", word


def check_toc2(toc: dict, lexicon: frozenset[str] | None = None, rejected: frozenset[str] | None = None) -> list[dict]:
    lexicon = action_nouns() if lexicon is None else lexicon
    rejected = non_action_nouns() if rejected is None else rejected
    rows = []
    for sub in toc["내용"]:
        word = last_word(sub["text"])
        value, note, used = classify(word, lexicon, rejected)
        checks = {CHECK: value}
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": f"section0 > 차례 > {sub['no']}-{sub['sub']}",
                "원고": visible(sub["text"]),
                "마지막 어절": word,
                "체크": checks,
                "판정": verdict(checks),
                "비고": {CHECK: note} if note else {},
                "수정 제안": "학습 내용명을 행동명사(‘~하다’가 붙는 명사)로 종결" if value == X else None,
            }
        )
    if not rows:
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": "section0 > 차례",
                "원고": None,
                "체크": {CHECK: TRI},
                "판정": verdict({CHECK: TRI}),
                "비고": {CHECK: "차례에서 학습 내용명(N-M.)을 읽지 못해 판단할 수 없음"},
                "수정 제안": None,
            }
        )
    return rows
