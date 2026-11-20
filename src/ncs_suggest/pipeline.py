"""원고 문장 추천(REQ-02-004) — 원고 전체(구성별·문장별 카드) 또는 문장 하나(종류 지정)에 규칙 후보·참고 예문·AI 후보를 낸다.

카드 하나 = 규정 꼴을 어겼거나 다듬을 표현이 있는 문장 하나:
  {'번호','구성','종류','자리','원문','본문','앞 번호','상태'('규칙 위반'|'표현 다듬기'|'확인 필요'|'표현 확인(AI)'),'사유','규정 꼴',
   '후보': [{'순위','문장','출처','근거','신뢰도','점수','바뀐 곳'}] (최대 5), '추천 없음': 이유|None,
   '참고 예문': [...], '버린 AI 후보': [...], 'AI': 상태|None}
AI는 두 가지를 묻는다(llm_suggest): 규칙에 걸린 문장의 정정 후보, 규정 꼴은 맞지만 낱말이 어색한 문장('표현 확인(AI)' 카드).
같은 종류의 문장끼리 묶어 한 번에 묻는다. 후보가 없으면 '추천 없음(사람이 고쳐야 함)'으로 정직하게 둔다.
원고 본문은 고치지 않는다. 채택은 집필자가 화면에서 한다.
"""

from __future__ import annotations

from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.llm import LlmError

from .config import AI_STATUS, DEFAULT_CONFIG, KINDS, LLM_TASK, NO_SUGGESTION, WORDING_TASK, SuggestConfig
from .examples import similar
from .extract import Sentence, collect, split_prefix, verbs_in
from .kinds import check
from .llm_suggest import fix_lines, wording_lines
from .rewrite import candidates

ASSUMPTIONS = {
    "역할": "종결·표현을 규칙으로 다듬은 후보만 제시합니다. 직무 내용을 새로 만들거나 교육 내용의 적절성을 판정하지 않습니다. 채택은 집필자가 합니다.",
    "출처 표시": "후보마다 '규칙 기반' 또는 'AI 생성'을 적습니다(AI 문장은 집필자 서약서 고지 대상일 수 있음). 참고 예문은 같은 원고의 규정을 지킨 문장입니다.",
    "검사 범위": "학습모듈의 목표·학습 목표 · 차례 학습명·학습 내용명 · 수행 내용 제목·수행 순서 네모 번호 줄 · 교수 방법·학습 방법 · 평가 항목",
    "행동명사": "ncs_core 행동명사 목록 + '~화' + 같은 원고에서 'W한다'로 쓰인 낱말. 모르는 낱말로 끝나면 '하다'를 붙이지 않습니다.",
    "AI": "AI는 같은 종류의 문장 줄만 받아 ① 규칙에 걸린 문장의 정정 후보 ② 규정 꼴은 맞지만 낱말이 어색한 문장을 냅니다. "
          "받은 문장은 규정 꼴·수치·영문·상호·원문 유사도로 다시 걸러 통과한 것만 후보로 씁니다.",
}


def _no_reason(kind: str, ok: bool | None) -> str:
    if ok is None:
        return f"{NO_SUGGESTION} — 규정 꼴인지 확인하지 못해 후보를 만들지 않음(행동명사 목록에 없는 낱말)"
    return f"{NO_SUGGESTION} — 끝말을 '{KINDS[kind]}' 꼴로 확실하게 바꿀 수 없음(서술어를 읽지 못했거나 불규칙 활용·모르는 낱말)"


def _rank(found: dict, no_reason: str, config: SuggestConfig) -> dict:
    found["후보"] = sorted(found["후보"], key=lambda c: -c["점수"])[: config.max_candidates]
    for rank, item in enumerate(found["후보"], 1):
        item["순위"] = rank
    found["추천 없음"] = None if found["후보"] else no_reason
    return found


def card(sentence: Sentence, *, extra: frozenset[str] = frozenset(), pool: list[tuple[str, str]] | None = None,
         config: SuggestConfig = DEFAULT_CONFIG) -> dict | None:
    """문장 하나의 규칙 추천 카드. 규정에 맞고 다듬을 것도 없으면 None. AI 후보는 add_ai가 나중에 붙인다."""
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
    return _rank(result, _no_reason(sentence.kind, ok), config)


