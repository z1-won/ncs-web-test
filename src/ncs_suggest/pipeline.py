"""원고 문장 추천(REQ-02-004) — 원고 전체(구성별·문장별 카드) 또는 문장 하나(종류 지정)에 AI 판정과 정정 후보를 낸다.

단계: 원고에서 종류별 문장 모으기(extract.collect) → 모은 문장(원고 한 건에 config.llm_max_sentences개까지)을 종류별로 번호 붙인
원고 블록 하나 + 볼 종류 전부를 요청 블록으로 Claude에 한 번에 묻기(ask_all — 출력이 잘리면 종류 묶음을 반으로, 종류 하나면 그 종류의
문장 범위를 반으로 나눠 다시, 원고 블록은 캐시 읽기) → 받은 후보 검증·근거 문장 붙이기·순위(llm_suggest.parse·screen) → 카드와 참고 예문.
원고 블록의 문장 아래에는 자리와 참고 문장(corpus — 기존 학습모듈·공공저작물)을 붙인다(REQ-02-004). 후보문장표는 candidate_table.
카드 하나 = LLM이 고칠 문장이라고 본 문장 하나:
  {'번호','구성','종류','자리','원문','본문','앞 번호','문맥': {'앞','뒤'},'상태'(LLM 사유 유형),'사유','규정 꼴',
   '후보': [{'순위','문장','출처'('AI 생성'),'근거','근거 문장': {'문장','출처','자리','유사도'}|None,'모델'}] (최대 5),
   '추천 없음': 이유|None, '참고 예문': [...], '버린 AI 후보': [...], 'AI': 상태}
근거 문장은 참고 문장 묶음에서 후보와 가장 비슷한 문장이고, 근거 문장이 있는 후보가 앞 순위다. 묶음이 없으면 모두 None(알림에 적는다).
후보가 하나도 남지 않으면 '추천 없음(사람이 고쳐야 함)'. LLM을 부르지 못하면 규칙으로 대신 판정하지 않고 카드 없이 이유만 낸다.
원고 본문은 고치지 않는다. 채택은 집필자가 화면에서 한다.
"""

from __future__ import annotations

import time
from pathlib import Path

from ncs_core.documents import load_document
from ncs_llmreview import claude

from .config import DEFAULT_CONFIG, KINDS, LLM_TASK, NO_FINDING, NO_SUGGESTION, REASONS, UNDECIDED, SuggestConfig
from .corpus import Corpus, load as load_corpus, state as corpus_state
from .examples import similar
from .extract import Sentence, collect, split_prefix, verbs_in
from .llm_suggest import build_request, build_system, document_text, out_schema, parse

SETUP_ERRORS = ("ANTHROPIC_API_KEY", "LLM_ALLOW_UPLOAD", "anthropic 패키지", "모델 이름")   # 끝까지 같은 오류 — 나눠 부르지 않는다

ASSUMPTIONS = {
    "역할": "고칠 문장과 정정 후보는 AI가 냅니다. 종결·표현만 고치며 직무 내용을 새로 만들거나 교육 내용의 적절성을 판정하지 않습니다. 채택은 집필자가 합니다.",
    "출처 표시": "후보는 모두 'AI 생성'입니다(AI 문장은 집필자 서약서 고지 대상일 수 있음). 참고 예문은 같은 원고에서 AI가 지적하지 않은 같은 종류 문장입니다.",
    "문맥": "모은 문장을 종류별로 원고 순서대로 한 번에 AI에 보내 앞뒤 문장의 흐름을 보게 하고, 문장마다 자리를 함께 적습니다.",
    "근거 문장": "참고 문장 묶음(기존 학습모듈·공공저작물에서 규정 꼴을 지킨 문장)에서 비슷한 문장을 AI에 표현 참고로 보내고, 후보마다 가장 비슷한 문장을 "
              "근거 문장(출처·자리·유사도)으로 붙입니다. 근거 문장이 있는 후보가 앞 순위입니다. 표현의 근거이며 직무 내용이 맞다는 보증이 아닙니다.",
    "검사 범위": "학습모듈의 목표·학습 목표 · 차례 학습명·학습 내용명 · 수행 내용 제목·수행 순서 네모 번호 줄 · 교수 방법·학습 방법 · 평가 항목",
    "검증": "AI 후보는 규정 꼴(행동명사 목록 + '~화' + 같은 원고에서 'W한다'로 쓰인 낱말)·원문에 없던 수치·영문·상호·원문 유사도로 다시 걸러 "
            "통과한 것만 후보로 씁니다. 규정 꼴에 맞는 문장을 '종결형 위반'이라 한 지적은 사유를 '기타 표현'으로 바꿉니다.",
}


DIRECT = "직접 입력"      # 문장 직접 입력의 구성·자리 이름 — 자리를 적지 않는다


