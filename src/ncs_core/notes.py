"""비고 문장 틀 — 엔진이 검수자가 읽을 문장을 만들 때 쓰는 작은 도우미.

규칙(PoC2_규칙_비고문구_v2-1): 1층(규칙) 문장은 항상 한 줄, 원고·기준 문구는 「」, 원인은 뒤에 괄호.
여러 사례는 lines()로 줄을 나눠 번호를 붙인다 — 확인서(sheet.summarize_remarks)가 줄 단위로 쌓고 자른다.
"""

MAX_CASES = 5


def lines(cases: list[str], limit: int = MAX_CASES, unit: str = "건") -> str:
    """사례 목록 → 한 건이면 그대로, 여럿이면 '1. …\\n2. …', limit 넘으면 '외 n건'."""
    cases = [c for c in cases if c]
    if not cases:
        return ""
    if len(cases) == 1:
        return cases[0]
    shown = [f"{i + 1}. {c}" for i, c in enumerate(cases[:limit])]
    if len(cases) > limit:
        shown.append(f"외 {len(cases) - limit}{unit}")
    return "\n".join(shown)
