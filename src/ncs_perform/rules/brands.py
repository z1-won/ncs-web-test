"""F02 수행 내용 ②: 재료·기기 항목에 상표명·상품명·제조사명(특정 모델명)이 노출되지 않았는가 — 블록당 1행.

규칙으로는 고유명사를 알 수 없어 LLM에 묻는다(ncs_core.llm). 보내는 것은 블록의 '재료·자료'와 '기기(장비·공구)' 줄뿐이다.
결과는 사람 확인(△) 후보: 모델이 찾은 항목을 줄 번호·근거와 함께 보여 주고, 아무것도 못 찾으면 O(비고에 모델 이름).
LLM 키·반출 승인이 없으면 △ "LLM 미설정/미승인"으로 남기고 다른 항목은 평소대로 돈다.
"""

from __future__ import annotations

import json

from ncs_core import NA, O, PASS, TRI, verdict, visible
from ncs_core.llm import LlmError, ask_json, settings

ITEM_ID = "F02-수행-②"
CHECK = "② 상표·상품·제조사명 노출 없음"
TASK = "perform2_brands"

SYSTEM = """당신은 NCS 학습모듈 원고의 검수 보조자입니다. 아래 '재료·자료'와 '기기(장비·공구)' 목록에서
특정 회사가 소유한 상표명·상품명(브랜드), 제조사명, 특정 모델명·제품 코드가 드러난 항목만 찾습니다.
- 찾을 것: 특정 회사의 제품·서비스 이름(예: 특정 오피스 제품, 특정 클라우드 서비스, 특정 생성형 AI 서비스, 특정 제조사의 장비명),
  오픈소스 프로젝트의 고유 제품명도 포함(확인용)
- 찾지 않을 것(영문 표기라는 이유만으로 잡지 말 것):
  · 일반 명사·보통 명칭과 그 영문 병기(노트북, POS 시스템, 커피 머신, table cloth, guest invoice, customer database)
  · 업계 공용 약어·문서명·보고서명(BEO, PMS, POS, SOP, Aging Report, Daily Exchange Rate, Event Schedule, floor plan, layout)
  · 공공 표준·법령·규격 이름, 일반화된 기술 용어(관계형 데이터베이스, 웹 브라우저, 디지털카메라)
  · 오탈자·띄어쓰기·표기 오류(이 검사의 대상이 아님)
- 특정 회사의 제품인지 확신할 수 없는 영문 표현은 넣지 않습니다. 넣는 항목은 "어느 회사의 무엇"인지 말할 수 있어야 합니다.
반드시 JSON 객체 하나만 출력합니다:
{"findings": [{"line": <입력 줄 번호(정수)>, "text": "<노출된 표현 그대로>", "kind": "상표|상품명|제조사명|모델명",
               "generic": "<대체할 일반 명칭 제안>", "confidence": "high|medium|low", "reason": "<어느 회사의 무엇인지 한 문장>"}]}
노출이 없으면 {"findings": []}."""

MIN_CONFIDENCE = ("high", "medium")  # low는 후보로 세지 않고 상세에만 '참고'로 남긴다


def _lines(block: dict) -> list[tuple[int, str, str]]:
    """(줄 번호, 소제목, 텍스트) — 재료·기기 줄만. 줄 번호는 프롬프트 안에서만 쓰는 1부터의 번호."""
    out = []
    for name in ("재료", "기기"):
        for item in block.get(name) or []:
            text = (item.get("text") or "").strip()
            if text and not _is_heading(text):
                out.append((len(out) + 1, name, text))
    return out


def _is_heading(text: str) -> bool:
    return text in ("재료·자료", "재료 · 자료", "재료", "기기(장비·공구)", "기기(장비 · 공구)", "기기") or len(text) <= 1


def _ask(lines: list[tuple[int, str, str]]) -> dict:
    user = "\n".join(f"{no}. [{name}] {text}" for no, name, text in lines)
    return ask_json(TASK, SYSTEM, user).__dict__


