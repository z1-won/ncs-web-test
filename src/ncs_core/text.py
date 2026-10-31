"""문자 정규화·비교·판정·지적사항 변환. 기존 결과와 호환된다.

정규화에서 어떤 머리 번호를 지우는지는 패키지마다 다르므로
`make_normalizer(prefix)`로 각 패키지가 자기 규칙의 `norm`/`same`을 만든다.
"""

import re
from collections.abc import Callable, Iterable

PUA = re.compile(r"[-]")
O, X, TRI, NA = "O", "X", "△", "-"
# 검수 확인서의 검수결과 표현. 한 항목의 판정은 이 셋 중 하나다.
PASS, FAIL, UNDECIDED = "적합", "부적합", "판단불가"
VERDICTS = (PASS, FAIL, UNDECIDED)

Normalizer = Callable[[str | None], str]


def make_normalizer(prefix: str | None = None) -> tuple[Normalizer, Callable[..., bool]]:
    """(norm, same)을 만든다.

    norm: 기호 글꼴(PUA) 문자를 가운뎃점으로 바꾸고, 양끝 공백과 머리 번호(prefix)를
    지운 뒤 연속 공백을 하나로 만든다.
    same: 두 문자열의 norm 결과가 같은가.
    """
    head = re.compile(prefix) if prefix else None

    def norm(text: str | None) -> str:
        value = PUA.sub("·", text or "").strip()
        if head is not None:
            value = head.sub("", value)
        return re.sub(r"\s+", " ", value)

    def same(expected: str | None, actual: str | None) -> bool:
        return norm(expected) == norm(actual)

    return norm, same


def visible(text: str | None) -> str:
    """PUA 문자를 ⟨U+XXXX⟩로 드러내 결과에 적는다."""
    return PUA.sub(lambda m: f"⟨U+{ord(m.group()):04X}⟩", text or "")


def verdict(checks: dict[str, str]) -> str:
    """X가 있으면 부적합, X 없이 △가 있으면 판단불가, 나머지는 적합. '-'는 무시."""
    values = [v for v in checks.values() if v != NA]
    if X in values:
        return FAIL
    if TRI in values:
        return UNDECIDED
    return PASS


def flatten(checklist: Iterable[dict]) -> list[dict]:
    """체크 항목 중 X·△만 지적사항 행으로 편다 (기존 키 유지)."""
    findings = []
    for row in checklist:
        for name, value in row["체크"].items():
            if value not in (X, TRI):
                continue
            notes = row["비고"]
            reason = notes.get(name, "") if isinstance(notes, dict) else "; ".join(notes)
            findings.append(
                {
                    "item_id": row["item_id"],
                    "check": name,
                    "region_path": row["region_path"],
                    "verdict": FAIL if value == X else UNDECIDED,
                    "evidence_quote": row["원고"],
                    "reason": reason,
                    "suggestion": row["수정 제안"],
                }
            )
    return findings
