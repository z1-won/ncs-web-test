"""평가 ④: '평가 방법'의 평가 항목을 학습 목표와 연관된 구체적 내용의 개조식(명사형)으로 작성하였는가 — 학습당 1행.

규칙으로 확정할 수 있는 부분만 본다. 내용이 '구체적'인지는 판단하지 않는다(LLM 후보 몫).
  종결     O  '~여부 / ~능력 / ~수준 / ~정도'(F02 예시)로 끝남(마침표 없이)
           X  끝에 마침표('~능력.') — 개조식(명사형)은 마침표 없이 끝낸다
           X  서술형 문장('~한다.', '~할 수 있다.' 등 '다'로 끝남)·질문형
           △  그 밖의 명사형('~이해', '~방법' …) — F02가 '등'이라 했으므로 사람 확인
  목표와 구별  X  어미를 뗀 평가 항목이 같은 학습의 평가 준거 학습 목표와 거의 같음(유사도 SIMILAR 이상 또는 목표에 통째로 들어 있고
              길이가 CONTAINED 이상). 체크리스트가 "평가 항목 내용과 학습 목표가 유사하면 안 됨"을 직접 요구하므로 X.
"""

import re
from difflib import SequenceMatcher

from ncs_core import NA, O, TRI, X, verdict, visible

ITEM_ID = "F02-평가-④"
ENDING = "④ 평가 항목 명사형 종결"
DISTINCT = "④ 평가 항목과 학습 목표 구별"

NOUN_END = re.compile(r"(여부|능력|수준|정도)\s*[.。]?\s*$")
SENTENCE_END = re.compile(r"(다\s*[)\"'”’]*\s*[.。]?|[?？])\s*$")
SIMILAR = 0.85
CONTAINED = 0.7

GOAL_TAIL = re.compile(r"(할\s*수\s*있다|한다|된다|있다)\s*[.。]?\s*$")
ITEM_TAIL = re.compile(r"(하는지|했는지|할\s*수\s*있는지|할\s*수\s*있는|하는|한)?\s*(여부|능력|수준|정도)\s*[.。]?\s*$")
NOISE = re.compile(r"[\s·ㆍ‧∙•\-–—/,.()\[\]〈〉<>「」『』'\"“”‘’]")


def judge_ending(item: str) -> tuple[str, str | None]:
    if NOUN_END.search(item):
        if re.search(r"[.。]\s*$", item):
            return X, "끝에 마침표가 있음 — 개조식(명사형)은 마침표 없이 끝냄"
        return O, None
    if SENTENCE_END.search(item):
        return X, "서술형 문장으로 끝남 — '~여부·~능력·~수준·~정도' 등 명사형으로"
    return TRI, "F02 예시 어미(여부·능력·수준·정도)가 아닌 명사형 — 사람 확인"


def _stem(text: str, tail: re.Pattern) -> str:
    text = re.sub(r"^\s*[\-–•·▪ㆍ‧◦○]\s*", "", text or "")
    return NOISE.sub("", tail.sub("", text))


def near_goal(item: str, goals: list[str]) -> str | None:
    """평가 항목이 학습 목표 하나와 거의 같으면 그 목표를, 아니면 None."""
    stem = _stem(item, ITEM_TAIL)
    if len(stem) < 4:
        return None
    for goal in goals:
        target = _stem(goal, GOAL_TAIL)
        if not target:
            continue
        if SequenceMatcher(None, stem, target).ratio() >= SIMILAR:
            return goal
        if stem in target and len(stem) / len(target) >= CONTAINED:
            return goal
    return None


def check_items(regions: list[dict]) -> list[dict]:
    rows = []
    for region in regions:
        lesson = region["lesson"]
        items = [entry for table in region.get("method_items", []) for entry in table]
        goals_by_name = {}
        for units in region["criteria"]:
            for unit in units:
                goals_by_name.setdefault(NOISE.sub("", unit["name"]), []).extend(unit["goals"])
        all_goals = [g for goals in goals_by_name.values() for g in goals]
        checks, notes, bad = {}, {}, []
        if not region["found"]:
            checks[ENDING] = TRI
            notes[ENDING] = "; ".join(region["notes"]) or "평가 구역을 찾지 못함"
        elif not items:
            checks[ENDING] = TRI
            notes[ENDING] = "평가 방법 표(학습 내용 | 평가 항목)에서 평가 항목을 찾지 못함 — 원고 확인"
        else:
            endings, similar = [], []
            for entry in items:
                value, why = judge_ending(entry["item"])
                endings.append(value)
                if value != O:
                    bad.append({"학습 내용": entry["name"], "평가 항목": visible(entry["item"]), "체크": value, "사유": why})
                goal = near_goal(entry["item"], goals_by_name.get(NOISE.sub("", entry["name"])) or all_goals)
                if goal:
                    similar.append(f"「{visible(entry['item'])}」 ≈ 학습 목표 「{visible(goal)}」")
            checks[ENDING] = X if X in endings else TRI if TRI in endings else O
            if bad:
                notes[ENDING] = f"{len(items)}개 중 {len(bad)}개: " + " / ".join(
                    f"「{b['평가 항목'][-30:]}」({b['사유'].split(' — ')[0]})" for b in bad[:5]) + (" …" if len(bad) > 5 else "")
            if not all_goals:
                checks[DISTINCT] = NA
                notes[DISTINCT] = "평가 준거 학습 목표를 읽지 못해 비교 생략"
            else:
                checks[DISTINCT] = X if similar else O
                if similar:
                    notes[DISTINCT] = f"학습 목표와 거의 같은 평가 항목 {len(similar)}개 — 학습 목표를 바탕으로 더 구체적으로 쓸 것: " + " / ".join(similar[:3]) + (
                        " …" if len(similar) > 3 else "")
        result = verdict(checks)
        rows.append({"item_id": ITEM_ID, "region_path": f"section1 > 학습 {lesson} > 평가 > 평가 방법", "위치": f"학습 {lesson}",
                     "원고": {"개수": len(items), "평가 항목": [visible(e["item"]) for e in items]}, "체크": checks, "판정": result,
                     "비고": notes, "수정 제안": None if result == "적합" else
                     "평가 항목을 학습 목표보다 구체적인 내용으로 쓰고 '~여부·~능력·~수준·~정도' 등 명사형으로 종결",
                     "위반_항목": bad})
    return rows
