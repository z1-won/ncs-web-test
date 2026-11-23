"""LLM 판정 묻기 — 의견들이 가리키는 원고 문단을 원고 블록 하나로, 의견 목록을 요청 블록으로 Claude에 한 번에 묻는다.

호출은 ncs_llmreview.claude.generate_json(공식 anthropic SDK, 프롬프트 캐시, 구조화 출력, 디스크 캐시, 작업 이름 opinion_reflection).
  system      prompts/00_의견반영.md의 절(원고마다 같음)
  원고 블록    [원고] 최종 원고 문단:   [1] (학습 1 필요 지식) 글 …   — 모든 의견이 고른 문단을 번호 붙여 한 번씩(최대 llm_lines개)
                    반영 전 원고 문단: [이전 1] …                   — 반영 전 원고가 있으면 같은 방법으로(캐시됨)
  요청 블록    [검토 의견] 1. (1차 · 학습 1 · 필요 지식 · 4쪽) [볼 문단: 3-7, 12 | 반영 전: 이전 2-4] 의견 글 …
  받는 것      {"opinions": [{"no", "type", "verdict", "evidence": [볼 문단 번호], "already_before", "reason", "suggestion",
                              "old_terms", "new_terms"}]}  (out_schema)
의견 전부를 한 번에 묻고, 출력이 max_tokens에서 잘리면 의견을 반으로 나눠 다시 부른다(원고 블록은 같아서 캐시 읽기).
번호 검증은 여기서 한다(묻지 않은 의견 번호·같은 번호의 두 번째 답은 버림, 근거는 그 의견의 볼 문단 번호만).
판정 정책(근거 검증·용어 변경·형식·그림·자리 없는 의견)은 judge.py가 적용한다. 원고 전문은 보내지 않는다.
generate: 테스트용 대역(system, document, request, *, task, tasks, out_schema) -> {'data','usage','cached','model'}.
"""

from __future__ import annotations

import time
from pathlib import Path

from ncs_llmreview import claude
from ncs_llmreview.prompts import SECTION, fill

from .config import DEFAULT_CONFIG, KINDS, LLM_CHECK, LLM_MISSING, LLM_REFLECTED, LLM_TASK, NO_PLACE, OpinionConfig
from .regions import Manuscript, locate, pick_paragraphs
from .sheet import Opinion

TASK = LLM_TASK
LLM_VERDICTS = (LLM_REFLECTED, LLM_MISSING, LLM_CHECK)
PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "00_의견반영.md"
SETUP_ERRORS = ("ANTHROPIC_API_KEY", "LLM_ALLOW_UPLOAD", "anthropic 패키지", "모델 이름")   # 끝까지 같은 오류 — 나눠 부르지 않는다


def sections() -> dict[str, str]:
    """prompts/00_의견반영.md의 '## [이름]' 아래 코드 블록들(ncs_llmreview.prompts와 같은 md 규칙)."""
    return {m.group(1): m.group(2) for m in SECTION.finditer(PROMPT_FILE.read_text(encoding="utf-8"))}


def build_system() -> str:
    own = sections()
    return "\n\n".join(own[name].strip() for name in ("역할", "원고 입력", "유형", "판정", "수정 문장·용어·이유", "규칙"))


def out_schema() -> dict:
    """구조화 출력 스키마 — object마다 모든 속성 required, 선택 값은 빈 문자열·빈 목록으로 받는다."""
    terms = {"type": "array", "items": {"type": "string"}}
    item = {"type": "object",
            "properties": {"no": {"type": "integer"}, "type": {"type": "string", "enum": list(KINDS)},
                           "verdict": {"type": "string", "enum": list(LLM_VERDICTS)},
                           "evidence": {"type": "array", "items": {"type": "integer"}}, "already_before": {"type": "boolean"},
                           "reason": {"type": "string"}, "suggestion": {"type": "string"}, "old_terms": terms, "new_terms": terms},
            "required": ["no", "type", "verdict", "evidence", "already_before", "reason", "suggestion", "old_terms", "new_terms"],
            "additionalProperties": False}
    return {"type": "object", "properties": {"opinions": {"type": "array", "items": item}}, "required": ["opinions"],
            "additionalProperties": False}


def llm_status(generate=None) -> tuple[bool, str]:
    """LLM을 부를 수 있는가 → (가능, 상태 문구). 없으면 'LLM 미설정 — 이유'(claude.why_not)."""
    if generate is not None:
        return True, "사용(주입된 응답)"
    cfg = claude.settings()
    problem = claude.why_not(cfg)
    if problem:
        return False, f"LLM 미설정 — {problem}"
    return True, f"사용({cfg['model']})"


def _merge(lists: list[list[int]], limit: int) -> list[int]:
    """의견마다 고른 문단 목록을 돌아가며 하나씩 합친다(앞 의견이 상한을 다 쓰지 않게) → 문서 순서."""
    chosen: list[int] = []
    for depth in range(max((len(l) for l in lists), default=0)):
        for picked in lists:
            if depth < len(picked) and picked[depth] not in chosen and len(chosen) < limit:
                chosen.append(picked[depth])
    return sorted(chosen)


