"""AI 후보(선택) — 같은 종류의 문장을 번호 붙여 보내 고친 문장을 받고, 규칙으로 다시 걸러 통과한 것만 쓴다.

수행 ③·평가 ④의 LLM 후보 규칙과 같은 구조다(ncs_core.llm.line_findings). 묻는 것은 두 가지다.
  정정 후보(fix_lines)      규칙에 걸린 문장 → 규정 꼴·문법만 고친 문장.   작업 이름 'sentence_suggest'
  표현 확인(wording_lines)  규정 꼴은 맞는 문장 가운데 낱말이 어색한 문장 → 이유와 고친 문장.   작업 이름 'sentence_wording'
    (끝말만 '~한다'로 맞춘 엉뚱한 낱말, 겹말처럼 규칙이 보지 못하는 것. 직무 내용이 옳은지는 묻지 않는다.)
둘 다 {"findings": [{"line": 문장 번호, "kind", "reason", "suggestion": 고친 문장}]}을 받는다.

원칙(ncs_core.llm과 같다)
- 키·반출 승인(LLM_ALLOW_UPLOAD=1)·작업 허용 목록(ncs_core.llm.ALLOWED_TASKS)이 모두 있을 때만 부른다. 아니면 규칙 후보만 낸다.
- 보내는 것은 그 종류의 문장 줄뿐이다(앞뒤 문단은 보내지 않는다). 응답은 ncs_core.llm이 캐시한다.
- 받은 문장은 버린다: 규정 꼴을 지키지 않음(kinds.check) · 원문에 없던 숫자·영문 낱말·상호가 생김(내용 생성 금지) ·
  원문과 글자 유사도가 config.ai_min_similarity 미만(내용을 바꿈) · 원문·규칙 후보와 같음. 버린 후보와 이유도 결과에 남긴다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ncs_core.brands import find_brands
from ncs_core.llm import line_findings

from .config import DEFAULT_CONFIG, KINDS, LLM_TASK, SOURCE_AI, WORDING_TASK, SuggestConfig
from .kinds import check

FIX_SYSTEM = """당신은 NCS 학습모듈 원고의 문장 다듬기 보조자입니다. 아래는 종류가 같은 문장들과 각 문장이 어긴 작성 규칙입니다.
각 문장을 규정 꼴에 맞게 고칩니다.
- 종결형과 문법·표현만 고칩니다. 직무 내용·용어·수치·영문·고유명사를 새로 넣거나 빼지 않고, 뜻을 바꾸지 않습니다.
- 문장 앞의 번호·글머리 기호는 넣지 않습니다.
- 확실하게 고칠 수 없는 문장은 넣지 않습니다.
반드시 JSON 객체 하나만 출력합니다:
{"findings": [{"line": <문장 번호(정수)>, "reason": "<무엇을 고쳤는지 한 문장>", "suggestion": "<고친 문장>"}]}
고칠 수 있는 문장이 없으면 {"findings": []}."""

WORDING_SYSTEM = """당신은 NCS 학습모듈 원고의 검수 보조자입니다. 아래는 종류가 같은 문장들입니다. 모두 종결형은 규정에 맞습니다.
낱말이나 표현이 어색한 문장만 찾습니다.
- 어색한 낱말: 문장의 다른 부분과 어울리지 않는 낱말, 끝말만 규정 꼴로 맞춘 엉뚱한 서술어, 글자가 빠지거나 잘못 들어간 낱말
  (예: "절차를 단계별로 저격한다.", "분석 방법을 지한다.")
