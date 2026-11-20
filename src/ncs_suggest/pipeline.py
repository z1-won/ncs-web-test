"""원고 문장 추천(REQ-02-004) — 원고 전체(구성별·문장별 카드) 또는 문장 하나(종류 지정)에 규칙 후보·참고 예문·AI 후보를 낸다.

카드 하나 = 규정 꼴을 어겼거나 다듬을 표현이 있는 문장 하나:
  {'번호','구성','종류','자리','원문','본문','앞 번호','상태'('규칙 위반'|'표현 다듬기'),'사유','규정 꼴',
   '후보': [{'순위','문장','출처','근거','신뢰도','점수','바뀐 곳'}] (최대 5), '추천 없음': 이유|None,
   '참고 예문': [...], '버린 AI 후보': [...]}
후보가 없으면 '추천 없음(사람이 고쳐야 함)'으로 정직하게 둔다. 원고 본문은 고치지 않는다. 채택은 집필자가 화면에서 한다.
"""

from __future__ import annotations

from pathlib import Path

from ncs_core.documents import load_document

from .config import DEFAULT_CONFIG, KINDS, NO_SUGGESTION, SuggestConfig
from .examples import similar
from .extract import Sentence, collect, split_prefix, verbs_in
from .kinds import check
from .llm_suggest import ai_candidates
from .rewrite import candidates

ASSUMPTIONS = {
    "역할": "종결·표현을 규칙으로 다듬은 후보만 제시합니다. 직무 내용을 새로 만들거나 교육 내용의 적절성을 판정하지 않습니다. 채택은 집필자가 합니다.",
    "출처 표시": "후보마다 '규칙 기반' 또는 'AI 생성'을 적습니다(AI 문장은 집필자 서약서 고지 대상일 수 있음). 참고 예문은 같은 원고의 규정을 지킨 문장입니다.",
    "검사 범위": "학습모듈의 목표·학습 목표 · 차례 학습명·학습 내용명 · 수행 내용 제목·수행 순서 네모 번호 줄 · 교수 방법·학습 방법 · 평가 항목",
    "행동명사": "ncs_core 행동명사 목록 + '~화' + 같은 원고에서 'W한다'로 쓰인 낱말. 모르는 낱말로 끝나면 '하다'를 붙이지 않습니다.",
}


def _no_reason(kind: str, ok: bool | None) -> str:
    if ok is None:
        return f"{NO_SUGGESTION} — 규정 꼴인지 확인하지 못해 후보를 만들지 않음(행동명사 목록에 없는 낱말)"
    return f"{NO_SUGGESTION} — 끝말을 '{KINDS[kind]}' 꼴로 확실하게 바꿀 수 없음(서술어를 읽지 못했거나 불규칙 활용·모르는 낱말)"


def card(sentence: Sentence, *, extra: frozenset[str] = frozenset(), pool: list[tuple[str, str]] | None = None,
         use_llm: bool = False, asker=None, config: SuggestConfig = DEFAULT_CONFIG) -> dict | None:
    """문장 하나의 추천 카드. 규정에 맞고 다듬을 것도 없으면 None."""
    ok, reasons = check(sentence.kind, sentence.body, extra)
    rule = candidates(sentence.kind, sentence.body, extra=extra, config=config)
    if ok is True and not rule:
        return None
    status = "규칙 위반" if ok is False else "확인 필요" if ok is None else "표현 다듬기"
    if ok is True:
        reasons = sorted({r for c in rule for r in c["근거"]})
    result = {"구성": sentence.part, "종류": sentence.kind, "자리": sentence.where, "원문": sentence.text, "본문": sentence.body,
              "앞 번호": sentence.prefix, "상태": status, "사유": reasons, "규정 꼴": KINDS[sentence.kind],
              "후보": list(rule), "추천 없음": None, "참고 예문": similar(sentence.body, pool or [], config=config),
              "버린 AI 후보": [], "AI": None}
    if use_llm:
        accepted, dropped, state = ai_candidates(sentence.kind, sentence.body, reasons, before=sentence.before, after=sentence.after,
                                                 taken={c["문장"] for c in rule}, extra=extra, asker=asker, config=config)
        result["후보"] += accepted
        result["버린 AI 후보"] = dropped
        result["AI"] = state
    result["후보"] = sorted(result["후보"], key=lambda c: -c["점수"])[: config.max_candidates]
    for rank, item in enumerate(result["후보"], 1):
        item["순위"] = rank
    if not result["후보"]:
        result["추천 없음"] = _no_reason(sentence.kind, ok)
    return result


