"""AI 문장 판정과 정정 후보 — 같은 종류의 문장을 번호 붙여 보내 고칠 문장만 받고, 받은 후보를 규칙으로 검증한다.

작업 이름 sentence_suggest(ncs_core.llm.ALLOWED_TASKS). 후보를 여러 개 받아야 해서 line_findings 대신 ask_json을 쓰고 번호 검증을 여기서 한다.
  보내는 것  [문장 종류] 교수 방법 — 규정 꼴: ~한다.  [문장] 1. … 2. …  (그 종류의 문장 줄, 최대 llm_batch개)
             문장 아래에 문맥(자리 · 같은 묶음의 앞 문장 · 뒤 문장)과 참고 문장(참고 문장 묶음에서 고른 기존 학습모듈 문장)을 붙인다.
             앞·뒤 문장이 같은 질문의 바로 윗줄·아랫줄이면 다시 적지 않고 자리만 적는다(pipeline._contexts).
             앞·뒤 문장은 같은 종류의 추천 대상 문장이고 참고 문장은 원고 밖 자료라, 원고에서 새로 나가는 글은 없다.
  받는 것    {"findings": [{"line": 문장 번호, "kind": 종결형 위반|주어 군더더기|어색한 낱말|중복 표현|문장부호|기타 표현,
                            "reason": 한 문장, "suggestions": [정정 후보, 순위 순, 최대 5개]}]}
검증(규칙은 출력 검증에만 쓴다)
- 없는 문장 번호·같은 번호의 두 번째 지적은 버린다. 사유 유형이 목록 밖이면 '기타 표현'.
- '종결형 위반'이라 했는데 원문이 규정 꼴에 맞으면(kinds.check) 사유 유형을 '기타 표현'으로 바꾼다(바꾼 지적으로 남김).
- 후보마다 validate: 규정 꼴 재검사, 원문에 없던 수치·영문 낱말·상호 금지(내용 생성 금지), 원문과 글자 유사도 하한.
  통과한 후보마다 참고 문장 묶음에서 가장 비슷한 문장을 '근거 문장'으로 붙이고(유사도 ground_min 이상일 때만),
  근거 문장이 있는 후보를 앞에, 그 안에서는 받은 순서대로 순위를 다시 매긴다(최대 5개). 버린 후보와 이유는 '버린 AI 후보'로 남긴다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ncs_core.brands import find_brands
from ncs_core.llm import ask_json

from .config import DEFAULT_CONFIG, ENDING, KINDS, LLM_TASK, OTHER_REASON, REASONS, SOURCE_AI, SuggestConfig
from .corpus import EMPTY, Corpus
from .kinds import check

SYSTEM = """당신은 NCS 학습모듈 원고의 문장 검수 보조자입니다. 아래는 종류가 같은 문장들과 그 종류의 규정 꼴입니다.
고쳐야 할 문장만 찾고, 문장마다 고친 문장 후보를 좋은 순서로 최대 5개 냅니다.
고칠 것(kind):
- 종결형 위반: 문장 끝이 규정 꼴과 다름(예: 규정 꼴이 '~한다.'인데 "설명함.", "설명할 수 있다.", 마침표 없음, 끝말 오타 "설명다.")
- 주어 군더더기: 문장 맨 앞에 문장 전체의 주어가 있음(예: 학습 목표의 "학습자는 …", 교수 방법의 "교수자는 …").
  "학습자가 …하도록 지도한다."처럼 안긴 문장의 주어는 군더더기가 아닙니다.
- 어색한 낱말: 문장의 다른 부분과 어울리지 않는 낱말, 끝말만 규정 꼴로 맞춘 엉뚱한 서술어, 글자가 빠지거나 잘못 들어간 낱말
  (예: "절차를 단계별로 저격한다.", "분석 방법을 지한다.", "개념을 요리한다.")