- 중복 표현: 같은 뜻의 말을 겹쳐 쓴 표현 (예: "미리 사전에 준비한다.")
찾지 않을 것:
- 직무 내용이 맞는지, 교육 내용으로 적절한지 — 이 검사의 대상이 아닙니다.
- 문장이 길거나 전문 용어가 많다는 이유만으로 고르지 않습니다. 종결형·띄어쓰기도 대상이 아닙니다.
확신할 수 없으면 넣지 않습니다. 고친 문장은 어색한 부분만 바꾸고, 직무 내용·용어·수치·영문·고유명사를 새로 넣지 않습니다.
반드시 JSON 객체 하나만 출력합니다:
{"findings": [{"line": <문장 번호(정수)>, "kind": "어색한 낱말|중복 표현", "reason": "<왜 어색한지 한 문장>", "suggestion": "<고친 문장, 확실하지 않으면 빈 문자열>"}]}
어색한 문장이 없으면 {"findings": []}."""

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")


def _compact(text: str) -> str:
    return re.sub(r"[\s.,·()]", "", text or "")


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


def _candidate(text: str, reason: str, model: str, config: SuggestConfig) -> dict:
    return {"문장": text, "출처": SOURCE_AI, "근거": [reason or "AI가 다듬음", "규칙 재검사 통과"],
            "점수": config.ai_score, "신뢰도": config.confidence(config.ai_score), "모델": model}


def _screen(kind: str, body: str, finding: dict, taken: set[str], model: str, extra: frozenset[str], config: SuggestConfig):
    """지적 하나의 고친 문장을 걸러 (채택 후보 | None, 버린 후보 | None)."""
    text = finding["suggestion"].strip()
    if not text:
        return None, None
    if text in taken and text != body:
        return None, None      # 규칙 후보와 같은 문장 — 새 후보가 아니므로 버린 목록에도 올리지 않는다
    why = validate(kind, body, text, extra=extra, config=config)
    if why:
        return None, {"문장": text, "이유": why}
    return _candidate(text, finding["reason"], model, config), None


def fix_lines(kind: str, bodies: list[str], reasons: list[list[str]], *, taken: list[set[str]] | None = None,
              extra: frozenset[str] = frozenset(), asker=None, config: SuggestConfig = DEFAULT_CONFIG) -> tuple[list[dict], str]:
    """규칙에 걸린 같은 종류 문장들의 AI 정정 후보 → (문장별 {'후보': […], '버린': […]}, 모델 이름).

    asker: 테스트에서 LLM 대신 넣는 함수((문장 줄 목록) → {'data': {'findings': […]}, 'model': …}). 부를 수 없으면 LlmError.
    """
    user = (f"[문장 종류] {kind} — 규정 꼴: {KINDS[kind]}\n[문장]\n"
            + "\n".join(f"{no}. {body}  (걸린 규칙: {'; '.join(why) or '표현 다듬기'})" for no, (body, why) in enumerate(zip(bodies, reasons), 1)))
    findings, model = line_findings(LLM_TASK, FIX_SYSTEM, user, bodies, asker=asker)
    out = [{"후보": [], "버린": []} for _ in bodies]
    for finding in findings:
        at = finding["line"] - 1
        seen = (taken[at] if taken else set()) | {bodies[at]}
        accepted, dropped = _screen(kind, bodies[at], finding, seen, model, extra, config)
        if accepted:
            out[at]["후보"].append(accepted)
        if dropped:
            out[at]["버린"].append(dropped)
    return out, model


def wording_lines(kind: str, bodies: list[str], *, extra: frozenset[str] = frozenset(), asker=None,
                  config: SuggestConfig = DEFAULT_CONFIG) -> tuple[dict[int, dict], str]:
    """규정 꼴은 맞는 같은 종류 문장들 가운데 낱말이 어색한 문장 → ({문장 순번(0부터): {'kind','reason','후보','버린'}}, 모델 이름)."""
    user = f"[문장 종류] {kind}\n[문장]\n" + "\n".join(f"{no}. {body}" for no, body in enumerate(bodies, 1))
    findings, model = line_findings(WORDING_TASK, WORDING_SYSTEM, user, bodies, asker=asker)
    out: dict[int, dict] = {}
    for finding in findings:
        at = finding["line"] - 1
        accepted, dropped = _screen(kind, bodies[at], finding, {bodies[at]}, model, extra, config)
        out[at] = {"kind": finding["kind"] or "어색한 낱말", "reason": finding["reason"],
                   "후보": [accepted] if accepted else [], "버린": [dropped] if dropped else []}
    return out, model