def check_brands(blocks: list[dict], *, asker=_ask) -> list[dict]:
    """asker: 테스트에서 LLM 대신 넣는 함수((줄 목록) → LlmAnswer.__dict__ 꼴 dict)."""
    rows = []
    cfg = settings()
    for block in blocks:
        lines = _lines(block)
        region = f"section1 > 학습 {block.get('lesson')} > {block.get('unit') or ''} > 수행 내용 {block.get('perform_no') or ''}".replace("  ", " ")
        where = f"{block.get('unit') or ''} 수행 내용 {block.get('perform_no') or ''}".strip()
        shown = [f"[{name}] {visible(text)}" for _, name, text in lines]
        if not lines:
            rows.append(_row(region, where, shown, {CHECK: NA}, {CHECK: "재료·기기 줄이 없음"}, None))
            continue
        if not cfg.ready:
            rows.append(_row(region, where, shown, {CHECK: TRI}, {CHECK: cfg.why_not + " — 사람이 상표·상품·제조사명을 확인"}, None))
            continue
        try:
            answer = asker(lines)
        except LlmError as error:
            rows.append(_row(region, where, shown, {CHECK: TRI}, {CHECK: f"LLM 호출 실패: {error}"}, None))
            continue
        all_findings = _valid_findings(answer.get("data") or {}, lines)
        findings = [f for f in all_findings if f["confidence"] in MIN_CONFIDENCE]
        low = [f for f in all_findings if f["confidence"] not in MIN_CONFIDENCE]
        model = answer.get("model", cfg.model)
        if not findings:
            notes = {"참고": f"LLM({model}) 탐지 없음" + (f" (확신 낮은 표현 {len(low)}건은 상세 참고)" if low else "")}
            rows.append(_row(region, where, shown, {CHECK: O}, notes, None, findings=all_findings))
            continue
        checks = {CHECK: TRI}
        parts = [f"「{f['text']}」({f['kind']}, {f['confidence']}) → 일반 명칭 「{f['generic']}」" if f.get("generic") else f"「{f['text']}」({f['kind']})"
                 for f in findings[:4]]
        notes = {CHECK: f"LLM({model}) 후보 {len(findings)}건 — 사람 확인: " + " / ".join(parts) + (" …" if len(findings) > 4 else "")}
        rows.append(_row(region, where, shown, checks, notes, "상표·상품·제조사명을 일반 명칭으로 바꿈(예: 특정 제품명 → 기능을 나타내는 보통 명칭)", findings=all_findings))
    if not blocks:
        rows.append(_row("section1", "", None, {CHECK: TRI}, {CHECK: "본문에서 '수행 내용' 머리를 찾지 못해 판단할 수 없음"}, None))
    return rows


def _valid_findings(data: dict, lines: list[tuple[int, str, str]]) -> list[dict]:
    """모델 출력 중 실제 입력 줄을 가리키고 text가 그 줄에 있는 것만 남긴다(환각 방지)."""
    by_no = {no: text for no, _, text in lines}
    out = []
    for f in data.get("findings") or []:
        try:
            no = int(f.get("line"))
        except (TypeError, ValueError):
            continue
        text = str(f.get("text") or "").strip()
        if no in by_no and text and text.replace(" ", "") in by_no[no].replace(" ", ""):
            out.append({"line": no, "text": text, "kind": str(f.get("kind") or "상표"), "generic": str(f.get("generic") or ""),
                        "confidence": str(f.get("confidence") or "medium"), "reason": str(f.get("reason") or ""), "원문": by_no[no]})
    return out


def _row(region, where, evidence, checks, notes, suggestion, findings=None):
    result = verdict(checks)
    row = {
        "item_id": ITEM_ID,
        "region_path": region,
        "위치": where,
        "원고": evidence,
        "체크": checks,
        "판정": result,
        "비고": notes,
        "수정 제안": None if result == PASS else suggestion,
    }
    if findings is not None:
        row["상세"] = [f"{f['line']}번째 줄 「{f['원문']}」: {f['text']} — {f['kind']}({f['confidence']}) {f['reason']}"
                     + (" [확신 낮음 — 후보에서 제외]" if f["confidence"] not in MIN_CONFIDENCE else "") for f in findings]
    return row
