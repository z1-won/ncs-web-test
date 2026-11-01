"""F02 차례 ②: ‘학습 내용명’은 행동명사로 종결하였는가?

행동명사 = ‘~하다’를 붙였을 때 뜻이 통하는 단어(예: 제시·파악·이해·분석). 글자 모양으로는 판정할 수 없어
패키지에 실린 행동명사 목록(ncs_core/data/action_nouns.txt — 표준국어대사전에서 ‘W하다’ 동사 표제어를 확인한
단어와 사람이 승인한 단어)으로 판정한다. 검수 실행은 네트워크를 쓰지 않는다.

  O  학습 내용명의 머리어(마지막 단어)가 목록에 있음
  △  목록에 없음 — 사전이 모르는 것일 뿐 틀렸다는 뜻은 아니므로 사람이 확인한다. 미확인 단어는 진단에 모인다.
"""

import re

from ncs_core import O, TRI, verdict, visible
from ncs_core.lexicon import action_nouns

ITEM_ID = "F02-차례-②"
CHECK = "행동명사 종결"
TRAILING_NOTE = re.compile(r"\s*[\(（][^)）]*[\)）]\s*$")  # 끝의 괄호 보충 설명 "(실습)"
# 나열 표지: 공백, 가운뎃점·빗금·쉼표, '및', 조사 '와/과'로 이어진 마지막 조각이 종결어다.
SEPARATOR = re.compile(r"[\s·ㆍ・/,，]+|(?<=\S)(?:\s*및\s*)(?=\S)")
TRAILING_PARTICLE = re.compile(r"(와|과)$")


def head_word(name: str) -> str:
    """학습 내용명의 머리어(마지막 단어). 끝의 괄호 설명·문장부호를 떼고 나열 표지로 나눈 마지막 조각."""
    text = TRAILING_NOTE.sub("", name).strip().rstrip(".。,")
    pieces = [p for p in SEPARATOR.split(text) if p]
    return pieces[-1] if pieces else text


def classify(word: str, lexicon: frozenset[str]) -> tuple[str, str | None]:
    """→ (체크값, 비고). 목록에 있으면 O, 아니면 △."""
    if not word:
        return TRI, "학습 내용명이 비어 있음"
    if word in lexicon:
        return O, None
    return TRI, f"행동명사 여부 확인 필요: '{word}'"


def check_toc2(toc: dict, lexicon: frozenset[str] | None = None) -> list[dict]:
    lexicon = action_nouns() if lexicon is None else lexicon
    rows = []
    for sub in toc["내용"]:
        word = head_word(sub["text"])
        value, note = classify(word, lexicon)
        checks = {CHECK: value}
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": f"section0 > 차례 > {sub['no']}-{sub['sub']}",
                "원고": visible(sub["text"]),
                "머리어": word,
                "체크": checks,
                "판정": verdict(checks),
                "비고": {CHECK: note} if note else {},
                "수정 제안": None,
            }
        )
    if not rows:
        rows.append(
            {
                "item_id": ITEM_ID,
                "region_path": "section0 > 차례",
                "원고": None,
                "머리어": None,
                "체크": {CHECK: TRI},
                "판정": verdict({CHECK: TRI}),
                "비고": {CHECK: "차례에서 학습 내용명(N-M.)을 읽지 못해 판단할 수 없음"},
                "수정 제안": None,
            }
        )
    return rows


def unknown_words(rows: list[dict]) -> list[str]:
    """②에서 △로 남은 머리어 목록(진단용). 사전 갱신 스크립트가 읽는다."""
    return sorted({r["머리어"] for r in rows if r["item_id"] == ITEM_ID and r["체크"].get(CHECK) == TRI and r.get("머리어")})