def _wording_card(sentence: Sentence, info: dict, model: str, config: SuggestConfig) -> dict:
    found = {"구성": sentence.part, "종류": sentence.kind, "자리": sentence.where, "원문": sentence.text, "본문": sentence.body,
             "앞 번호": sentence.prefix, "상태": AI_STATUS, "사유": [f"{info['kind']} — {info['reason']}" if info["reason"] else info["kind"]],
             "규정 꼴": KINDS[sentence.kind], "후보": list(info["후보"]), "추천 없음": None, "참고 예문": [],
             "버린 AI 후보": list(info["버린"]), "AI": f"AI 사용({model})"}
    return _rank(found, f"{NO_SUGGESTION} — AI가 낱말이 어색하다고 본 문장이며, 쓸 수 있는 고친 문장은 받지 못함", config)


def llm_ready(asker=None) -> tuple[bool, str]:
    """AI를 부를 수 있는가 → (가능, 상태 문구). 수행 ③·평가 ④와 같이 설정·승인이 없으면 이유를 적고 규칙 결과만 낸다."""
    if asker is not None:
        return True, "AI 사용(주입된 응답)"
    from ncs_core.llm import settings, task_allowed

    blocked = [task for task in (LLM_TASK, WORDING_TASK) if not task_allowed(task)]
    if blocked:
        return False, f"AI 미사용 — 허용되지 않은 작업: {', '.join(blocked)} (ncs_core.llm.ALLOWED_TASKS)"
    cfg = settings()
    if not cfg.ready:
        return False, f"AI 미사용 — {cfg.why_not}"
    return True, f"AI 사용({cfg.model})"