def llm_ready(generate=None) -> tuple[bool, str]:
    """AI를 부를 수 있는가 → (가능, 상태 문구). 없으면 'AI 미설정 — 이유'(claude.why_not)."""
    if generate is not None:
        return True, "AI 사용(주입된 응답)"
    cfg = claude.settings()
    problem = claude.why_not(cfg)
    if problem:
        return False, f"AI 미설정 — {problem}"
    return True, f"AI 사용({cfg['model']})"


def _card(sentence: Sentence, info: dict, model: str) -> dict:
    return {"구성": sentence.part, "종류": sentence.kind, "자리": sentence.where, "원문": sentence.text, "본문": sentence.body,
            "앞 번호": sentence.prefix, "문맥": {"앞": sentence.before, "뒤": sentence.after}, "상태": info["kind"], "사유": [info["reason"]] if info["reason"] else [],
            "규정 꼴": KINDS[sentence.kind], "후보": info["후보"],
            "추천 없음": None if info["후보"] else f"{NO_SUGGESTION} — AI가 고칠 문장으로 보았으나 검증을 통과한 정정 후보가 없음",
            "참고 예문": [], "버린 AI 후보": info["버린"], "AI": f"AI 사용({model})"}


def _split(group: list[tuple[str, list[int]]]) -> list[list[tuple[str, list[int]]]] | None:
    """잘린 요청 나누기 — 종류가 여럿이면 종류 묶음을 반으로, 하나면 그 종류의 문장 범위를 반으로. 더 못 나누면 None."""
    if len(group) > 1:
        half = len(group) // 2
        return [group[:half], group[half:]]
    kind, numbers = group[0]
    if len(numbers) > 1:
        half = len(numbers) // 2
        return [[(kind, numbers[:half])], [(kind, numbers[half:])]]
    return None


def _add_usage(usage: dict, answer: dict, model: str) -> None:
    if answer.get("cached"):
        return
    u = answer.get("usage") or {}
    usage["new_calls"] += 1
    for key in ("input", "output", "cache_read"):
        usage[key] += u.get(key, 0)
    usage["cost_usd"] += claude.cost(model, u) or 0.0


def ask_all(sentences: list[Sentence], *, extra: frozenset[str] = frozenset(), corpus: Corpus | None = None, generate=None,
            config: SuggestConfig = DEFAULT_CONFIG) -> tuple[list[dict | None], list[bool], dict]:
    """문장들 → (문장마다 카드|None, 문장마다 AI에 물었는가, 통계 {'호출','물은 문장 수','실패','모델','사유를 바꾼 지적','usage'}).

    원고 한 건에서 묻는 문장은 config.llm_max_sentences개까지(종류가 처음 나온 순서로 종류마다 앞에서부터).
    물을 문장 전부를 원고 블록 하나로 번호 붙이고(같은 종류끼리 이어진 번호), 볼 종류 전부를 한 번에 묻는다.
    corpus: 참고 문장 묶음 — 문장 아래에 표현 참고로 붙이고, 후보의 근거 문장을 찾는다(없으면 corpus.load()).
    usage는 ncs_llmreview.service.review_manuscript와 같은 키(calls, new_calls, input, output, cache_read, cost_usd, dropped, seconds).
    """
    generate = generate or claude.generate_json
    corpus = corpus if corpus is not None else load_corpus()
    started = time.perf_counter()
    cards: list[dict | None] = [None] * len(sentences)
    asked = [False] * len(sentences)
    usage = {"calls": 0, "new_calls": 0, "input": 0, "output": 0, "cache_read": 0, "cost_usd": 0.0, "dropped": 0}
    stats = {"호출": 0, "물은 문장 수": 0, "실패": [], "모델": "", "사유를 바꾼 지적": [], "usage": usage}
    groups: dict[str, list[int]] = {}
    for at, sentence in enumerate(sentences):
        groups.setdefault(sentence.kind, []).append(at)
    budget = config.llm_max_sentences
    numbered: dict[int, tuple[str, str]] = {}
    where: dict[int, int] = {}                 # 문장 번호 → sentences 순번
    request: list[tuple[str, list[int]]] = []
    extras: dict[int, dict] = {}               # 문장 번호 → 문장 아래에 붙일 자리·참고 문장
    for kind, members in groups.items():
        chunk = members[:max(budget, 0)]
        if not chunk:
            break
        budget -= len(chunk)
        numbers = []
        for at in chunk:
            no = len(numbered) + 1
            numbered[no] = (kind, sentences[at].body)
            where[no] = at
            numbers.append(no)
            # 문장 아래에 붙일 줄(REQ-02-004): 자리, 참고 문장 묶음에서 고른 기존 학습모듈 문장. 앞뒤 문장은 블록 안의 윗줄·아랫줄이다
            found = corpus.find(kind, sentences[at].body, limit=config.max_references, minimum=config.reference_min)
            place = "" if sentences[at].part == DIRECT else sentences[at].where
            if place or found:
                extras[no] = {"자리": place, "참고 문장": [ref["문장"] for ref in found]}
        request.append((kind, numbers))
    if not request:
        return cards, asked, stats
    system, document, schema = build_system(), document_text(numbered, extras), out_schema()
    queue = [request]
    while queue:
        group = queue.pop(0)
        usage["calls"] += 1
        try:
            reply = generate(system, document, build_request(group), task=LLM_TASK, tasks=None, out_schema=schema)
        except claude.ClaudeError as error:
            parts = _split(group) if "max_tokens" in str(error) else None
            if parts:
                queue[:0] = parts                   # 잘리면 나눠 다시(원고 블록은 캐시 읽기)
                continue
            stats["실패"].append(str(error))
            if any(s in str(error) for s in SETUP_ERRORS):
                break                               # 설정 문제는 끝까지 같은 오류 — 남은 묶음도 묻지 못함
            continue
        model = str(reply.get("model") or "")
        _add_usage(usage, reply, model)
        mine = {no: numbered[no] for _, numbers in group for no in numbers}
        flagged, relabeled, dropped = parse(reply.get("data") or {}, mine, model, extra=extra, corpus=corpus, config=config)
        stats["호출"] += 1
        stats["물은 문장 수"] += len(mine)
        stats["모델"] = model
        stats["사유를 바꾼 지적"] += relabeled
        usage["dropped"] += dropped
        for no in mine:
            asked[where[no]] = True
        for no, info in flagged.items():
            cards[where[no]] = _card(sentences[where[no]], info, model)
    usage["cost_usd"] = round(usage["cost_usd"], 4)
    usage["seconds"] = round(time.perf_counter() - started, 1)
    return cards, asked, stats


