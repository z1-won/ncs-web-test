"""LLM 판정 묻기 — 같은 범위를 가리키는 의견들과 그 범위에서 고른 원고 문단을 번호 붙여 보내고, 의견마다 유형·판정·근거를 받는다.

작업 이름 opinion_reflection(ncs_core.llm.ALLOWED_TASKS). 줄 번호로 지적 줄만 받는 line_findings와 달리 모든 의견의 답을 받아야 해서
ask_json을 직접 쓰고, 번호 검증을 여기서 한다(없는 의견 번호·없는 문단 번호는 버림, 의견마다 첫 답만).

  보내는 것  [원고 문단]          의견이 가리키는 범위에서 고른 최종 원고 문단 — [1] (학습 1 필요 지식) 글 …  (최대 llm_lines개)
            [반영 전 원고 문단]   반영 전 원고가 있으면 같은 범위에서 고른 문단 — [이전 1] …
            [검토 의견]          1. (1차 · 학습 1 필요 지식 · 4쪽) 의견 글 …  (최대 llm_batch개)
  받는 것    {"opinions": [{"no": 의견 번호, "type": 조치 불필요|용어 변경|형식|그림|내용, "verdict": 반영|미반영|확인 필요,
                            "evidence": [원고 문단 번호], "already_before": bool, "reason": 한 문장, "suggestion": 수정 문장 후보,
                            "old_terms": [옛 용어], "new_terms": [새 용어]}]}
판정 정책(근거 검증·용어 변경·형식·그림·자리 없는 의견)은 judge.py가 적용한다. 원고 전문은 보내지 않는다. 응답은 ncs_core.llm이 캐시한다.
"""

from __future__ import annotations

from ncs_core.llm import LlmError, ask_json, settings, task_allowed

from .config import DEFAULT_CONFIG, KINDS, LLM_CHECK, LLM_MISSING, LLM_REFLECTED, LLM_TASK, NO_PLACE, OpinionConfig
from .regions import Manuscript, locate, pick_paragraphs
from .sheet import Opinion

TASK = LLM_TASK
LLM_VERDICTS = (LLM_REFLECTED, LLM_MISSING, LLM_CHECK)

SYSTEM = """당신은 NCS 학습모듈 원고의 검수 보조자입니다. 검토의견서의 [검토 의견]마다 그 의견이 최종 원고에 반영되었는지 판단합니다.
[원고 문단]은 의견이 가리키는 범위에서 고른 최종 원고 문단이며 앞에 [번호]가 있습니다. [반영 전 원고 문단]이 있으면 의견을 받기 전 원고의 같은 범위입니다.
모든 의견에 대해 빠짐없이 하나씩 답합니다.

type(유형) — 하나를 고릅니다.
- 조치 불필요: 수정·보완을 요구하지 않는 의견(적합하다는 확인, 칭찬, 이미 반영되었다는 확인)
- 용어 변경: 낱말·명칭·기관명·법령명을 다른 것으로 바꾸라는 의견(옛 용어 → 새 용어)
- 형식: 정렬·줄 바꿈·글꼴·띄어쓰기·오탈자·쪽 번호처럼 편집·표기에 대한 의견
- 그림: 그림 속 내용이나 그림 품질에 대한 의견
- 내용: 내용을 추가·수정·삭제하라는 의견

verdict(판정) — 내용 의견에서만 판단하고, 다른 유형은 "확인 필요"로 둡니다.
- 반영: 의견이 요구한 내용이 [원고 문단]에 들어가 있음. 표현이 달라도(같은 뜻의 다른 낱말, 풀어 쓴 설명, 약어와 본딧말) 반영으로 봅니다.
  evidence에 그 내용이 있는 원고 문단 번호를 반드시 적습니다.
- 미반영: 의견이 요구한 내용이 [원고 문단] 어디에도 없음
- 확인 필요: 일부만 반영됨, 받은 문단만으로 판단할 수 없음, [원고 문단]이 없음,
  또는 같은 내용이 [반영 전 원고 문단]에도 이미 있어 의견 때문에 바뀐 것인지 알 수 없음(이때 already_before를 true로)
원고 문단에 없는 사실을 지어내지 않습니다. 확신할 수 없으면 "확인 필요"입니다.

suggestion: 미반영일 때만 원고에 넣을 수정 문장 후보 한 문장, 아니면 빈 문자열.
suggestion은 의견에 적힌 낱말과 요구만으로 쓴 한 문장입니다. 의견에 없는 설명·정의·수치·사례를 덧붙이지 않습니다(직무 내용은 집필자가 씁니다).
old_terms·new_terms: 용어 변경 의견이면 의견에 적힌 옛 용어와 새 용어(의견에 적힌 글자 그대로), 아니면 빈 목록.
reason: 왜 그렇게 보는지 한 문장. 문단 번호 대신 문단의 낱말을 들어 말합니다(사람은 번호를 보지 못합니다).

반드시 JSON 객체 하나만 출력합니다:
{"opinions": [{"no": <의견 번호(정수)>, "type": "조치 불필요|용어 변경|형식|그림|내용", "verdict": "반영|미반영|확인 필요",
 "evidence": [<원고 문단 번호(정수)>], "already_before": false, "reason": "<한 문장>", "suggestion": "", "old_terms": [], "new_terms": []}]}"""