- 중복 표현: 같은 뜻의 말을 겹쳐 씀(예: "미리 사전에 준비한다.", "예측되어지도록")
- 문장부호: 끝이나 중간의 문장부호가 잘못됨(예: 평가 항목 끝의 마침표, "..!")
- 기타 표현: 위에 없지만 분명히 틀린 표현(겹친 조사 "요구사항을를" 등)
고치지 않을 것:
- 직무 내용이 맞는지, 교육 내용으로 적절한지 — 이 검사의 대상이 아닙니다.
- 문장이 길거나 전문 용어가 많다는 이유만으로 고르지 않습니다. 띄어쓰기만 다른 것도 고르지 않습니다.
- 확신할 수 없으면 넣지 않습니다.
문장 아래에 붙는 줄(있을 때만):
- '문맥'은 그 문장의 자리와 같은 묶음의 앞 문장·뒤 문장입니다. 자리가 이어지는 번호(예: '수행 순서 1', '수행 순서 2')는 서로 앞뒤 문장이며,
  그때는 앞 문장·뒤 문장을 따로 적지 않습니다. 흐름을 보는 데만 씁니다: 앞뒤 문장과 서술어·용어·끝말이 이어지게 고치고,
  앞뒤와 뜻이 겹치거나 어긋나는 낱말을 찾습니다. 문맥 줄 자체는 지적하지도 고치지도 않습니다(같은 문장이 번호로도 오면 그 번호에서 봅니다).
- '참고 문장'은 기존 학습모듈에서 규정 꼴을 지킨 비슷한 문장입니다. 서술어·끝말·어순 같은 표현만 참고합니다.
  참고 문장의 직무 내용·용어·수치를 가져오지 않습니다. 표현이 맞으면 참고 문장의 표현을 따른 후보를 앞 순위에 둡니다.
고친 문장(suggestions) 규칙:
- 후보마다 원문 전체를 다시 쓴 완전한 문장입니다. 바뀐 부분만 쓰지 않습니다(예: "지도한다."만 쓰면 안 됨).
  원문의 나머지 글자는 한 글자도 바꾸지 않고 그대로 둡니다.
- 틀린 부분만 고치고 규정 꼴로 끝냅니다. 직무 내용·용어·수치·영문·고유명사를 새로 넣거나 빼지 않고, 뜻을 바꾸지 않습니다.
- 후보는 검토자가 고를 수 있게 서로 다른 고친 방법으로 3~5개를 좋은 순서로 냅니다(다른 서술어·낱말, 다른 조사·어순,
  규정 꼴 안에서 다른 끝말 등). 문맥상 맞는 고침이 하나뿐일 때만 하나를 냅니다.
- 문장 앞의 번호·글머리 기호는 넣지 않습니다. 같은 후보를 두 번 넣지 않습니다.
반드시 JSON 객체 하나만 출력합니다:
{"findings": [{"line": <문장 번호(정수)>, "kind": "종결형 위반|주어 군더더기|어색한 낱말|중복 표현|문장부호|기타 표현",
 "reason": "<무엇이 틀렸는지 한 문장>", "suggestions": ["<고친 문장 1순위>", "<2순위>"]}]}
