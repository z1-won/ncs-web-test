"""참고 자료 ④: 기존 개발 학습모듈에서 출처가 없는 그림·표를 인용하였을 경우 기존 학습모듈명을 출처로 제시하였는가.

F14 꼴: 출처: 교육부(개발 연도). 학습모듈명(LM코드 번호). 한국직업능력연구원. p.00.
본문 '출처:' 줄 중 옛 학습모듈을 가리키는 것(LM 코드가 있거나, '교육부(연도)'로 시작하고 기관이 한국직업능력연구원·개발원인 줄)을
골라 여섯 요소가 모두 있는지 본다 — 교육부 · (연도) · 모듈명 · (LM 코드) · 기관 · 쪽. 하나라도 빠지면 X(빠진 요소를 적음).

  - LM 코드는 10자리와 옛 8자리(LM20010409_14v2)를 모두 인정한다.
  - 기관은 한국직업능력연구원과 옛 명칭 한국직업능력개발원을 모두 인정한다 — 옛 모듈 발행 당시 명칭이며
    SW제품기획 최종본 10종의 옛 모듈 출처 144줄이 모두 '개발원'(사람이 통과시킴). 명칭 확인은 참고자료 ②의 △가 맡는다.
  - 옛 모듈 출처 줄이 하나도 없으면 '-' — 출처 없는 그림·표가 옛 모듈에서 왔는지는 이전 판본과 대조해야 해서 여기서 판단하지 않는다.
"""

import re

from ncs_core import NA, O, X, visible

from .common import row

CHECK = "④ 기존 학습모듈 출처 표기"
LM = r"LM(?:\d{10}|\d{8})_\d{2}v\d+"
AGENCY = r"한국직업능력(?:연구원|개발원)"
FULL = re.compile(rf"^교육부\(\d{{4}}\)\.\s*(?P<name>[^()]+?)\s*\({LM}\)\.\s*{AGENCY}\.\s*pp?\.\s*\d+(?:\s*[-~–]\s*\d+)?\.?$")
OLD_MODULE = re.compile(rf"{LM}|^교육부\(\d{{4}}\)\..*{AGENCY}")


def missing_parts(text: str) -> list[str]:
    """F14 옛 학습모듈 출처의 여섯 요소 중 빠지거나 꼴이 다른 것."""
    out = []
    if not text.startswith("교육부"):
        out.append("저작권자 '교육부'로 시작하지 않음")
    if not re.match(r"^교육부\(\d{4}\)\.", text):
        out.append("'교육부(개발 연도).' 꼴이 아님")
    if not re.search(rf"\({LM}\)", text):
        out.append("학습모듈명 뒤 '(LM코드)' 없음")
    elif not re.search(rf"[^\s(.][^()]*\({LM}\)", text):
        out.append("LM 코드 앞에 학습모듈명 없음")
    if not re.search(AGENCY, text):
        out.append("기관 '한국직업능력연구원' 없음")
    if not re.search(r"pp?\.\s*\d+", text):
        out.append("쪽 'p.00' 없음")
    return out or ["마침표 구분이 F14 꼴과 다름"]


def check_old_module(citations: list[dict]) -> list[dict]:
    old = [c for c in citations if OLD_MODULE.search(c["text"])]
    if not old:
        return [row("④", "section1 > 출처", "", {"옛 모듈 출처": 0}, {CHECK: NA},
                    {CHECK: "옛 학습모듈을 출처로 든 줄이 없음 — 출처 없는 그림·표가 옛 모듈에서 왔는지는 이전 판본과 대조해야 함(이 항목에서 판단하지 않음)"})]
    rows, bad = [], 0
    for c in old:
        if FULL.match(c["text"].strip()):
            continue
        bad += 1
        why = missing_parts(c["text"].strip())
        rows.append(row("④", f"section1 > 문단 {c['idx']} > 출처", f"문단 {c['idx']}", visible(c["text"]), {CHECK: X},
                        {CHECK: f"「{visible(c['text'])[:50]}」 — " + ", ".join(why)},
                        "옛 학습모듈 출처는 '교육부(개발 연도). 학습모듈명(LM코드). 한국직업능력연구원. p.00.'"))
    if not bad:
        rows.append(row("④", "section1 > 출처", "", {"옛 모듈 출처": len(old)}, {CHECK: O},
                        {CHECK: f"옛 학습모듈 출처 {len(old)}줄 모두 교육부·연도·모듈명·LM 코드·기관·쪽을 갖춤"}))
    return rows
