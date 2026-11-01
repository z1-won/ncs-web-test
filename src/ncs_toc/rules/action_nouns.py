"""F02 차례 ②: ‘학습 내용명’은 행동명사로 종결하였는가?

행동명사 = ‘~하다’를 붙였을 때 뜻이 통하는 단어(예: 제시·파악·이해·분석). 판정은 ncs_core.lexicon이 한다:
  (1) 머리어 W 추출 → (2) 저장 목록에 있으면 O → (3) 없으면 표준국어대사전 API로 ‘W하다’ 조회
  → (4) 동사 표제어 있으면 목록에 추가하고 O → (5) 없으면 X(기록). 조회 불가(인증키 없음·오류)면 △.
운용 전에 scripts/build_action_nouns.py로 목록을 미리 채워 두면 검수 중 조회는 예외가 된다.
"""

import re

from ncs_core import TRI, verdict, visible
from ncs_core.lexicon import ActionNounLexicon, default_lexicon

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


def check_toc2(toc: dict, lexicon: ActionNounLexicon | None = None) -> list[dict]:
    lexicon = default_lexicon() if lexicon is None else lexicon
    rows = []
    for sub in toc["내용"]:
        word = head_word(sub["text"])
        value, note = lexicon.judge(word)
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
                "수정 제안": "학습 내용명을 행동명사(‘~하다’가 붙는 명사)로 종결" if value == "X" else None,
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
    """②에서 △로 남은 머리어(사전 조회 불가 등). 진단에 실어 사람이 보게 한다."""
    return sorted({r["머리어"] for r in rows if r["item_id"] == ITEM_ID and r["체크"].get(CHECK) == TRI and r.get("머리어")})