def _batches(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def add_ai(entries: list[list], *, extra: frozenset[str] = frozenset(), asker=None, config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """entries: [문장, 카드|None, 규정 판정] 목록에 AI 결과를 붙인다(카드에 후보를 더하고, 어색한 문장은 새 카드로) → 통계.

    같은 종류의 문장끼리 config.llm_batch개씩 묶어 묻는다. 원고 한 건에서 묻는 문장은 config.llm_max_sentences개까지.
    """
    stats = {"호출": 0, "물은 문장 수": 0, "실패": [], "모델": ""}
    budget = config.llm_max_sentences

    def groups(wanted) -> dict[str, list[list]]:
        out: dict[str, list[list]] = {}
        for entry in entries:
            if wanted(entry):
                out.setdefault(entry[0].kind, []).append(entry)
        return out

    for kind, group in groups(lambda e: e[1] is not None).items():          # ① 규칙에 걸린 문장의 정정 후보
        for chunk in _batches(group, config.llm_batch):
            chunk = chunk[:max(budget, 0)]
            if not chunk:
                break
            budget -= len(chunk)
            try:
                results, model = fix_lines(kind, [e[0].body for e in chunk], [e[1]["사유"] for e in chunk],
                                           taken=[{c["문장"] for c in e[1]["후보"]} for e in chunk], extra=extra, asker=asker, config=config)
            except LlmError as error:
                stats["실패"].append(str(error))
                for entry in chunk:
                    entry[1]["AI"] = f"AI 호출 실패: {error}"
                continue
            stats["호출"] += 1
            stats["물은 문장 수"] += len(chunk)
            stats["모델"] = model
            for entry, result in zip(chunk, results):
                found = entry[1]
                found["후보"] += result["후보"]
                found["버린 AI 후보"] += result["버린"]
                found["AI"] = f"AI 사용({model})"
                _rank(found, found["추천 없음"] or _no_reason(entry[0].kind, entry[2]), config)

    for kind, group in groups(lambda e: e[1] is None and e[2] is True).items():   # ② 규정 꼴은 맞지만 낱말이 어색한 문장
        for chunk in _batches(group, config.llm_batch):
            chunk = chunk[:max(budget, 0)]
            if not chunk:
                break
            budget -= len(chunk)
            try:
                flagged, model = wording_lines(kind, [e[0].body for e in chunk], extra=extra, asker=asker, config=config)
            except LlmError as error:
                stats["실패"].append(str(error))
                continue
            stats["호출"] += 1
            stats["물은 문장 수"] += len(chunk)
            stats["모델"] = model
            for at, info in flagged.items():
                chunk[at][1] = _wording_card(chunk[at][0], info, model, config)
    return stats


def _ai_state(state: str, stats: dict) -> str:
    text = (f"AI 사용({stats['모델']})" if stats["모델"] else state) + f" · 호출 {stats['호출']}번, 문장 {stats['물은 문장 수']}개"
    if stats["실패"]:
        text += f", 실패 {len(stats['실패'])}번({stats['실패'][0]})"
    return text


def suggest_sentence(text: str, kind: str, *, before: str = "", after: str = "", use_llm: bool = False, asker=None,
                     config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """문장 하나 + 종류 → 카드. 규정에 맞으면 '상태': '규정에 맞음'과 빈 후보(AI가 낱말이 어색하다고 보면 '표현 확인(AI)')."""
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 문장 종류: {kind} (가능: {', '.join(KINDS)})")
    if not (text or "").strip():
        raise ValueError("추천받을 문장을 넣으세요")
    prefix, body = split_prefix(text)
    sentence = Sentence(kind, "직접 입력", "직접 입력", text.strip(), prefix, body, before, after)
    entry = [sentence, card(sentence, config=config), check(kind, body)[0]]
    state = None
    if use_llm:
        on, state = llm_ready(asker)
        if on:
            state = _ai_state(state, add_ai([entry], asker=asker, config=config))
    found = entry[1]
    if found is None:
        found = {"구성": "직접 입력", "종류": kind, "자리": "직접 입력", "원문": text.strip(), "본문": body, "앞 번호": prefix,
                 "상태": "규정에 맞음", "사유": [], "규정 꼴": KINDS[kind], "후보": [], "추천 없음": None, "참고 예문": [],
                 "버린 AI 후보": [], "AI": None}
    found["AI"] = state
    found["번호"] = "s1"
    return found


def suggest_manuscript(path: Path | str, *, use_llm: bool = False, asker=None, config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """원고(hwp/hwpx) → 구성별 추천 카드와 요약. use_llm: AI 후보도 묻는다(설정·승인·허용 목록이 있을 때만 실제 호출)."""
    document = load_document(path)
    sentences = collect(document)
    extra = verbs_in(document)
    verdicts = [check(s.kind, s.body, extra)[0] for s in sentences]
    pools: dict[str, list[tuple[str, str]]] = {}
    for s, ok in zip(sentences, verdicts):
        if ok is True:
            pools.setdefault(s.kind, []).append((s.body, s.where))
    entries = [[s, card(s, extra=extra, pool=pools.get(s.kind), config=config), ok] for s, ok in zip(sentences, verdicts)]
    llm = {"요청": use_llm, "상태": "AI 미사용 — 요청하지 않음", "물은 문장 수": 0, "호출": 0}
    if use_llm:
        on, state = llm_ready(asker)
        if on:
            stats = add_ai(entries, extra=extra, asker=asker, config=config)
            state = _ai_state(state, stats)
            llm.update({"물은 문장 수": stats["물은 문장 수"], "호출": stats["호출"]})
        llm["상태"] = state
    cards = []
    for _, found, _ in entries:
        if found is not None:
            found["번호"] = f"s{len(cards) + 1}"
            cards.append(found)
    parts: list[dict] = []
    for found in cards:
        if not parts or parts[-1]["구성"] != found["구성"]:
            parts.append({"구성": found["구성"], "문장": []})
        parts[-1]["문장"].append(found)
    count = lambda status: sum(1 for c in cards if c["상태"] == status)   # noqa: E731
    unknown = sum(1 for ok in verdicts if ok is None)
    notes = []
    if not sentences:
        notes.append("추천 대상 문장을 찾지 못했습니다(개요·차례·본문 구조를 읽지 못함). 원고 양식을 확인하세요.")
    if document.format == "hwp":
        notes.append("hwp 원고는 문단 스타일이 없어 수행 순서 네모 번호를 첫 글자로 찾습니다. hwpx를 권장합니다.")
    if unknown:
        notes.append(f"끝 낱말이 행동명사 목록에 없어 판정하지 못한 문장 {unknown}개는 '확인 필요'로 두고 추천하지 않았습니다.")
    return {
        "원고": Path(path).name, "형식": document.format,
        "요약": {"검사한 문장": len(sentences), "규칙 위반": count("규칙 위반"), "확인 필요": count("확인 필요"),
               "표현 다듬기": count("표현 다듬기"), "표현 확인(AI)": count(AI_STATUS),
               "추천 있음": sum(1 for c in cards if c["후보"]), "추천 없음": sum(1 for c in cards if not c["후보"]),
               "종류별 검사 수": {kind: n for kind in KINDS if (n := sum(1 for s in sentences if s.kind == kind))}},
        "구성": parts, "AI": llm, "알림": notes, "가정": ASSUMPTIONS,
    }
