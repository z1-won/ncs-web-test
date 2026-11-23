"""AI 문장 판정과 정정 후보 — 모은 문장을 원고 블록 하나로, 볼 종류를 요청 블록으로 Claude에 묻고, 받은 후보를 규칙으로 검증한다.

호출은 ncs_llmreview.claude.generate_json(공식 anthropic SDK, 프롬프트 캐시, 구조화 출력, 디스크 캐시, 작업 이름 sentence_suggest).
  system      prompts/00_문장추천.md의 절(원고마다 같음)
  원고 블록    [원고 문장] ## 교수 방법 (규정 꼴: ~한다.)  [41] …  [42] …   — 모은 문장을 종류별로 번호 붙여 한 번씩(캐시됨)
              문장 아래에 '자리'(그 문장이 놓인 곳)와 '참고 문장'(참고 문장 묶음에서 고른 기존 학습모듈 문장)을 붙인다(있을 때만).
              같은 묶음의 앞뒤 문장은 블록 안에서 바로 윗줄·아랫줄이라 따로 적지 않는다. 참고 문장은 원고 밖 자료라 원고에서 새로 나가는 글은 없다.
  요청 블록    [검토 요청] - 교수 방법 (규정 꼴: ~한다.): 문장 [41]~[52]       — 이번에 볼 종류와 번호 범위
  받는 것      {"findings": [{"line": 문장 번호, "kind": 종결형 위반|주어 군더더기|어색한 낱말|중복 표현|문장부호|기타 표현,
                              "reason": 한 문장, "suggestions": [정정 후보, 순위 순]}]}  (out_schema)
검증(규칙은 출력 검증에만 쓴다)
- 이번에 묻지 않은 문장 번호·같은 번호의 두 번째 지적은 버린다. 사유 유형이 목록 밖이면 '기타 표현'.
- '종결형 위반'이라 했는데 원문이 규정 꼴에 맞으면(kinds.check) 사유 유형을 '기타 표현'으로 바꾼다(바꾼 지적으로 남김).
- 후보마다 validate: 규정 꼴 재검사, 원문에 없던 수치·영문 낱말·상호 금지(내용 생성 금지), 원문과 글자 유사도 하한.
  통과한 후보마다 참고 문장 묶음에서 가장 비슷한 문장을 '근거 문장'으로 붙이고(유사도 ground_min 이상일 때만),
  근거 문장이 있는 후보를 앞에, 그 안에서는 받은 순서대로 순위를 다시 매긴다(최대 5개). 버린 후보와 이유는 '버린 AI 후보'로 남긴다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from ncs_core.brands import find_brands
from ncs_llmreview.prompts import SECTION

from .config import DEFAULT_CONFIG, ENDING, KINDS, OTHER_REASON, REASONS, SOURCE_AI, SuggestConfig
from .corpus import EMPTY, Corpus
from .kinds import check

PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "00_문장추천.md"

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


def sections() -> dict[str, str]:
    """prompts/00_문장추천.md의 '## [이름]' 아래 코드 블록들(ncs_llmreview.prompts와 같은 md 규칙)."""
    return {m.group(1): m.group(2) for m in SECTION.finditer(PROMPT_FILE.read_text(encoding="utf-8"))}


def build_system() -> str:
    own = sections()
    return "\n\n".join(own[name].strip() for name in ("역할", "원고 입력", "고칠 것", "고치지 않을 것", "고친 문장 규칙", "규칙"))


def out_schema() -> dict:
    """구조화 출력 스키마 — object마다 모든 속성 required. 후보 수(최대 5개)는 코드가 자른다."""
    item = {"type": "object",
            "properties": {"line": {"type": "integer"}, "kind": {"type": "string", "enum": list(REASONS)},
                           "reason": {"type": "string"}, "suggestions": {"type": "array", "items": {"type": "string"}}},
            "required": ["line", "kind", "reason", "suggestions"], "additionalProperties": False}
    return {"type": "object", "properties": {"findings": {"type": "array", "items": item}}, "required": ["findings"],
            "additionalProperties": False}


def document_text(numbered: dict[int, tuple[str, str]], extras: dict[int, dict] | None = None) -> str:
    """원고 블록 — {문장 번호: (종류, 본문)}(같은 종류끼리 번호가 이어짐) → '[원고 문장]\\n## 종류 (규정 꼴: …)\\n[n] 본문 …'.
    extras: {문장 번호: {'자리': 그 문장이 놓인 곳, '참고 문장': [참고 문장 묶음에서 고른 문장]}} — 있으면 문장 아래 줄로 붙인다(REQ-02-004)."""
    parts, last = ["[원고 문장]"], None
    for no, (kind, body) in numbered.items():
        if kind != last:
            parts.append(f"\n## {kind} (규정 꼴: {KINDS[kind]})")
            last = kind
        parts.append(f"[{no}] {body}")
        extra = (extras or {}).get(no) or {}
        if extra.get("자리"):
            parts.append(f"   자리 — {extra['자리']}")
        if extra.get("참고 문장"):
            parts.append("   참고 문장 — " + " / ".join(f"「{text}」" for text in extra["참고 문장"]))
    return "\n".join(parts)


def build_request(group: list[tuple[str, list[int]]]) -> str:
    """요청 블록 — [(종류, 그 종류에서 이번에 볼 문장 번호들(이어진 번호))]."""
    lines = [sections()["요청 머리"].strip()]
    for kind, numbers in group:
        span = f"[{numbers[0]}]" if len(numbers) == 1 else f"[{numbers[0]}]~[{numbers[-1]}]"
        lines.append(f"- {kind} (규정 꼴: {KINDS[kind]}): 문장 {span}")
    return "\n".join(lines)


def parse(data: dict, asked: dict[int, tuple[str, str]], model: str, *, extra: frozenset[str] = frozenset(), corpus: Corpus = EMPTY,
          config: SuggestConfig = DEFAULT_CONFIG) -> tuple[dict[int, dict], list[dict], int]:
    """모델 JSON → ({문장 번호: {'kind','reason','후보','버린'}}, 사유를 바꾼 지적 목록, 버린 지적 수).
    asked: 이번에 물은 {문장 번호: (종류, 본문)}."""
    items = (data or {}).get("findings")
    out: dict[int, dict] = {}
    relabeled: list[dict] = []
    dropped = 0
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        try:
            no = int(item.get("line"))
        except (TypeError, ValueError):
            dropped += 1
            continue
        if no not in asked or no in out:
            dropped += 1
            continue
        kind, body = asked[no]
        reason_kind = str(item.get("kind") or "").strip()
        reason_kind = reason_kind if reason_kind in REASONS else OTHER_REASON
        reason = str(item.get("reason") or "").strip()
        if reason_kind == ENDING and check(kind, body, extra)[0] is True:
            note = "끝말은 규정 꼴에 맞음 — AI의 '종결형 위반'을 '기타 표현'으로 바꿈"
            relabeled.append({"문장": body, "이유": note})
            reason_kind, reason = OTHER_REASON, f"{reason} ({note})".strip()
        finding = {"kind": reason_kind, "reason": reason, "suggestions": _suggestions(item.get("suggestions"))}
        out[no] = {"kind": reason_kind, "reason": finding["reason"], **screen(kind, body, finding, model, extra=extra, corpus=corpus, config=config)}
    return out, relabeled, dropped
