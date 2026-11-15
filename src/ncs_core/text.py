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


# 보조 평면 사용자 영역(한컴 기호 글꼴의 번호 글자 등). U+F02B1~은 수행 순서의 네모 번호 󰊱󰊲…
PUA_SUPPLEMENTARY = re.compile(r"[\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]")
BOX_NUMBER_BASE = 0xF02B0


def _show_supplementary(match: re.Match) -> str:
    code = ord(match.group())
    if BOX_NUMBER_BASE < code <= BOX_NUMBER_BASE + 20:  # 󰊱 → [1]
        return f"[{code - BOX_NUMBER_BASE}]"
    return f"⟨U+{code:05X}⟩"


def visible(text: str | None) -> str:
    """기호 글꼴 문자를 읽을 수 있게 바꿔 결과에 적는다: 기본 평면 PUA → ⟨U+XXXX⟩, 네모 번호 → [n], 그 밖의 보조 평면 → ⟨U+XXXXX⟩.

    한글 글꼴이 없는 화면(브라우저·JSON 뷰어)에서 □로 깨지지 않게 하기 위한 표시 변환이며 판정에는 쓰지 않는다.
    """
    shown = PUA.sub(lambda m: f"⟨U+{ord(m.group()):04X}⟩", text or "")
    return PUA_SUPPLEMENTARY.sub(_show_supplementary, shown)


MARK_VERDICT = {X: FAIL, TRI: UNDECIDED, O: PASS}   # 체크 표시 → 검수결과
SEVERITY = (FAIL, UNDECIDED, PASS)                  # 종합할 때 이기는 순서


def worst(values: Iterable[str]) -> str:
    """판정 종합의 단 하나의 구현 — 부적합이 하나라도 있으면 부적합, 없고 판단불가가 있으면 판단불가, 나머지는 적합.

    체크 표시(O/X/△)와 검수결과(적합/부적합/판단불가) 어느 쪽을 줘도 된다. '-'(해당 없음)와 모르는 값은 무시하고, 빈 목록은 적합이다.
    행 판정(verdict), 확인서 항목(sheet.build_sheet), 요약(reporting.overall_verdict)이 모두 이 함수를 쓴다 — 우선순위를 바꿀 때 한 곳만 고친다.
    """
    seen = {MARK_VERDICT.get(value, value) for value in values}
    return next((v for v in SEVERITY if v in seen), PASS)


def verdict(checks: dict[str, str]) -> str:
    """한 행의 체크들 → 검수결과. X가 있으면 부적합, X 없이 △가 있으면 판단불가, 나머지는 적합. '-'는 무시."""
    return worst(checks.values())


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