def suggest_sentence(text: str, kind: str, *, before: str = "", after: str = "", use_llm: bool = False, asker=None,
                     config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """문장 하나 + 종류 → 카드. 규정에 맞으면 '상태': '규정에 맞음'과 빈 후보."""
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 문장 종류: {kind} (가능: {', '.join(KINDS)})")
    if not (text or "").strip():
        raise ValueError("추천받을 문장을 넣으세요")
    prefix, body = split_prefix(text)
    sentence = Sentence(kind, "직접 입력", "직접 입력", text.strip(), prefix, body, before, after)
    found = card(sentence, use_llm=use_llm, asker=asker, config=config)
    if found is None:
        found = {"구성": "직접 입력", "종류": kind, "자리": "직접 입력", "원문": text.strip(), "본문": body, "앞 번호": prefix,
                 "상태": "규정에 맞음", "사유": [], "규정 꼴": KINDS[kind], "후보": [], "추천 없음": None, "참고 예문": [],
                 "버린 AI 후보": [], "AI": None}
    found["번호"] = "s1"
    return found


def suggest_manuscript(path: Path | str, *, use_llm: bool = False, asker=None, config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """원고(hwp/hwpx) → 구성별 추천 카드와 요약. use_llm: 걸린 문장마다 AI 후보도 묻는다(설정·승인·허용 목록이 있을 때만 실제 호출)."""
    document = load_document(path)
    sentences = collect(document)
    extra = verbs_in(document)
    pools: dict[str, list[tuple[str, str]]] = {}
    for s in sentences:
        if check(s.kind, s.body, extra)[0] is True:
            pools.setdefault(s.kind, []).append((s.body, s.where))
    cards, unknown, asked, ai_state = [], 0, 0, None
    for s in sentences:
        if check(s.kind, s.body, extra)[0] is None:
            unknown += 1
        ask = use_llm and asked < config.llm_max_sentences and not (ai_state or "").startswith("AI 미사용")
        found = card(s, extra=extra, pool=pools.get(s.kind), use_llm=ask, asker=asker, config=config)
        if found is None:
            continue
        if ask:
            asked += 1
            ai_state = found["AI"]
        found["번호"] = f"s{len(cards) + 1}"
        cards.append(found)
    parts: list[dict] = []
    for found in cards:
        if not parts or parts[-1]["구성"] != found["구성"]:
            parts.append({"구성": found["구성"], "문장": []})
        parts[-1]["문장"].append(found)
    violations = [c for c in cards if c["상태"] == "규칙 위반"]
    unsure = [c for c in cards if c["상태"] == "확인 필요"]
    notes = []
    if not sentences:
        notes.append("추천 대상 문장을 찾지 못했습니다(개요·차례·본문 구조를 읽지 못함). 원고 양식을 확인하세요.")
    if document.format == "hwp":
        notes.append("hwp 원고는 문단 스타일이 없어 수행 순서 네모 번호를 첫 글자로 찾습니다. hwpx를 권장합니다.")
    if unknown:
        notes.append(f"끝 낱말이 행동명사 목록에 없어 판정하지 못한 문장 {unknown}개는 '확인 필요'로 두고 추천하지 않았습니다.")
    llm = {"요청": use_llm, "상태": ai_state or ("AI 미사용 — 요청하지 않음" if not use_llm else "AI 미사용 — 물을 문장 없음"),
           "물은 문장 수": asked}
    return {
        "원고": Path(path).name, "형식": document.format,
        "요약": {"검사한 문장": len(sentences), "규칙 위반": len(violations), "확인 필요": len(unsure), "표현 다듬기": len(cards) - len(violations) - len(unsure),
               "추천 있음": sum(1 for c in cards if c["후보"]), "추천 없음": sum(1 for c in cards if not c["후보"]),
               "종류별 검사 수": {kind: n for kind in KINDS if (n := sum(1 for s in sentences if s.kind == kind))}},
        "구성": parts, "AI": llm, "알림": notes, "가정": ASSUMPTIONS,
    }