def _picks(opinion: Opinion, manuscript: Manuscript, config: OpinionConfig) -> list[int]:
    region, label, _, caption = locate(opinion, manuscript, config)
    if label == NO_PLACE:
        return []
    picked = pick_paragraphs(opinion.text, manuscript, region, caption=caption, config=config)
    # 겹침이 큰 문단이 먼저 들어가도록, 캡션 → 나머지 순으로 둔다(_merge가 앞에서부터 자른다)
    return ([caption] if caption in picked else []) + [i for i in picked if i != caption]


def _where(opinion: Opinion) -> str:
    return " · ".join(filter(None, [opinion.round, opinion.group, opinion.part or "", f"{opinion.page}쪽" if opinion.page else ""]))


def _ranges(numbers: list[int], prefix: str = "") -> str:
    """[3, 4, 5, 9] → '3-5, 9' (prefix='이전 '이면 '이전 3-5, 이전 9')."""
    out, run = [], []
    for n in sorted(set(numbers)):
        if run and n == run[-1] + 1:
            run.append(n)
            continue
        if run:
            out.append(f"{prefix}{run[0]}" + (f"-{run[-1]}" if len(run) > 1 else ""))
        run = [n]
    if run:
        out.append(f"{prefix}{run[0]}" + (f"-{run[-1]}" if len(run) > 1 else ""))
    return ", ".join(out)


def build_prompt(opinions: list[Opinion], final: Manuscript, previous: Manuscript | None,
                 config: OpinionConfig = DEFAULT_CONFIG) -> dict:
    """의견 전부의 질문 → {'document'(원고 블록), 'lines'(의견 번호(1부터) → 요청 줄), '문단'(원고 블록 번호 → 최종 원고 문단 순번),
    '볼 문단'(의견 번호 → 그 의견의 원고 블록 번호들), '반영 전 볼 문단'(의견 번호 → 반영 전 블록 번호들)}."""
    picks = [[i for i in _picks(o, final, config)] for o in opinions]
    chosen = _merge(picks, config.llm_lines)
    number = {index: no for no, index in enumerate(chosen, 1)}
    before_picks = [_picks(o, previous, config) for o in opinions] if previous is not None else [[] for _ in opinions]
    before = _merge(before_picks, config.llm_lines) if previous is not None else []
    before_number = {index: no for no, index in enumerate(before, 1)}
    parts = ["[원고]", "최종 원고 문단:"]
    parts += [f"[{no}] ({final.paras[i].where}) {final.paras[i].text[: config.llm_para_chars]}" for no, i in enumerate(chosen, 1)]
    if not chosen:
        parts.append("(없음 — 가리키는 자리가 있는 의견이 없음)")
    if previous is not None:
        parts.append("\n반영 전 원고 문단:")
        parts += [f"[이전 {no}] ({previous.paras[i].where}) {previous.paras[i].text[: config.llm_para_chars]}" for no, i in enumerate(before, 1)]
        if not before:
            parts.append("(같은 범위를 반영 전 원고에서 찾지 못함)")
    looks, before_looks, lines = {}, {}, {}
    for no, (o, mine, old) in enumerate(zip(opinions, picks, before_picks), 1):
        looks[no] = [number[i] for i in mine if i in number]
        before_looks[no] = [before_number[i] for i in old if i in before_number]
        if looks[no]:
            look = _ranges(looks[no])
        else:
            look = "없음 — 가리키는 자리가 없는 의견이므로 유형만 분류하고 verdict는 \"확인 필요\""
        if previous is not None:
            look += " | 반영 전: " + (_ranges(before_looks[no], "이전 ") if before_looks[no] else "찾지 못함")
        lines[no] = f"{no}. ({_where(o)}) [볼 문단: {look}] {o.text}"
    return {"document": "\n".join(parts), "lines": lines, "문단": {no: i for i, no in number.items()},
            "볼 문단": looks, "반영 전 볼 문단": before_looks}


def build_request(lines: dict[int, str], group: list[int]) -> str:
    head = fill(sections()["요청 머리"], {"의견_번호": ", ".join(map(str, group))})
    return "\n".join([head, *(lines[no] for no in group)])


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _terms(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value or [] if str(v).strip()] if isinstance(value, list) else []


