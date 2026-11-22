"""LLM 답 검증 — 코드가 확실히 확인할 수 있는 것만 본다.

버리는 것: 보낸 검수 대상에 없는 n, 인용 없음, 그 문단에 글자 그대로 없는 인용(모델이 지어낸 답).
표시만 하는 것: 공백만 다른 인용, 정해 둔 문제 종류 밖, 수정 문장이 원문과 같음.
"""

from __future__ import annotations

import re


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def verify(chunk: dict, answer, kinds: list[str]) -> tuple[list[dict], list[dict]]:
    targets = {item["n"]: item["글"] for item in chunk.get("검수 대상", [])}
    kept, dropped = [], []
    findings = answer if isinstance(answer, list) else answer.get("지적") if isinstance(answer, dict) else None
    if not isinstance(findings, list):
        return [], [{"검증": "형식 오류 — '지적' 목록이 없음"}]
    for f in findings:
        if not isinstance(f, dict):
            dropped.append({"검증": "형식 오류"})
            continue
        f = dict(f)
        try:
            n = int(f.get("n"))
        except (TypeError, ValueError):
            n = None
        text = targets.get(n)
        quote = (f.get("인용") or "").strip()
        notes = []
        if text is None:
            dropped.append({**f, "검증": "버림 — 보낸 검수 대상에 없는 n"})
            continue
        f["n"] = n
        if not quote:
            dropped.append({**f, "검증": "버림 — 인용 없음"})
            continue
        if quote not in text:
            if _squash(quote) and _squash(quote) in _squash(text):
                notes.append("인용 공백만 다름")
            else:
                dropped.append({**f, "검증": "버림 — 인용이 원문에 없음"})
                continue
        if kinds and f.get("문제") not in kinds:
            notes.append(f"문제 종류 밖({f.get('문제')})")
        if _squash(f.get("수정 문장")) == _squash(text):
            notes.append("수정 문장이 원문과 같음")
        f["검증"] = "통과" + (f" ({', '.join(notes)})" if notes else "")
        kept.append(f)
    return kept, dropped
