"""규칙 기반 추천 후보 만들기 — 표현 다듬기(주어 군더더기·이중 피동·겹말·중복 조사·문장부호) + 종결형 교정, 순위 매기기.

후보 하나 = 원문에 규칙 몇 개를 적용한 문장. 만든 후보는 반드시 kinds.check로 다시 판정해 규정을 지키는 것만 낸다.
점수 = 적용한 규칙 확신도 중 가장 낮은 값 × 종류별 꼴 가중치(예: 수행 순서는 '~한다.'를 '~할 수 있다.'보다 위에). 점수가 같으면 덜 바꾼 후보가 위.
직무 내용은 건드리지 않는다: 낱말을 더하는 규칙은 '하다/되다' 어미와 평가 항목의 '여부/능력'뿐이고, 지우는 규칙은 목록에 적힌 군더더기뿐이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .config import DEFAULT_CONFIG, SOURCE_RULE, SuggestConfig
from .endings import read_predicate
from .kinds import GOAL_SUBJECT, TEACH_SUBJECT, check

# 이중 피동(국립국어원 표준 화법·어문 규범 해설의 대표 예) — (틀린 줄기, 바른 줄기)
DOUBLE_PASSIVE = (("되어지", "되"), ("되어진", "된"), ("보여지", "보이"), ("보여진", "보인"), ("쓰여지", "쓰이"), ("쓰여진", "쓰인"),
                  ("잊혀지", "잊히"), ("잊혀진", "잊힌"), ("짜여지", "짜이"), ("짜여진", "짜인"), ("읽혀지", "읽히"), ("읽혀진", "읽힌"),
                  ("불려지", "불리"), ("불려진", "불린"), ("나뉘어지", "나뉘"), ("나뉘어진", "나뉜"), ("열려지", "열리"), ("닫혀지", "닫히"))
# 겹말(같은 뜻이 겹친 말) — (겹친 말, 고친 말)
REDUNDANT = (("미리 예측", "예측"), ("미리 예방", "예방"), ("미리 예비", "예비"), ("미리 준비", "준비"), ("다시 재확인", "재확인"),
             ("다시 재검토", "재검토"), ("다시 재정의", "재정의"), ("서로 상호", "상호"), ("가장 최선", "최선"), ("가장 최적", "최적"),
             ("가장 최고", "최고"), ("과반수 이상", "과반수"), ("결론적으로 말해서", "결론적으로"), ("함께 공유", "공유"),
             ("새로 신설", "신설"), ("먼저 선행", "선행"), ("직접 대면", "대면"), ("간단히 요약", "요약"))
# 겹친 조사 — 자연스러운 낱말과 겹치지 않는 짝만(을을·이가는 '마을을·아이가'와 겹쳐 넣지 않는다)
DOUBLE_PARTICLE = re.compile(r"(?<=[가-힣])(을를|를을|은는|는은|에서에서|으로로)(?=\s|$|[,.])")
SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,])")
MULTI_PUNCT = re.compile(r"([.。])[.。!?！？]+$|[!?！？]+$")
MULTI_SPACE = re.compile(r"\s{2,}")

TARGETS = {   # 종류 → [(꼴, 가중치, 끝에 붙일 문장부호)]
    "학습 목표": [("할 수 있다", 1.0, ".")],
    "수행 순서": [("한다", 1.0, "."), ("할 수 있다", 0.8, ".")],
    "교수 방법": [("한다", 1.0, ".")],
    "학습 방법": [("한다", 1.0, ".")],
    "안전·유의 사항": [("한다", 1.0, ".")],
    "평가 항목": [("능력", 0.9, ""), ("여부", 0.85, "")],
    "학습명": [("하기", 1.0, "")],
    "수행 내용 제목": [("하기", 1.0, "")],
    "학습 내용명": [("명사", 1.0, "")],
}


@dataclass
class Fix:
    text: str
    score: float                 # 적용한 규칙 확신도 중 가장 낮은 값(가장 약한 규칙이 후보의 신뢰도를 정한다)
    rules: list[str] = field(default_factory=list)
    partial: bool = False        # 표현 규칙을 일부만 적용한 후보 — 다 적용한 후보보다 아래에 둔다


def _expression_fixes(kind: str, body: str) -> list[tuple[str, float, str]]:
    """본문에 적용할 표현 규칙들 → [(고친 본문, 확신도, 규칙 설명)] — 하나씩 따로(합치는 것은 candidates가 한다)."""
    out = []
    subject = GOAL_SUBJECT if kind == "학습 목표" else TEACH_SUBJECT if kind == "교수 방법" else None
    if subject and (m := subject.match(body)):
        out.append((body[m.end():], 0.95, f"주어 군더더기 '{m.group(0).strip()}' 삭제"))
    for wrong, right in DOUBLE_PASSIVE:
        if wrong in body:
            out.append((body.replace(wrong, right), 0.9, f"이중 피동 '{wrong}~' → '{right}~'"))
    for wrong, right in REDUNDANT:
        if wrong in body:
            out.append((body.replace(wrong, right), 0.9, f"겹말 '{wrong}' → '{right}'"))
    if DOUBLE_PARTICLE.search(body):
        fixed = DOUBLE_PARTICLE.sub(lambda m: {"을를": "을", "를을": "를", "은는": "은", "는은": "는", "에서에서": "에서", "으로로": "으로"}[m.group(1)], body)
        out.append((fixed, 0.85, "겹친 조사 정리"))
    tidy = MULTI_SPACE.sub(" ", SPACE_BEFORE_PUNCT.sub(r"\1", body))
    if kind in TARGETS and TARGETS[kind][0][2] == ".":
        tidy = MULTI_PUNCT.sub(".", tidy)
    if kind in TARGETS and TARGETS[kind][0][2] == "":
        tidy = re.sub(r"[\s.。,!?！？…~]+$", "", tidy)   # 제목·명사형은 마침표 없이
    if tidy != body:
        out.append((tidy, 0.95, "문장부호·띄어쓰기 정리"))
    return out


def _endings(kind: str, body: str, extra: frozenset[str]) -> list[Fix]:
    """종결형을 종류의 규정 꼴로 바꾼 후보들."""
    predicate = read_predicate(body, extra)
    if predicate is None:
        return []
    out = []
    for target, weight, punct in TARGETS[kind]:
        form = predicate.form(target, extra)
        if form and re.sub(r"[\s.。!?！？…~]", "", form + punct) == re.sub(r"[\s.。!?！？…~]", "", body):
            out.append(Fix(form + punct, 0.95, ["끝 문장부호 정리"]))
        elif form:
            label = f"종결 {predicate.source} → '~{target}{punct}'" if target not in ("명사", "능력", "여부") else (
                f"종결 {predicate.source} → 행동명사로 끝냄" if target == "명사" else f"서술형 {predicate.source} → 명사형 '~ {target}'")
            out.append(Fix(form + punct, predicate.confidence * weight, [label]))
    return out


def _changed(before: str, after: str) -> str:
    """바뀐 곳만 짧게: 「…앞 3글자[바뀐 글자]…」 → 「…[새 글자]…」."""
    matcher = SequenceMatcher(None, before, after, autojunk=False)
    parts = []
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == "equal":
            continue
        old, new = before[a:b] or "∅", after[c:d] or "∅"
        parts.append(f"「{before[max(0, a - 4):a]}{old}」→「{before[max(0, a - 4):a]}{new}」")
    return " · ".join(parts[:3]) + (" …" if len(parts) > 3 else "")


def candidates(kind: str, body: str, *, extra: frozenset[str] = frozenset(), config: SuggestConfig = DEFAULT_CONFIG) -> list[dict]:
    """규칙 기반 후보 목록(점수 순, 최대 config.max_candidates개). 원문이 이미 규정에 맞고 고칠 표현이 없으면 빈 목록."""
    expressions = _expression_fixes(kind, body)
    combined = Fix(body, 1.0)
    for fixed, score, rule in expressions:   # 표현 규칙은 앞에서 고친 문장 위에 차례로 다시 적용한다
        again = next((f for f, _, r in _expression_fixes(kind, combined.text) if r == rule), None)
        if again is not None:
            combined = Fix(again, min(combined.score, score), combined.rules + [rule])
    bases = [combined] + ([Fix(body, 1.0, partial=True)] if combined.rules else [])
    bases += [Fix(f, s, [r], partial=True) for f, s, r in expressions if len(expressions) > 1]
    pool: list[Fix] = []
    for base in bases:
        ok, _ = check(kind, base.text, extra)
        if ok and base.rules:
            pool.append(base)
        elif ok is False:
            for fix in _endings(kind, base.text, extra):
                pool.append(Fix(fix.text, min(base.score, fix.score), base.rules + fix.rules, base.partial))
    seen, ranked = {body}, []
    order = sorted(pool, key=lambda f: (f.partial, -round(f.score, 3), 1 - SequenceMatcher(None, body, f.text, autojunk=False).ratio()))
    for fix in order:
        if fix.text in seen or check(kind, fix.text, extra)[0] is not True:
            continue
        seen.add(fix.text)
        score = fix.score * (0.9 if fix.partial else 1.0)
        ranked.append({"문장": fix.text, "출처": SOURCE_RULE, "근거": fix.rules, "점수": round(score, 3),
                       "신뢰도": config.confidence(score), "바뀐 곳": _changed(body, fix.text)})
    return ranked[: config.max_candidates]
