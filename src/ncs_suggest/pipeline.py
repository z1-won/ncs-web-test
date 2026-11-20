"""원고 문장 추천(REQ-02-004) — 원고 전체(구성별·문장별 카드) 또는 문장 하나(종류 지정)에 AI 판정과 정정 후보를 낸다.

단계: 원고에서 종류별 문장 모으기(extract.collect) → 같은 종류끼리 config.llm_batch개씩 LLM에 묻기(llm_suggest.ask_lines,
원고 한 건에 config.llm_max_sentences개까지) → 받은 후보 검증·순위(llm_suggest.screen) → 카드와 참고 예문.
카드 하나 = LLM이 고칠 문장이라고 본 문장 하나:
  {'번호','구성','종류','자리','원문','본문','앞 번호','상태'(LLM 사유 유형),'사유','규정 꼴',
   '후보': [{'순위','문장','출처'('AI 생성'),'근거','모델'}] (최대 5), '추천 없음': 이유|None,
   '참고 예문': [...], '버린 AI 후보': [...], 'AI': 상태}
후보가 하나도 남지 않으면 '추천 없음(사람이 고쳐야 함)'. LLM을 부르지 못하면 규칙으로 대신 판정하지 않고 카드 없이 이유만 낸다.
원고 본문은 고치지 않는다. 채택은 집필자가 화면에서 한다.
"""

from __future__ import annotations

from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.llm import LlmError, settings, task_allowed

from .config import DEFAULT_CONFIG, KINDS, LLM_TASK, NO_FINDING, NO_SUGGESTION, REASONS, UNDECIDED, SuggestConfig
from .examples import similar
from .extract import Sentence, collect, split_prefix, verbs_in
from .llm_suggest import ask_lines

ASSUMPTIONS = {
    "역할": "고칠 문장과 정정 후보는 AI가 냅니다. 종결·표현만 고치며 직무 내용을 새로 만들거나 교육 내용의 적절성을 판정하지 않습니다. 채택은 집필자가 합니다.",
    "출처 표시": "후보는 모두 'AI 생성'입니다(AI 문장은 집필자 서약서 고지 대상일 수 있음). 참고 예문은 같은 원고에서 AI가 지적하지 않은 같은 종류 문장입니다.",
    "검사 범위": "학습모듈의 목표·학습 목표 · 차례 학습명·학습 내용명 · 수행 내용 제목·수행 순서 네모 번호 줄 · 교수 방법·학습 방법 · 평가 항목",
    "검증": "AI 후보는 규정 꼴(행동명사 목록 + '~화' + 같은 원고에서 'W한다'로 쓰인 낱말)·원문에 없던 수치·영문·상호·원문 유사도로 다시 걸러 "
            "통과한 것만 후보로 씁니다. 규정 꼴에 맞는 문장을 '종결형 위반'이라 한 지적은 사유를 '기타 표현'으로 바꿉니다.",
}


def llm_ready(asker=None) -> tuple[bool, str]:
    """AI를 부를 수 있는가 → (가능, 상태 문구). 없으면 'AI 미설정 — 이유'."""
    if asker is not None:
        return True, "AI 사용(주입된 응답)"
    if not task_allowed(LLM_TASK):
        return False, f"AI 미설정 — '{LLM_TASK}' 작업이 허용 목록(LLM_ALLOWED_TASKS)에서 빠져 있음"
    cfg = settings()
    if not cfg.ready:
        return False, f"AI 미설정 — {cfg.why_not}"
    return True, f"AI 사용({cfg.model})"


def _card(sentence: Sentence, info: dict, model: str) -> dict:
    return {"구성": sentence.part, "종류": sentence.kind, "자리": sentence.where, "원문": sentence.text, "본문": sentence.body,
            "앞 번호": sentence.prefix, "상태": info["kind"], "사유": [info["reason"]] if info["reason"] else [],
            "규정 꼴": KINDS[sentence.kind], "후보": info["후보"],
            "추천 없음": None if info["후보"] else f"{NO_SUGGESTION} — AI가 고칠 문장으로 보았으나 검증을 통과한 정정 후보가 없음",
            "참고 예문": [], "버린 AI 후보": info["버린"], "AI": f"AI 사용({model})"}


def ask_all(sentences: list[Sentence], *, extra: frozenset[str] = frozenset(), asker=None,
            config: SuggestConfig = DEFAULT_CONFIG) -> tuple[list[dict | None], list[bool], dict]:
    """문장들 → (문장마다 카드|None, 문장마다 AI에 물었는가, 통계 {'호출','물은 문장 수','실패','모델','버린 지적'}).

    같은 종류의 문장끼리 config.llm_batch개씩 묶어 묻는다. 원고 한 건에서 묻는 문장은 config.llm_max_sentences개까지.
    """
    cards: list[dict | None] = [None] * len(sentences)
    asked = [False] * len(sentences)
    stats = {"호출": 0, "물은 문장 수": 0, "실패": [], "모델": "", "사유를 바꾼 지적": []}
    groups: dict[str, list[int]] = {}
    for at, sentence in enumerate(sentences):
        groups.setdefault(sentence.kind, []).append(at)
    budget = config.llm_max_sentences
    for kind, members in groups.items():
        for start in range(0, len(members), config.llm_batch):
            chunk = members[start:start + config.llm_batch][:max(budget, 0)]
            if not chunk:
                break
            budget -= len(chunk)
            try:
                flagged, rejected, model = ask_lines(kind, [sentences[at].body for at in chunk], extra=extra, asker=asker, config=config)
            except LlmError as error:
                stats["실패"].append(str(error))
                continue
            stats["호출"] += 1
            stats["물은 문장 수"] += len(chunk)
            stats["모델"] = model
            stats["사유를 바꾼 지적"] += rejected
            for at in chunk:
                asked[at] = True
            for order, info in flagged.items():
                cards[chunk[order]] = _card(sentences[chunk[order]], info, model)
    return cards, asked, stats


