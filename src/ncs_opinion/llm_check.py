"""LLM 2차 판정(선택) — (의견, 의견이 가리키는 원고 문단)을 보내 반영 여부 후보·근거 줄·수정 문장 후보를 받는다.

원칙(ncs_core.llm과 같다)
- 키·반출 승인(LLM_ALLOW_UPLOAD=1)·작업 허용 목록(ncs_core.llm.ALLOWED_TASKS)이 모두 있을 때만 부른다. 아니면 규칙 판정을 그대로 두고
  'LLM 미사용 — 이유'를 남긴다. 지금 허용 목록에 'opinion_reflection'이 없어 실제 호출은 일어나지 않는다(팀장 요청 이슈).
- 원고 전문이 아니라 규칙이 고른 범위의 문단 최대 llm_lines개만 번호를 붙여 보낸다. 응답은 캐시된다(ncs_core.llm).
- 모델이 댄 근거 줄 번호가 보낸 줄에 없거나, 근거 문장이 그 줄에 실제로 없으면 근거로 쓰지 않는다(환각 방지).
- LLM은 판정을 '후보'까지만 바꾼다. 규칙과 LLM이 엇갈리면 '확인 필요'. 용어·형식·그림·개발계획서 의견은 판정을 바꾸지 않고 의견만 붙인다.
"""

from __future__ import annotations

from ncs_core.llm import LlmError, ask_json

from .config import CHECK, DEFAULT_CONFIG, KIND_CONTENT, LLM_TASK, NOT_REFLECTED, PLAN, REFLECTED, OpinionConfig
from .keys import Reading, compact
from .regions import Manuscript
from .sheet import Opinion

SYSTEM = (
    "당신은 NCS 학습모듈 원고 검수 보조자다. 검토의견서의 의견 하나와, 그 의견이 가리키는 최종 원고의 문단(번호 붙임)을 받는다. "
    "의견의 요구가 원고에 반영되었는지 판단해 JSON 객체 하나로만 답한다: "
    '{"판정": "반영" | "미반영" | "판단불가", "근거_줄": [줄 번호], "근거_문장": "근거 줄에서 그대로 옮긴 짧은 구절", '
    '"이유": "한 문장", "수정_문장": "미반영이면 원고에 넣을 문장 후보, 아니면 빈 문자열"}. '
    "근거 줄은 반드시 받은 줄 번호 중에서 고른다. 확신이 없으면 판단불가로 답한다."
)


def _lines(manuscript: Manuscript, region: list[int], anchors: list[int], limit: int) -> list[int]:
    """범위에서 보낼 문단(근거 문단을 가운데에 두고 최대 limit개)."""
    if len(region) <= limit:
        return region
    center = region.index(anchors[0]) if anchors and anchors[0] in region else 0
    start = max(0, min(center - limit // 2, len(region) - limit))
    return region[start:start + limit]


def prompt(opinion: Opinion, lines: list[str]) -> str:
    numbered = "\n".join(f"{n}. {text}" for n, text in enumerate(lines, 1))
    where = " ".join(filter(None, [opinion.round, opinion.group, opinion.part or "", f"{opinion.page}쪽" if opinion.page else ""]))
    return f"[의견] ({where}) {opinion.text}\n\n[원고 문단]\n{numbered}"


def refine(row: dict, opinion: Opinion, reading: Reading, manuscript: Manuscript, *, asker=None,
           config: OpinionConfig = DEFAULT_CONFIG) -> dict:
    """규칙 판정 행(judge.judge 결과)에 LLM 판정을 더한다. asker: 테스트용 (줄 목록, 프롬프트) → {'data': {...}, 'model': …}."""
    region = row.get("범위") or []
    anchors = [e["문단 번호"] for e in row.get("근거", []) if "문단 번호" in e]
    chosen = _lines(manuscript, region, anchors, config.llm_lines)
    lines = [manuscript.paras[i].text for i in chosen]
    if not lines:
        row["LLM"] = {"상태": "보낼 원고 문단 없음"}
        return row
    user = prompt(opinion, lines)
    try:
        answer = asker(lines, user) if asker is not None else ask_json(LLM_TASK, SYSTEM, user).__dict__
    except LlmError as error:   # 미설정·미승인·허용 목록 밖·통신 실패 — 규칙 판정을 그대로 둔다
        row["LLM"] = {"상태": f"LLM 미사용 — {error}"}
        return row
    data = answer.get("data") or {}
    verdict = str(data.get("판정") or "판단불가")
    numbers = []
    for value in data.get("근거_줄") or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= len(lines) and number not in numbers:
            numbers.append(number)
    quote = str(data.get("근거_문장") or "")
    quoted_ok = not quote or any(compact(quote) in compact(lines[n - 1]) for n in numbers)
    evidence = [{"문단": lines[n - 1][: config.evidence_chars], "위치": manuscript.paras[chosen[n - 1]].where,
                 "문단 번호": chosen[n - 1]} for n in numbers]
    info = {"상태": "사용", "모델": str(answer.get("model") or ""), "판정": verdict, "이유": str(data.get("이유") or ""),
            "근거": evidence, "수정 문장": str(data.get("수정_문장") or "")}
    row["LLM"] = info
    if reading.kind != KIND_CONTENT or opinion.group == PLAN or row["판정"] not in (REFLECTED, NOT_REFLECTED, CHECK):
        return row
    before = row["판정"]
    if verdict == "반영":
        if not evidence or not quoted_ok:
            info["알림"] = "LLM이 원고에 있는 근거 줄을 대지 못해 판정에 쓰지 않음"
            row["판정"] = CHECK if before == REFLECTED else before
        else:
            row["판정"] = REFLECTED if before in (REFLECTED, CHECK) else CHECK
    elif verdict == "미반영":
        row["판정"] = NOT_REFLECTED if before in (NOT_REFLECTED, CHECK) else CHECK
        if info["수정 문장"]:
            row["수정 제안"] = info["수정 문장"]
    else:
        row["판정"] = CHECK if before == REFLECTED else before
    if row["판정"] != before:
        row["비고"].append(f"LLM 판정 반영: {before} → {row['판정']}")
    return row