def parse_answer(data: dict, looks: dict[int, list[int]], paragraph_of: dict[int, int]) -> tuple[dict[int, dict], int]:
    """모델 JSON → ({의견 번호: 답}, 버린 답 수). looks: 이번에 물은 의견 번호 → 그 의견의 볼 문단 번호들,
    paragraph_of: 원고 블록 번호 → 최종 원고 문단 순번. 묻지 않은 의견 번호·같은 번호의 두 번째 답은 버리고,
    근거는 그 의견의 볼 문단 번호만 남긴다.

    답: {'유형'(KINDS 밖이면 ''), '판정'(LLM_VERDICTS 밖이면 ''), '근거'(최종 원고 문단 순번 목록), '버린 근거 번호',
         '반영 전에도 있음', '이유', '수정 문장', '옛 용어', '새 용어'}
    """
    out: dict[int, dict] = {}
    dropped = 0
    items = (data or {}).get("opinions")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        no = _int(item.get("no"))
        if no is None or no not in looks or no in out:
            dropped += 1
            continue
        cited = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        numbers = [_int(c) for c in cited]
        valid = [paragraph_of[c] for c in dict.fromkeys(numbers) if c is not None and c in looks[no] and c in paragraph_of]
        kind, verdict = str(item.get("type") or "").strip(), str(item.get("verdict") or "").strip()
        out[no] = {
            "유형": kind if kind in KINDS else "", "판정": verdict if verdict in LLM_VERDICTS else "",
            "근거": valid, "버린 근거 번호": len(set(numbers)) - len(valid),
            "반영 전에도 있음": item.get("already_before") is True,
            "이유": str(item.get("reason") or "").strip(), "수정 문장": str(item.get("suggestion") or "").strip(),
            "옛 용어": _terms(item.get("old_terms")), "새 용어": _terms(item.get("new_terms")),
        }
    return out, dropped


def new_usage() -> dict:
    """사용량 — ncs_llmreview.service.review_manuscript의 'usage'와 같은 키."""
    return {"calls": 0, "new_calls": 0, "input": 0, "output": 0, "cache_read": 0, "cost_usd": 0.0, "dropped": 0}


def add_usage(usage: dict, answer: dict, model: str) -> None:
    if answer.get("cached"):
        return
    u = answer.get("usage") or {}
    usage["new_calls"] += 1
    for key in ("input", "output", "cache_read"):
        usage[key] += u.get(key, 0)
    usage["cost_usd"] += claude.cost(model, u) or 0.0


def ask_all(opinions: list[tuple[Opinion, str]], final: Manuscript, previous: Manuscript | None, *, generate=None,
            config: OpinionConfig = DEFAULT_CONFIG) -> tuple[list[dict | None], dict]:
    """(의견, 찾은 범위 이름) 목록 → (의견마다 답 | {'오류': 이유} | None(답하지 않음), 통계).

    통계: {'호출', '물은 의견', '실패', '모델', 'usage'} — usage는 ncs_llmreview와 같은 키(+ seconds).
    의견 전부를 한 번에 묻고, 출력이 잘리면 반으로 나눠 다시 묻는다. 답에는 '모델', '보낸 문단 수', '반영 전 문단 수'를 붙인다.
    """
    generate = generate or claude.generate_json
    started = time.perf_counter()
    answers: list[dict | None] = [None] * len(opinions)
    usage = new_usage()
    stats = {"호출": 0, "물은 의견": 0, "실패": 0, "모델": "", "usage": usage}
    if not opinions:
        return answers, stats
    prompt = build_prompt([o for o, _ in opinions], final, previous, config)
    system = build_system()
    schema = out_schema()
    queue = [list(range(1, len(opinions) + 1))]
    while queue:
        group = queue.pop(0)
        usage["calls"] += 1
        try:
            reply = generate(system, prompt["document"], build_request(prompt["lines"], group), task=TASK, tasks=None, out_schema=schema)
        except claude.ClaudeError as error:
            if "max_tokens" in str(error) and len(group) > 1:
                half = len(group) // 2
                queue[:0] = [group[:half], group[half:]]       # 잘리면 반으로 나눠 다시(원고 블록은 캐시 읽기)
                continue
            stats["실패"] += 1
            for no in group:
                answers[no - 1] = {"오류": str(error)}
            if any(s in str(error) for s in SETUP_ERRORS):  # 설정 문제는 끝까지 같은 오류 — 남은 의견도 같은 이유
                for rest in queue:
                    for no in rest:
                        answers[no - 1] = {"오류": str(error)}
                stats["실패"] += len(queue)
                break
            continue
        model = str(reply.get("model") or "")
        add_usage(usage, reply, model)
        stats["호출"] += 1
        stats["물은 의견"] += len(group)
        stats["모델"] = model
        parsed, dropped = parse_answer(reply.get("data") or {}, {no: prompt["볼 문단"][no] for no in group}, prompt["문단"])
        usage["dropped"] += dropped
        for no, answer in parsed.items():
            answer.update({"모델": model, "보낸 문단 수": len(prompt["볼 문단"][no]), "반영 전 문단 수": len(prompt["반영 전 볼 문단"][no])})
            answers[no - 1] = answer
    usage["cost_usd"] = round(usage["cost_usd"], 4)
    usage["seconds"] = round(time.perf_counter() - started, 1)
    return answers, stats