def llm_status(asker=None) -> tuple[bool, str]:
    """LLM을 부를 수 있는가 → (가능, 상태 문구). 없으면 'LLM 미설정 — 이유'."""
    if asker is not None:
        return True, "사용(주입된 응답)"
    if not task_allowed(TASK):
        return False, f"LLM 미설정 — '{TASK}' 작업이 허용 목록(LLM_ALLOWED_TASKS)에서 빠져 있음"
    cfg = settings()
    if not cfg.ready:
        why = cfg.why_not
        return False, why if why.startswith("LLM 미설정") else f"LLM 미설정 — {why}"
    return True, f"사용({cfg.model})"


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


def build_prompt(opinions: list[Opinion], final: Manuscript, previous: Manuscript | None,
                 config: OpinionConfig = DEFAULT_CONFIG) -> dict:
    """묶음 하나의 질문 → {'user', '문단'(최종 원고 문단 번호), '반영 전 문단'(반영 전 원고 문단 번호), '의견'(글)}."""
    paragraphs = _merge([_picks(o, final, config) for o in opinions], config.llm_lines)
    before = _merge([_picks(o, previous, config) for o in opinions], config.llm_lines) if previous is not None else []
    parts = ["[원고 문단]"]
    parts += [f"[{no}] ({final.paras[i].where}) {final.paras[i].text[: config.llm_para_chars]}" for no, i in enumerate(paragraphs, 1)]
    if not paragraphs:
        parts.append("(없음 — 가리키는 자리가 없는 의견이므로 유형만 분류하고 verdict는 \"확인 필요\")")
    if previous is not None:
        parts.append("\n[반영 전 원고 문단]")
        parts += [f"[이전 {no}] ({previous.paras[i].where}) {previous.paras[i].text[: config.llm_para_chars]}" for no, i in enumerate(before, 1)]
        if not before:
            parts.append("(같은 범위를 반영 전 원고에서 찾지 못함)")
    parts.append("\n[검토 의견]")
    parts += [f"{no}. ({_where(o)}) {o.text}" for no, o in enumerate(opinions, 1)]
    return {"user": "\n".join(parts), "문단": paragraphs, "반영 전 문단": before, "의견": [o.text for o in opinions]}


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _terms(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value or [] if str(v).strip()] if isinstance(value, list) else []


def parse_answer(data: dict, n_opinions: int, paragraphs: list[int]) -> dict[int, dict]:
    """모델 JSON → {의견 순번(0부터): 답}. 없는 의견 번호·같은 번호의 두 번째 답은 버리고, 근거는 보낸 문단 번호만 남긴다.

    답: {'유형'(KINDS 밖이면 ''), '판정'(LLM_VERDICTS 밖이면 ''), '근거'(원고 문단 번호 목록), '버린 근거 번호',
         '반영 전에도 있음', '이유', '수정 문장', '옛 용어', '새 용어'}
    """
    out: dict[int, dict] = {}
    items = (data or {}).get("opinions")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        no = _int(item.get("no"))
        if no is None or not 1 <= no <= n_opinions or no - 1 in out:
            continue
        cited = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        numbers = [_int(c) for c in cited]
        valid = [paragraphs[c - 1] for c in dict.fromkeys(numbers) if c is not None and 1 <= c <= len(paragraphs)]
        kind, verdict = str(item.get("type") or "").strip(), str(item.get("verdict") or "").strip()
        out[no - 1] = {
            "유형": kind if kind in KINDS else "", "판정": verdict if verdict in LLM_VERDICTS else "",
            "근거": valid, "버린 근거 번호": len(set(numbers)) - len(valid),
            "반영 전에도 있음": item.get("already_before") is True,
            "이유": str(item.get("reason") or "").strip(), "수정 문장": str(item.get("suggestion") or "").strip(),
            "옛 용어": _terms(item.get("old_terms")), "새 용어": _terms(item.get("new_terms")),
        }
    return out


def ask_all(opinions: list[tuple[Opinion, str]], final: Manuscript, previous: Manuscript | None, *, asker=None,
            config: OpinionConfig = DEFAULT_CONFIG) -> tuple[list[dict | None], dict]:
    """(의견, 찾은 범위 이름) 목록 → (의견마다 답 | {'오류': 이유} | None(답하지 않음), 통계 {'호출','물은 의견','실패','모델'}).

    같은 범위 이름끼리 config.llm_batch개씩 묶어 묻는다. 답에는 '모델', '보낸 문단 수', '반영 전 문단 수'를 붙인다.
    asker: 테스트에서 LLM 대신 넣는 함수(build_prompt 결과 dict → {'data': {...}, 'model': …}).
    """
    groups: dict[str, list[int]] = {}
    for at, (_, label) in enumerate(opinions):
        groups.setdefault(label, []).append(at)
    answers: list[dict | None] = [None] * len(opinions)
    stats = {"호출": 0, "물은 의견": 0, "실패": 0, "모델": ""}
    for members in groups.values():
        for start in range(0, len(members), config.llm_batch):
            batch = members[start:start + config.llm_batch]
            prompt = build_prompt([opinions[at][0] for at in batch], final, previous, config)
            try:
                if asker is not None:
                    reply = asker(prompt)
                else:
                    reply = ask_json(TASK, SYSTEM, prompt["user"], max_output_tokens=config.llm_output_tokens).__dict__
            except LlmError as error:
                stats["실패"] += 1
                for at in batch:
                    answers[at] = {"오류": str(error)}
                continue
            model = str(reply.get("model") or "")
            stats["호출"] += 1
            stats["물은 의견"] += len(batch)
            stats["모델"] = model
            for order, answer in parse_answer(reply.get("data") or {}, len(batch), prompt["문단"]).items():
                answer.update({"모델": model, "보낸 문단 수": len(prompt["문단"]), "반영 전 문단 수": len(prompt["반영 전 문단"])})
                answers[batch[order]] = answer
    return answers, stats
