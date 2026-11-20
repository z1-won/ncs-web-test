"""LLM 2차 판정(선택) — 같은 범위를 가리키는 의견들을 번호 붙여 보내 '반영되지 않은 의견'만 받는다.

수행 ③·평가 ④의 LLM 후보 규칙과 같은 구조다(ncs_core.llm.line_findings).
  보내는 것   [원고 문단] 의견이 가리키는 범위에서 고른 문단(규칙이 찾은 근거 문단 + 의견과 글자가 겹치는 문단, 최대 llm_lines개)
              [검토 의견] 그 범위를 가리키는 내용 의견들(번호 붙임)
  받는 것     {"findings": [{"line": 의견 번호, "kind": "미반영|확인 필요", "reason", "suggestion"}]} — 지적하지 않은 의견은 '미반영 아님'
  쓰는 방법   규칙 판정(judge.judge)과 맞춰 본다. 둘이 엇갈리면 '확인 필요'. LLM은 판정을 후보까지만 바꾼다(사람이 확정).

원칙(ncs_core.llm과 같다)
- 키·반출 승인(LLM_ALLOW_UPLOAD=1)·작업 허용 목록(ncs_core.llm.ALLOWED_TASKS)이 모두 있을 때만 부른다. 아니면 규칙 판정을 그대로 둔다.
- 원고 전문이 아니라 고른 문단만 보낸다. 응답은 캐시된다. 모델이 댄 의견 번호가 보낸 번호 밖이면 버린다(line_findings).
- 용어·형식·그림·개발계획서·종합 의견은 보내지 않는다 — 용어는 집필자 확인, 형식·그림은 글로 확인할 수 없기 때문이다.

판정을 맞추는 표(규칙 → LLM → 결과)
  반영 후보   + 미반영 아님 → 반영 후보          반영 후보   + 미반영/확인 필요 → 확인 필요(엇갈림)
  확인 필요   + 미반영 아님 → 반영 후보(원고 전체에서 찾은 경우는 확인 필요 그대로)
  확인 필요   + 미반영     → 미반영 후보          확인 필요   + 확인 필요       → 확인 필요
  미반영 후보 + 미반영     → 미반영 후보(수정 문장 후보를 수정 제안에)
  미반영 후보 + 미반영 아님 → 확인 필요(엇갈림)   미반영 후보 + 확인 필요       → 확인 필요
"""

from __future__ import annotations

from ncs_core.llm import LlmError, line_findings

from .config import CHECK, DEFAULT_CONFIG, KIND_CONTENT, LLM_TASK, NOT_REFLECTED, PLAN, REFLECTED, SUMMARY, OpinionConfig
from .keys import Reading, compact
from .regions import Manuscript
from .sheet import Opinion

TASK = LLM_TASK
WHOLE = "원고 전체"
KIND_MISSING = "미반영"
NOT_FLAGGED = "미반영 아님"

SYSTEM = """당신은 NCS 학습모듈 원고의 검수 보조자입니다. 아래는 최종 원고에서 고른 [원고 문단]과, 그 부분에 대한 검토의견서의 [검토 의견]입니다.
각 의견이 요구한 내용이 원고 문단에 반영되었는지 보고, 반영되지 않은 의견만 찾습니다.
- 미반영: 의견이 추가·수정·삭제를 요구한 내용이 원고 문단 어디에도 반영되어 있지 않음
- 확인 필요: 일부만 반영되었거나, 받은 원고 문단만으로는 판단할 수 없음
찾지 않을 것:
- 표현이 달라도 의견이 요구한 내용이 원고에 들어가 있는 의견 (같은 뜻의 다른 낱말, 풀어 쓴 설명, 약어와 본딧말도 반영으로 봄)
- 수정·보완을 요구하지 않는 의견
원고 문단에 없는 사실을 지어내지 않습니다. 확신할 수 없으면 '확인 필요'로 넣습니다.
반드시 JSON 객체 하나만 출력합니다:
{"findings": [{"line": <의견 번호(정수)>, "kind": "미반영|확인 필요", "reason": "<왜 그렇게 보는지 한 문장>", "suggestion": "<미반영이면 원고에 넣을 문장 후보 한 문장, 아니면 빈 문자열>"}]}
모든 의견이 반영되었으면 {"findings": []}."""


def eligible(row: dict, opinion: Opinion, reading: Reading) -> bool:
    """LLM에 물을 의견인가 — 원고 글로 반영 여부를 볼 수 있는 내용 의견만."""
    return (reading.kind == KIND_CONTENT and opinion.group not in (PLAN, SUMMARY)
            and row["판정"] in (REFLECTED, NOT_REFLECTED, CHECK) and bool(row.get("범위")))


def _bigrams(text: str) -> set[str]:
    text = compact(text)
    return {text[i:i + 2] for i in range(len(text) - 1)}