고칠 문장이 없으면 {"findings": []}."""

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


def _cut(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def prompt(kind: str, bodies: list[str], *, contexts: list[dict] | None = None, references: list[list[dict]] | None = None,
           config: SuggestConfig = DEFAULT_CONFIG) -> str:
    """contexts: 문장마다 {'자리','앞','뒤'}(없으면 빈 값), references: 문장마다 참고 문장 [{'문장',…}]. 둘 다 없으면 문장 줄만 보낸다."""
    lines = []
    for no, body in enumerate(bodies, 1):
        lines.append(f"{no}. {body}")
        context = contexts[no - 1] if contexts and no - 1 < len(contexts) else None
        if context and config.context_chars > 0:
            parts = [f"{label}: {_cut(context.get(key, ''), config.context_chars)}"
                     for label, key in (("자리", "자리"), ("앞 문장", "앞"), ("뒤 문장", "뒤")) if (context.get(key) or "").strip()]
            if parts:
                lines.append("   문맥 — " + " | ".join(parts))
        found = references[no - 1] if references and no - 1 < len(references) else None
        if found:
            lines.append("   참고 문장 — " + " / ".join(f"「{ref['문장']}」" for ref in found[: config.max_references]))
    return f"[문장 종류] {kind} — 규정 꼴: {KINDS[kind]}\n[문장]\n" + "\n".join(lines)


def _suggestions(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def ground(kind: str, text: str, corpus: Corpus, config: SuggestConfig = DEFAULT_CONFIG) -> dict | None:
    """후보 문장의 근거 문장 — 참고 문장 묶음에서 가장 비슷한 같은 종류 문장({'문장','출처','자리','유사도'}). 없으면 None."""
    found = corpus.find(kind, text, limit=1, minimum=config.ground_min)
    return found[0] if found else None


def screen(kind: str, body: str, finding: dict, model: str, *, extra: frozenset[str] = frozenset(), corpus: Corpus = EMPTY,
           config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """지적 하나의 후보들을 검증 → {'후보': [순위 붙은 후보], '버린': [{'문장','이유'}]}. 같은 후보가 두 번 오면 한 번만 본다.
    통과한 후보에 근거 문장을 붙이고, 근거 문장이 있는 후보를 앞에(그 안에서는 받은 순서) 두어 순위를 매긴다."""
    passed, dropped, seen = [], [], set()
    for text in finding["suggestions"]:
        if text in seen:
            continue
        seen.add(text)
        why = validate(kind, body, text, extra=extra, config=config)
        if why:
            dropped.append({"문장": text, "이유": why})
        else:
            passed.append((text, ground(kind, text, corpus, config)))
    passed.sort(key=lambda item: item[1] is None)      # 안정 정렬 — 근거 문장이 있는 후보가 앞, 같은 쪽 안에서는 AI가 낸 순서
    accepted = [{"순위": rank, "문장": text, "출처": SOURCE_AI, "근거": [finding["reason"] or "AI가 다듬음", "규칙 재검사 통과"],
                 "근거 문장": basis, "모델": model} for rank, (text, basis) in enumerate(passed[: config.max_candidates], 1)]
    return {"후보": accepted, "버린": dropped}


def ask_lines(kind: str, bodies: list[str], *, contexts: list[dict] | None = None, references: list[list[dict]] | None = None,
              extra: frozenset[str] = frozenset(), corpus: Corpus = EMPTY, asker=None,
              config: SuggestConfig = DEFAULT_CONFIG) -> tuple[dict[int, dict], list[dict], str]:
    """같은 종류 문장들 → ({문장 순번(0부터): {'kind','reason','후보','버린'}}, 사유를 바꾼 지적 목록, 모델 이름).

    contexts·references: prompt 참고(문장마다 문맥과 참고 문장). corpus: 후보의 근거 문장을 찾을 참고 문장 묶음.
    asker: 테스트에서 LLM 대신 넣는 함수((종류, 문장 목록) → {'data': {'findings': […]}, 'model': …}). 부를 수 없으면 LlmError.
    """
    if asker is not None:
        reply = asker(kind, bodies)
    else:
        user = prompt(kind, bodies, contexts=contexts, references=references, config=config)
        reply = ask_json(LLM_TASK, SYSTEM, user, max_output_tokens=config.llm_output_tokens).__dict__
    model = str(reply.get("model") or "")
    items = (reply.get("data") or {}).get("findings")
    out: dict[int, dict] = {}
    relabeled: list[dict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            no = int(item.get("line"))
        except (TypeError, ValueError):
            continue
        if not 1 <= no <= len(bodies) or no - 1 in out:
            continue
        reason_kind = str(item.get("kind") or "").strip()
        reason_kind = reason_kind if reason_kind in REASONS else OTHER_REASON
        reason = str(item.get("reason") or "").strip()
        body = bodies[no - 1]
        if reason_kind == ENDING and check(kind, body, extra)[0] is True:
            note = "끝말은 규정 꼴에 맞음 — AI의 '종결형 위반'을 '기타 표현'으로 바꿈"
            relabeled.append({"문장": body, "이유": note})
            reason_kind, reason = OTHER_REASON, f"{reason} ({note})".strip()
        finding = {"kind": reason_kind, "reason": reason, "suggestions": _suggestions(item.get("suggestions"))}
        out[no - 1] = {"kind": reason_kind, "reason": finding["reason"], **screen(kind, body, finding, model, extra=extra, corpus=corpus, config=config)}
    return out, relabeled, model
