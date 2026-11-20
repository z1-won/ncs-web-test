"""AI 후보(선택) — 문장 하나와 앞뒤 문단, 적용 규칙을 보내 다듬은 문장 후보를 받고, 규칙으로 다시 걸러 통과한 것만 쓴다.

원칙(ncs_core.llm과 같다)
- 키·반출 승인(LLM_ALLOW_UPLOAD=1)·작업 허용 목록(ncs_core.llm.ALLOWED_TASKS)이 모두 있을 때만 부른다. 아니면 규칙 후보만 내고
  'AI 미사용 — 이유'를 적는다. 지금 허용 목록에 'sentence_suggest'가 없어 실제 호출은 일어나지 않는다(팀장 요청 이슈).
- 보내는 것은 그 문장과 앞뒤 문단 일부(config.llm_context_chars)뿐이다. 응답은 ncs_core.llm이 캐시한다.
- 받은 후보는 버린다: 규정 꼴을 지키지 않음(kinds.check) · 원문에 없던 숫자·영문 낱말·상호가 생김(내용 생성 금지) ·
  원문과 글자 유사도가 config.ai_min_similarity 미만(내용을 바꿈) · 원문·규칙 후보와 같음. 버린 후보와 이유도 결과에 남긴다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ncs_core.brands import find_brands
from ncs_core.llm import LlmError, ask_json

from .config import DEFAULT_CONFIG, KINDS, LLM_TASK, SOURCE_AI, SuggestConfig
from .kinds import check

SYSTEM = (
    "당신은 NCS 학습모듈 원고의 문장 다듬기 보조자다. 문장 하나와 그 문장의 종류·규정 꼴, 앞뒤 문단을 받는다. "
    "규정 꼴(종결형)과 문법·표현만 고친 문장 후보를 최대 3개 만든다. 직무 내용·용어·수치·영문·고유명사를 새로 넣거나 빼지 말고, "
    "뜻을 바꾸지 않는다. 확신이 없으면 후보를 내지 않는다. JSON 객체 하나로만 답한다: "
    '{"후보": [{"문장": "고친 문장", "이유": "무엇을 고쳤는지 한 문장"}]}'
)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")


def _compact(text: str) -> str:
    return re.sub(r"[\s.,·()]", "", text or "")


def prompt(kind: str, body: str, reasons: list[str], before: str, after: str, config: SuggestConfig) -> str:
    limit = config.llm_context_chars
    return (f"[문장 종류] {kind} — 규정 꼴: {KINDS[kind]}\n[걸린 규칙] {'; '.join(reasons) or '표현 다듬기'}\n"
            f"[앞 문단] {before[-limit:]}\n[문장] {body}\n[뒤 문단] {after[:limit]}")


def validate(kind: str, body: str, text: str, *, extra: frozenset[str] = frozenset(), config: SuggestConfig = DEFAULT_CONFIG) -> str | None:
    """AI 후보를 버릴 이유(없으면 None)."""
    text = (text or "").strip()
    if not text:
        return "빈 문장"
    if text == body:
        return "원문과 같음"
    ok, why = check(kind, text, extra)
    if ok is not True:
        return "규정 꼴을 지키지 않음: " + ("; ".join(why) or "확인 못 함")
    new_numbers = set(NUMBER.findall(text)) - set(NUMBER.findall(body))
    if new_numbers:
        return f"원문에 없던 수치 {', '.join(sorted(new_numbers))} — 내용 생성 금지"
    new_latin = {w.lower() for w in LATIN.findall(text)} - {w.lower() for w in LATIN.findall(body)}
    if new_latin:
        return f"원문에 없던 영문 낱말 {', '.join(sorted(new_latin))} — 내용 생성 금지"
    clear, ambiguous = find_brands(text)
    before_names = {name for name, _ in sum(find_brands(body), [])}
    added = {name for name, _ in clear + ambiguous} - before_names
    if added:
        return f"원문에 없던 상호·상품명 {', '.join(sorted(added))}"
    ratio = SequenceMatcher(None, _compact(body), _compact(text), autojunk=False).ratio()
    if ratio < config.ai_min_similarity:
        return f"원문과 너무 다름(글자 유사도 {ratio:.2f} < {config.ai_min_similarity:g}) — 내용을 바꾼 것으로 봄"
    return None


def ai_candidates(kind: str, body: str, reasons: list[str], *, before: str = "", after: str = "", taken: set[str] | None = None,
                  extra: frozenset[str] = frozenset(), asker=None, config: SuggestConfig = DEFAULT_CONFIG) -> tuple[list[dict], list[dict], str]:
    """→ (채택한 AI 후보, 버린 AI 후보 [{'문장','이유'}], 상태). asker: 테스트용 (system, user) → {'data': {...}, 'model': …}.
    LLM을 부를 수 없으면 ([], [], 'AI 미사용 — 이유')."""
    user = prompt(kind, body, reasons, before, after, config)
    try:
        answer = asker(SYSTEM, user) if asker is not None else ask_json(LLM_TASK, SYSTEM, user).__dict__
    except LlmError as error:
        return [], [], f"AI 미사용 — {error}"
    raw = (answer.get("data") or {}).get("후보") or []
    model = str(answer.get("model") or "")
    taken = set(taken or ()) | {body}
    accepted, dropped = [], []
    for entry in raw[:5]:
        text = str(entry.get("문장") if isinstance(entry, dict) else entry or "").strip()
        why = "이미 있는 후보와 같음" if text in taken else validate(kind, body, text, extra=extra, config=config)
        if why:
            dropped.append({"문장": text, "이유": why})
            continue
        taken.add(text)
        accepted.append({"문장": text, "출처": SOURCE_AI, "근거": [str(entry.get("이유") or "AI가 다듬음") if isinstance(entry, dict) else "AI가 다듬음",
                                                                "규칙 재검사 통과"],
                         "점수": config.ai_score, "신뢰도": config.confidence(config.ai_score), "모델": model})
    return accepted, dropped, f"AI 사용({model})" if model else "AI 사용"
