"""F02 수행 내용 ③: '안전·유의 사항'(필수 작성) 내용이 추상적으로 작성되지는 않았는가 — 블록당 1행.

두 가지를 본다.
  작성 여부(규칙)  X  '안전·유의 사항' 소제목이 없음 / 소제목 아래 내용이 없음 / '해당 사항 없음'만 적음
                    — 체크리스트가 '필수 작성'이라 했고 안내서 A-05(필수 구성요소 누락)는 자동 판정이다
                  O  내용이 한 줄 이상 있음
  추상성(LLM)     △  모델이 '추상적'이라고 본 줄이 있음 — 줄과 이유, 구체화 방향을 후보로 보여 준다(사람 확정)
                  O  모델이 추상적인 줄을 찾지 못함(비고에 모델 이름)
                  △  LLM 미설정·미승인·호출 실패 — 사람이 확인
추상적인지는 내용 판단이라 규칙으로 확정하지 않는다(안내서: 후보 제시 + 사람 확정). 보내는 것은 그 블록의 안전·유의 사항 줄뿐이다.
"""

from __future__ import annotations

import re

from ncs_core import NA, O, PASS, TRI, X, verdict, visible
from ncs_core.llm import LlmError, line_findings, settings
from ncs_core.notes import lines as numbered

ITEM_ID = "F02-수행-③"
WRITTEN = "③ 안전·유의 사항 작성"
ABSTRACT = "③ 추상적 표현 없음"
TASK = "perform3_safety"
NONE = re.compile(r"^[\s\-–•·]*해당\s*(사항)?\s*(이|은|이\s*)?\s*없[음다]")
HEADING = re.compile(r"^안\s*전\s*[‧·ㆍ･・⋅∙.]?\s*유\s*의\s*사\s*항")
MAX_SHOWN = 4

SYSTEM = """당신은 NCS 학습모듈 원고의 검수 보조자입니다. 아래는 수행 내용 하나의 '안전·유의 사항' 항목입니다.
내용이 추상적으로 작성된 항목만 찾습니다.
- 추상적: 무엇을, 어떤 상황에서, 어떻게 조심하는지 없이 일반적인 당부만 있는 문장
  (예: "안전에 유의한다.", "주의하여 작업한다.", "관련 규정을 준수한다.", "정확하게 수행한다.")
- 구체적(찾지 않음): 대상·상황·행동 가운데 둘 이상이 드러난 문장
  (예: "고객 개인정보가 담긴 예약 화면은 자리를 비울 때 잠근다.", "전원 케이블을 뽑은 뒤 덮개를 연다.")
- 문장이 짧다는 이유만으로 고르지 않습니다. 확신할 수 없으면 넣지 않습니다.
- 맞춤법·띄어쓰기·문장 종결은 이 검사의 대상이 아닙니다.
반드시 JSON 객체 하나만 출력합니다:
{"findings": [{"line": <입력 줄 번호(정수)>, "reason": "<왜 추상적인지 한 문장>", "suggestion": "<무엇을 더 적으면 되는지 한 문장>"}]}
추상적인 항목이 없으면 {"findings": []}."""


def _lines(block: dict) -> list[str]:
    return [text for text in ((item.get("text") or "").strip() for item in block.get("안전") or []) if text and not HEADING.match(text)]


def check_safety(blocks: list[dict], *, asker=None) -> list[dict]:
    """asker: 테스트에서 LLM 대신 넣는 함수((줄 목록) → {'data': {'findings': […]}, 'model': …})."""
    if not blocks:
        return [_row("section1", "", None, {WRITTEN: TRI}, {WRITTEN: "본문에서 '수행 내용' 머리를 찾지 못해 판단할 수 없음"}, None)]
    rows, cfg = [], settings()
    for block in blocks:
        region = f"section1 > {block['block_id']} > 안전·유의 사항"
        where = f"{block.get('unit') or ''} 수행 내용 {block.get('perform_no') or ''}".strip()
        texts = _lines(block)
        shown = [visible(t) for t in texts]
        fix = "안전·유의 사항에 그 수행 내용에서 조심할 대상·상황·행동을 구체적으로 적을 것"
        if "안전" in (block.get("소제목 누락") or []):
            rows.append(_row(region, where, shown, {WRITTEN: X, ABSTRACT: NA}, {WRITTEN: "'안전·유의 사항' 소제목을 찾지 못함(필수 작성)"}, fix))
            continue
        if not texts:
            rows.append(_row(region, where, shown, {WRITTEN: X, ABSTRACT: NA}, {WRITTEN: "'안전·유의 사항' 아래에 내용이 없음(필수 작성)"}, fix))
            continue
        if all(NONE.match(t) for t in texts):
            rows.append(_row(region, where, shown, {WRITTEN: X, ABSTRACT: NA},
                             {WRITTEN: f"「{shown[0]}」 — '해당 사항 없음'으로 둘 수 없음(필수 작성)"}, fix))
            continue
        if asker is None and not cfg.ready:
            rows.append(_row(region, where, shown, {WRITTEN: O, ABSTRACT: TRI},
                             {ABSTRACT: cfg.why_not + " — 안전·유의 사항이 추상적인지 사람이 확인"}, None))
            continue
        user = "\n".join(f"{no}. {text}" for no, text in enumerate(texts, 1))
        try:
            findings, model = line_findings(TASK, SYSTEM, user, texts, asker=asker)
        except LlmError as error:
            rows.append(_row(region, where, shown, {WRITTEN: O, ABSTRACT: TRI}, {ABSTRACT: f"LLM 호출 실패: {error}"}, None))
            continue
        if not findings:
            rows.append(_row(region, where, shown, {WRITTEN: O, ABSTRACT: O}, {"참고": f"LLM({model}) 추상적 표현 탐지 없음"}, None, findings=[]))
            continue
        parts = [f"「{visible(f['원문'])[:40]}」 — {f['reason']}" + (f" → {f['suggestion']}" if f["suggestion"] else "") for f in findings[:MAX_SHOWN]]
        if len(findings) > MAX_SHOWN:
            parts.append(f"외 {len(findings) - MAX_SHOWN}건")
        note = f"LLM({model}) 후보 {len(texts)}줄 중 {len(findings)}줄 — 사람 확인\n" + numbered(parts)
        rows.append(_row(region, where, shown, {WRITTEN: O, ABSTRACT: TRI}, {ABSTRACT: note}, fix, findings=findings))
    return rows


def _row(region, where, evidence, checks, notes, suggestion, findings=None):
    result = verdict(checks)
    row = {"item_id": ITEM_ID, "region_path": region, "위치": where, "원고": evidence, "체크": checks, "판정": result, "비고": notes,
           "수정 제안": None if result == PASS else suggestion}
    if findings is not None:
        row["상세"] = [f"{f['line']}번째 줄 「{visible(f['원문'])}」: {f['reason']}" for f in findings]
    return row
