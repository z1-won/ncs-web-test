"""평가 ④(내용): 평가 항목이 학습 목표와 연관성 있는 구체적인 내용인가 — 학습당 1행, LLM 후보.

형태(명사형 종결, 학습 목표와 글자가 거의 같음)는 rules/items.py가 규칙으로 본다. 여기는 규칙으로 알 수 없는 두 가지를 모델에 묻는다.
  추상적      무엇을 평가하는지 드러나지 않는 일반적 표현('내용 이해 여부', '수행 능력')
  목표와 무관  그 학습의 어느 학습 목표와도 이어지지 않는 내용
결과는 사람 확인(△) 후보까지만: 모델이 고른 항목과 이유를 보여 주고, 못 찾으면 O(비고에 모델 이름).
LLM 미설정·미승인·호출 실패는 △. 보내는 것은 그 학습의 평가 준거 학습 목표와 평가 항목뿐이다.
"""

from __future__ import annotations

from ncs_core import NA, O, PASS, TRI, verdict, visible
from ncs_core.llm import LlmError, line_findings, settings
from ncs_core.notes import lines as numbered

ITEM_ID = "F02-평가-④"
CONTENT = "④ 평가 항목 구체성·목표 연관"
TASK = "evaluation4_items"
MAX_SHOWN = 4

SYSTEM = """당신은 NCS 학습모듈 원고의 검수 보조자입니다. 아래는 학습 하나의 [학습 목표]와 평가 방법 표의 [평가 항목]입니다.
평가 항목은 학습 목표와 연관성 있는 구체적인 내용이어야 합니다. 다음에 해당하는 평가 항목만 찾습니다.
- 추상적: 무엇을 평가하는지 드러나지 않는 일반적 표현 (예: "내용 이해 여부", "수행 능력", "학습 태도", "전반적인 숙련 정도")
- 목표와 무관: 제시된 어느 학습 목표와도 이어지지 않는 내용
찾지 않을 것:
- 학습 목표의 한 부분을 평가할 수 있는 내용으로 풀어 쓴 항목 (예: 목표 "객실 유형에 따라 정보를 구분할 수 있다." → 항목 "객실 유형별 부대시설 구분 여부")
- 종결 어미(여부·능력·수준·정도), 맞춤법, 띄어쓰기 — 이 검사의 대상이 아님
- 학습 목표와 글자가 거의 같은 항목 — 다른 검사가 봄
확신할 수 없으면 넣지 않습니다.
반드시 JSON 객체 하나만 출력합니다:
{"findings": [{"line": <평가 항목 번호(정수)>, "kind": "추상적|목표와 무관", "reason": "<이유 한 문장>", "suggestion": "<어떻게 고치면 되는지 한 문장>"}]}
해당하는 항목이 없으면 {"findings": []}."""


def check_item_content(regions: list[dict], *, asker=None) -> list[dict]:
    """asker: 테스트에서 LLM 대신 넣는 함수((평가 항목 줄 목록) → {'data': {'findings': […]}, 'model': …})."""
    rows, cfg = [], settings()
    for region in regions:
        lesson = region["lesson"]
        items = [entry for table in region.get("method_items", []) for entry in table]
        goals = [goal for units in region.get("criteria") or [] for unit in units for goal in unit["goals"]]
        texts = [f"[{entry['name']}] {entry['item']}" for entry in items]
        shown = {"학습 목표": len(goals), "평가 항목": [visible(t) for t in texts]}
        if not region.get("found") or not items:
            rows.append(_row(lesson, shown, {CONTENT: NA}, {CONTENT: "평가 항목을 읽지 못해 내용 확인 생략(명사형 종결 체크 참조)"}))
            continue
        if not goals:
            rows.append(_row(lesson, shown, {CONTENT: TRI}, {CONTENT: "평가 준거의 학습 목표를 읽지 못해 연관성을 확인하지 못함 — 사람 확인"}))
            continue
        if asker is None and not cfg.ready:
            rows.append(_row(lesson, shown, {CONTENT: TRI}, {CONTENT: cfg.why_not + " — 평가 항목이 구체적이고 학습 목표와 연관되는지 사람이 확인"}))
            continue
        user = ("[학습 목표]\n" + "\n".join(f"- {goal}" for goal in goals)
                + "\n\n[평가 항목]\n" + "\n".join(f"{no}. {text}" for no, text in enumerate(texts, 1)))
        try:
            findings, model = line_findings(TASK, SYSTEM, user, texts, asker=asker)
        except LlmError as error:
            rows.append(_row(lesson, shown, {CONTENT: TRI}, {CONTENT: f"LLM 호출 실패: {error}"}))
            continue
        if not findings:
            rows.append(_row(lesson, shown, {CONTENT: O}, {"참고": f"LLM({model}) 추상적·무관 항목 탐지 없음"}, findings=[]))
            continue
        parts = [f"「{visible(f['원문'])[:40]}」({f['kind'] or '확인'}) — {f['reason']}" for f in findings[:MAX_SHOWN]]
        if len(findings) > MAX_SHOWN:
            parts.append(f"외 {len(findings) - MAX_SHOWN}건")
        note = f"LLM({model}) 후보 {len(texts)}개 중 {len(findings)}개 — 사람 확인\n" + numbered(parts)
        rows.append(_row(lesson, shown, {CONTENT: TRI}, {CONTENT: note}, findings=findings))
    return rows


def _row(lesson, evidence, checks, notes, findings=None):
    result = verdict(checks)
    row = {"item_id": ITEM_ID, "region_path": f"section1 > 학습 {lesson} > 평가 > 평가 방법", "위치": f"학습 {lesson}", "원고": evidence,
           "체크": checks, "판정": result, "비고": notes,
           "수정 제안": None if result == PASS else "평가 항목을 학습 목표와 이어지는 구체적인 평가 내용으로 고쳐 쓸 것"}
    if findings is not None:
        row["상세"] = [f"{f['line']}번째 항목 「{visible(f['원문'])}」: {f['kind']} — {f['reason']}" + (f" → {f['suggestion']}" if f["suggestion"] else "")
                     for f in findings]
    return row