def _ai_state(state: str, stats: dict) -> str:
    usage = stats["usage"]
    text = (f"AI 사용({stats['모델']})" if stats["모델"] else state) + f" · 호출 {usage['calls']}번(새 호출 {usage['new_calls']}번), 문장 {stats['물은 문장 수']}개"
    if stats["실패"]:
        text += f", 실패 {len(stats['실패'])}번({stats['실패'][0]})"
    text += f" · 입력 {usage['input']:,}(캐시 읽기 {usage['cache_read']:,})·출력 {usage['output']:,}토큰 · 약 ${usage['cost_usd']}"
    return text


def suggest_sentence(text: str, kind: str, *, generate=None, corpus: Corpus | None = None, config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """문장 하나 + 종류 → 카드. AI가 지적하지 않으면 '상태': '지적 없음', AI를 부르지 못하면 '판단불가'와 이유(빈 후보).
    참고 문장 묶음이 있으면 후보에 근거 문장을 붙인다."""
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 문장 종류: {kind} (가능: {', '.join(KINDS)})")
    if not (text or "").strip():
        raise ValueError("추천받을 문장을 넣으세요")
    prefix, body = split_prefix(text)
    sentence = Sentence(kind, DIRECT, DIRECT, text.strip(), prefix, body)
    corpus = corpus if corpus is not None else load_corpus()
    on, state = llm_ready(generate)
    found = None
    status, reasons = UNDECIDED, [state]
    if on:
        cards, _, stats = ask_all([sentence], corpus=corpus, generate=generate, config=config)
        found, state = cards[0], _ai_state(state, stats)
        status, reasons = (UNDECIDED, [f"AI 호출 실패: {stats['실패'][0]}"]) if stats["실패"] else (NO_FINDING, [])
    if found is None:
        found = {"구성": "직접 입력", "종류": kind, "자리": "직접 입력", "원문": text.strip(), "본문": body, "앞 번호": prefix,
                 "문맥": {"앞": "", "뒤": ""}, "상태": status, "사유": reasons, "규정 꼴": KINDS[kind], "후보": [], "추천 없음": None,
                 "참고 예문": [], "버린 AI 후보": []}
    found["AI"] = state
    found["참고 문장"] = corpus_state(corpus)
    found["번호"] = "s1"
    return found


def suggest_manuscript(path: Path | str, *, generate=None, corpus: Corpus | None = None, config: SuggestConfig = DEFAULT_CONFIG) -> dict:
    """원고(hwp/hwpx) → 구성별 추천 카드와 요약. AI(Claude)는 ANTHROPIC_API_KEY·반출 승인(LLM_ALLOW_UPLOAD=1)이 있으면 자동으로 부른다.
    generate: 테스트용 가짜 Claude(system, document, request, *, task, tasks, out_schema) -> {'data','usage','cached','model'}.
    corpus: 참고 문장 묶음(없으면 corpus.load()로 기준정보 폴더의 파일을 읽는다)."""
    corpus = corpus if corpus is not None else load_corpus()
    document = load_document(path)
    sentences = collect(document)
    extra = verbs_in(document)
    on, state = llm_ready(generate)
    llm = {"상태": state, "물은 문장 수": 0, "호출": 0, "실패": 0, "사유를 바꾼 지적": [], "usage": None}
    cards: list[dict | None] = [None] * len(sentences)
    asked = [False] * len(sentences)
    if on and sentences:
        cards, asked, stats = ask_all(sentences, extra=extra, corpus=corpus, generate=generate, config=config)
        llm.update({"상태": _ai_state(state, stats), "물은 문장 수": stats["물은 문장 수"], "호출": stats["호출"],
                    "실패": len(stats["실패"]), "사유를 바꾼 지적": stats["사유를 바꾼 지적"], "usage": stats["usage"]})
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
    if not len(corpus):
        notes.append("참고 문장 묶음이 없어 후보에 근거 문장(기존 학습모듈·공공저작물)을 붙이지 못했습니다. 후보는 AI가 원문을 고쳐 쓴 문장입니다.")
    candidates = [item for card in shown for item in card["후보"]]
    return {
        "원고": Path(path).name, "형식": document.format,
        "요약": {"검사한 문장": len(sentences), "AI에 보낸 문장": llm["물은 문장 수"], "고칠 문장": len(shown),
               "사유별": {reason: n for reason in REASONS if (n := sum(1 for c in shown if c["상태"] == reason))},
               "추천 있음": sum(1 for c in shown if c["후보"]), "추천 없음": sum(1 for c in shown if not c["후보"]),
               "버린 AI 후보": sum(len(c["버린 AI 후보"]) for c in shown),
               "후보": len(candidates), "근거 문장 있는 후보": sum(1 for item in candidates if item.get("근거 문장")),
               "종류별 검사 수": {kind: n for kind in KINDS if (n := sum(1 for s in sentences if s.kind == kind))}},
        "구성": parts, "AI": llm, "참고 문장": {"상태": corpus_state(corpus), "문장 수": len(corpus), "종류별": corpus.counts()},
        "알림": notes, "가정": ASSUMPTIONS,
    }


def basis_text(basis: dict | None) -> str:
    """근거 문장 한 칸 글 — '「문장」 (출처, 자리, 유사도 0.82)'. 없으면 빈 글."""
    if not basis:
        return ""
    place = ", ".join(part for part in (basis.get("출처"), basis.get("자리")) if part)
    return f"「{basis['문장']}」 ({place + ', ' if place else ''}유사도 {basis['유사도']})"


def table_columns(config: SuggestConfig = DEFAULT_CONFIG) -> list[str]:
    """후보문장표의 열 이름(순서대로) — 행이 없어도 머리글을 쓸 수 있게 따로 둔다."""
    ranked = [f"{name} {rank}순위" for rank in range(1, config.max_candidates + 1) for name in ("정정 후보", "근거 문장")]
    return ["번호", "원고", "구성", "자리", "종류", "규정 꼴", "변경 필요 원본 문장", "사유 유형", "사유", *ranked, "비고"]


def candidate_table(result: dict, *, config: SuggestConfig = DEFAULT_CONFIG) -> list[dict]:
    """결과(suggest_manuscript) 또는 카드 하나(suggest_sentence) → 문장 정정 필요 후보문장표의 행(카드마다 한 행).

    요구사항 산출물 '(변경 필요 원본 문장) ⇄ (문장 정정 후보군) 5순위까지': 원본 문장 옆에 후보 1~5순위와 후보별 근거 문장을 둔다.
    후보에는 원문의 앞 번호·글머리를 다시 붙여 원고에 그대로 옮길 수 있게 한다.
    """
    whole = isinstance(result.get("구성"), list)       # 원고 전체 결과인가(아니면 카드 하나)
    cards = [card for part in result["구성"] for card in part["문장"]] if whole else [result]
    rows = []
    for card in cards:
        row = {"번호": card.get("번호", ""), "원고": result.get("원고", "") if whole else "", "구성": card["구성"],
               "자리": card["자리"], "종류": card["종류"], "규정 꼴": card["규정 꼴"], "변경 필요 원본 문장": card["원문"],
               "사유 유형": card["상태"], "사유": " / ".join(card["사유"])}
        prefix = f"{card['앞 번호']} " if card.get("앞 번호") else ""
        for rank in range(1, config.max_candidates + 1):
            item = next((c for c in card["후보"] if c["순위"] == rank), None)
            row[f"정정 후보 {rank}순위"] = prefix + item["문장"] if item else ""
            row[f"근거 문장 {rank}순위"] = basis_text(item.get("근거 문장")) if item else ""
        row["비고"] = card.get("추천 없음") or ""
        rows.append(row)
    return rows
