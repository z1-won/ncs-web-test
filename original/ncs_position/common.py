"""기존 결과와 호환되는 문자 정규화·판정·지적사항 변환."""

import re

PUA = re.compile(r"[-]")
O, X, TRI, NA = "O", "X", "△", "-"
RP = "section0 > NCS-학습모듈의 위치"
LABELS3 = ("대분류", "중분류", "소분류")


def norm(s):
    s = PUA.sub("·", s or "").strip()
    return re.sub(r"^\d+\.\s*", "", s)


def same(exp, act):
    return norm(exp) == norm(act)


def visible(s):
    return PUA.sub(lambda m: f"⟨U+{ord(m.group()):04X}⟩", s or "")


def _verdict(checks):
    vals = [v for v in checks.values() if v != NA]
    if X in vals:
        return "미반영"
    if TRI in vals:
        return "판단불가"
    return "반영"


def flatten(checklist):
    F = []
    for c in checklist:
        for name, val in c["체크"].items():
            if val in (X, TRI):
                notes = c["비고"]
                reason = (
                    notes.get(name, "") if isinstance(notes, dict) else "; ".join(notes)
                )
                F.append(
                    {
                        "item_id": c["item_id"],
                        "check": name,
                        "region_path": c["region_path"],
                        "verdict": "미반영" if val == X else "판단불가",
                        "evidence_quote": c["원고"],
                        "reason": reason,
                        "suggestion": c["수정 제안"],
                    }
                )
    return F