def _ai_state(state: str, stats: dict) -> str:
    text = (f"AI 사용({stats['모델']})" if stats["모델"] else state) + f" · 호출 {stats['호출']}번, 문장 {stats['물은 문장 수']}개"
    if stats["실패"]:
        text += f", 실패 {len(stats['실패'])}번({stats['실패'][0]})"
    return text


def suggest_sentence(text: str, kind: str, *, asker=None, config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """문장 하나 + 종류 → 카드. AI가 지적하지 않으면 '상태': '지적 없음', AI를 부르지 못하면 '판단불가'와 이유(빈 후보)."""
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 문장 종류: {kind} (가능: {', '.join(KINDS)})")
    if not (text or "").strip():
        raise ValueError("추천받을 문장을 넣으세요")
    prefix, body = split_prefix(text)
    sentence = Sentence(kind, "직접 입력", "직접 입력", text.strip(), prefix, body)
    on, state = llm_ready(asker)
    found = None
    status, reasons = UNDECIDED, [state]
    if on:
        cards, _, stats = ask_all([sentence], asker=asker, config=config)
        found, state = cards[0], _ai_state(state, stats)
        status, reasons = (UNDECIDED, [f"AI 호출 실패: {stats['실패'][0]}"]) if stats["실패"] else (NO_FINDING, [])
    if found is None:
        found = {"구성": "직접 입력", "종류": kind, "자리": "직접 입력", "원문": text.strip(), "본문": body, "앞 번호": prefix,
                 "상태": status, "사유": reasons, "규정 꼴": KINDS[kind], "후보": [], "추천 없음": None, "참고 예문": [],
                 "버린 AI 후보": []}
    found["AI"] = state
    found["번호"] = "s1"
    return found


def suggest_manuscript(path: Path | str, *, asker=None, config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """원고(hwp/hwpx) → 구성별 추천 카드와 요약. AI는 설정·반출 승인·허용 목록이 있으면 자동으로 부른다."""
    document = load_document(path)
    sentences = collect(document)
    extra = verbs_in(document)
    on, state = llm_ready(asker)
    llm = {"상태": state, "물은 문장 수": 0, "호출": 0, "실패": 0, "사유를 바꾼 지적": []}
    cards: list[dict | None] = [None] * len(sentences)
    asked = [False] * len(sentences)
    if on and sentences:
        cards, asked, stats = ask_all(sentences, extra=extra, asker=asker, config=config)
        llm.update({"상태": _ai_state(state, stats), "물은 문장 수": stats["물은 문장 수"], "호출": stats["호출"],
                    "실패": len(stats["실패"]), "사유를 바꾼 지적": stats["사유를 바꾼 지적"]})
    pools: dict[str, list[tuple[str, str]]] = {}
    for sentence, found, was_asked in zip(sentences, cards, asked):
        if was_asked and found is None:      # AI가 지적하지 않은 같은 종류 문장 — 참고 예문 후보
            pools.setdefault(sentence.kind, []).append((sentence.body, sentence.where))
    shown = []
    for sentence, found in zip(sentences, cards):
        if found is not None:
            found["참고 예문"] = similar(sentence.body, pools.get(sentence.kind, []), config=config)
            found["번호"] = f"s{len(shown) + 1}"
            shown.append(found)
    parts: list[dict] = []
    for found in shown:
        if not parts or parts[-1]["구성"] != found["구성"]:
            parts.append({"구성": found["구성"], "문장": []})
        parts[-1]["문장"].append(found)
    notes = []
    if not sentences:
        notes.append("추천 대상 문장을 찾지 못했습니다(개요·차례·본문 구조를 읽지 못함). 원고 양식을 확인하세요.")
    if document.format == "hwp":
        notes.append("hwp 원고는 문단 스타일이 없어 수행 순서 네모 번호를 첫 글자로 찾습니다. hwpx를 권장합니다.")
    if not on:
        notes.append(f"{state} — 규칙으로 대신 판정하지 않으므로 고칠 문장을 찾지 않았습니다(판단불가).")
    elif (unasked := sum(1 for a in asked if not a)) and sentences:
        notes.append(f"AI에 묻지 못한 문장 {unasked}개(상한 {config.llm_max_sentences}개 또는 호출 실패)는 판단불가입니다.")
    return {
        "원고": Path(path).name, "형식": document.format,
        "요약": {"검사한 문장": len(sentences), "AI에 보낸 문장": llm["물은 문장 수"], "고칠 문장": len(shown),
               "사유별": {reason: n for reason in REASONS if (n := sum(1 for c in shown if c["상태"] == reason))},
               "추천 있음": sum(1 for c in shown if c["후보"]), "추천 없음": sum(1 for c in shown if not c["후보"]),
               "버린 AI 후보": sum(len(c["버린 AI 후보"]) for c in shown),
               "종류별 검사 수": {kind: n for kind in KINDS if (n := sum(1 for s in sentences if s.kind == kind))}},
        "구성": parts, "AI": llm, "알림": notes, "가정": ASSUMPTIONS,
    }
