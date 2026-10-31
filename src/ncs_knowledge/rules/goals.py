"""F02 필요지식 ⑤: 각 학습 내용의 '학습 목표' = 개발계획서 학습 목표(수행 준거).

같음 O / 공백·문장부호만 다름 X(설정으로 O+참고) / 유사도 ≥ 임계값 윤문 △ / 그 밖·누락·본문에만 있음 X.
"""

import difflib
import re

from ncs_core import NA, O, PUA, TRI, X, visible

from .common import row


def goal_norm(text: str) -> str:
    text = re.sub(r"^\s*(\d+\.\d+|[•·▪ㆍ‧◦○\-])\s*", "", text or "")  # '1.1 ' / '•' 제거
    text = PUA.sub("·", text)
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def goal_key(text: str) -> str:
    """공백·부호·대소문자를 뺀 비교 키 (윤문 유사도 계산용)."""
    return re.sub(r"[\s·,.()\[\]/\-]", "", goal_norm(text)).lower()


def check_goals(plan: dict | None, units: list[dict], *, similarity: float, whitespace_is_difference: bool) -> list[dict]:
    rows = []
    for unit in units:
        key = f"{unit['no']}-{unit['sub']}"
        region = f"section1 > 학습 {unit['lesson']} > {key}. {visible(unit['text'])} > 학습 목표"
        actual = unit["goal"]
        if not plan:
            rows.append(row("⑤", region, [visible(a) for a in actual], {"개발계획서 학습 목표 일치": NA}, {"개발계획서": "개발계획서를 읽지 못해 대조 생략"}))
            continue
        checks, notes = {}, {}
        if unit["goal_k"] is None:
            checks["학습 목표 블록"], notes["학습 목표 블록"] = X, "제목 아래 '학습 목표' 줄을 찾지 못함"
        expected_unit = plan["내용"].get((unit["no"], unit["sub"]))
        if expected_unit is None:
            checks["개발계획서 학습 목표 일치"] = X
            notes["개발계획서 학습 목표 일치"] = f"개발계획서에 {key} 가 없음 (계획서 목록: {sorted(plan['내용'])})"
            rows.append(row("⑤", region, [visible(a) for a in actual], checks, notes))
            continue
        expected = expected_unit["goals"]
        checks["학습 목표 개수"] = O if len(expected) == len(actual) else X
        if checks["학습 목표 개수"] == X:
            notes["학습 목표 개수"] = f"본문 {len(actual)} / 개발계획서 {len(expected)}"
        exp_keys, act_keys = [goal_key(e) for e in expected], [goal_key(a) for a in actual]
        problems, soft = [], []
        for i, e in enumerate(expected):
            if i < len(actual) and goal_norm(e) == goal_norm(actual[i]):
                continue
            if exp_keys[i] in act_keys:  # 공백·문장부호만 다름
                j = act_keys.index(exp_keys[i])
                message = f'{i + 1}번째 공백·부호만 다름: 본문 "{visible(goal_norm(actual[j]))}" / 계획서 "{goal_norm(e)}"' + ("" if j == i else f" (본문 {j + 1}번째 자리)")
                (problems if whitespace_is_difference else soft).append((X, message))
                continue
            best = max(((difflib.SequenceMatcher(None, exp_keys[i], a, autojunk=False).ratio(), j) for j, a in enumerate(act_keys)), default=(0, None))
            if best[0] >= similarity:
                problems.append((TRI, f'{i + 1}번째 윤문 수준 차이(유사 {best[0]:.0%}): 본문 "{visible(goal_norm(actual[best[1]]))}" / 계획서 "{goal_norm(e)}" — 직능연 협의 여부 확인'))
            else:
                problems.append((X, f'{i + 1}번째 불일치 또는 누락: 계획서 "{goal_norm(e)}"'))
        extra = [
            a for j, a in enumerate(actual)
            if act_keys[j] not in exp_keys and not any(difflib.SequenceMatcher(None, act_keys[j], e, autojunk=False).ratio() >= similarity for e in exp_keys)
        ]
        for a in extra:
            problems.append((X, f'본문에만 있음(임의 추가 불가): "{visible(goal_norm(a))}"'))
        if problems:
            checks["개발계획서 학습 목표 일치"] = X if any(v == X for v, _ in problems) else TRI
            notes["개발계획서 학습 목표 일치"] = " / ".join(m for _, m in problems)
        else:
            checks["개발계획서 학습 목표 일치"] = O
        if soft:
            notes["개발계획서 학습 목표 일치(참고)"] = " / ".join(m for _, m in soft) + " — 통과 처리"
        rows.append(row("⑤", region, [visible(a) for a in actual], checks, notes, "개발계획서 학습 목표 문장으로 통일", 개발계획서=expected))
    return rows