def pick_paragraphs(row: dict, opinion: Opinion, manuscript: Manuscript, config: OpinionConfig = DEFAULT_CONFIG) -> list[int]:
    """의견 하나를 위해 보낼 문단 번호 — 규칙이 찾은 근거 문단과 그 이웃, 의견과 글자가 많이 겹치는 문단."""
    region = row.get("범위") or []
    if len(region) <= config.llm_per_opinion:
        return list(region)
    inside = set(region)
    chosen: list[int] = []
    for evidence in row.get("근거", []):
        at = evidence.get("문단 번호")
        for i in (at - 1, at, at + 1) if at is not None else ():
            if i in inside and i not in chosen:
                chosen.append(i)
    wanted = _bigrams(opinion.text)
    scored = sorted(((len(wanted & _bigrams(manuscript.paras[i].text)), -i) for i in region), reverse=True)
    for score, minus in scored:
        if len(chosen) >= config.llm_per_opinion or score < config.llm_min_overlap:
            break
        if -minus not in chosen:
            chosen.append(-minus)
    return sorted(chosen)


def _prompt(paragraphs: list[str], opinions: list[str]) -> str:
    return ("[원고 문단]\n" + "\n".join(f"- {text}" for text in paragraphs)
            + "\n\n[검토 의견]\n" + "\n".join(f"{no}. {text}" for no, text in enumerate(opinions, 1)))


def _apply(row: dict, finding: dict | None, model: str, sent: int) -> None:
    before = row["판정"]
    whole = row.get("찾은 범위") == WHOLE
    if finding is None:
        verdict = NOT_FLAGGED
        after = {REFLECTED: REFLECTED, CHECK: CHECK if whole else REFLECTED, NOT_REFLECTED: CHECK}[before]
    elif finding["kind"] == KIND_MISSING:
        verdict = KIND_MISSING
        after = CHECK if before == REFLECTED else NOT_REFLECTED
    else:
        verdict, after = CHECK, CHECK
    row["LLM"] = {"상태": "사용", "모델": model, "판정": verdict, "이유": finding["reason"] if finding else "",
                  "수정 문장": finding["suggestion"] if finding else "", "보낸 문단 수": sent}
    if after == NOT_REFLECTED and finding and finding["suggestion"]:
        row["수정 제안"] = finding["suggestion"]
    if before != after:
        row["판정"] = after
        row["비고"].append(f"LLM({model}) 판정 반영: {before} → {after}"
                         + (" — 규칙 판정과 엇갈림" if {before, verdict} in ({REFLECTED, KIND_MISSING}, {NOT_REFLECTED, NOT_FLAGGED}) else ""))
    elif finding is None and before == CHECK:
        row["비고"].append(f"LLM({model})은 미반영으로 보지 않음 — 의견이 가리키는 자리를 정하지 못해 판정은 그대로")


def refine_all(items: list[tuple[dict, Opinion, Reading]], manuscript: Manuscript, *, asker=None,
               config: OpinionConfig = DEFAULT_CONFIG) -> dict:
    """규칙 판정 행들에 LLM 판정을 더한다 → {'호출', '물은 의견', '실패'}.

    items: (judge.judge 결과 행, 의견, 읽기). 같은 범위('찾은 범위')를 가리키는 의견끼리 묶어 한 번에 묻는다.
    asker: 테스트에서 LLM 대신 넣는 함수((의견 줄 목록) → {'data': {'findings': […]}, 'model': …}).
    """
    groups: dict[str, list[tuple[dict, Opinion]]] = {}
    for row, opinion, reading in items:
        if eligible(row, opinion, reading):
            groups.setdefault(row["찾은 범위"], []).append((row, opinion))
    stats = {"호출": 0, "물은 의견": 0, "실패": 0}
    for members in groups.values():
        for start in range(0, len(members), config.llm_batch):
            batch = members[start:start + config.llm_batch]
            picked: list[int] = []
            for row, opinion in batch:
                picked += [i for i in pick_paragraphs(row, opinion, manuscript, config) if i not in picked]
            picked = sorted(picked)[: config.llm_lines]
            paragraphs = [manuscript.paras[i].text[: config.llm_para_chars] for i in picked]
            opinions = [opinion.text for _, opinion in batch]
            if not paragraphs:
                for row, _ in batch:
                    row["LLM"] = {"상태": "보낼 원고 문단 없음"}
                continue
            try:
                findings, model = line_findings(TASK, SYSTEM, _prompt(paragraphs, opinions), opinions, asker=asker)
            except LlmError as error:    # 통신 실패 등 — 규칙 판정을 그대로 둔다
                stats["실패"] += 1
                for row, _ in batch:
                    row["LLM"] = {"상태": f"LLM 호출 실패: {error}"}
                continue
            stats["호출"] += 1
            stats["물은 의견"] += len(batch)
            flagged = {finding["line"]: finding for finding in findings}
            for no, (row, _) in enumerate(batch, 1):
                _apply(row, flagged.get(no), model, len(paragraphs))
    return stats
