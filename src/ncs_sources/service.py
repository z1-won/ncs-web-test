"""REQ-02-008 저작권 검토 실행 — 원고 하나 → 출처 목록 + 점검 행 + 참고 자료 점검 + 문장 단위 출처 후보.

참고 자료 항목·서지 형식·본문 인용 대조·나열 순서·옛 학습모듈 표기는 참고 자료 엔진(ncs_references ①~④)을 그대로 돌린다.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ncs_core import load_document
from ncs_core.text import verdict

from .checks import check_entry
from .extract import attach, body_sources, figure_sources, table_sources
from .quotes import quote_candidates

# 규칙으로 할 수 없어 LLM(또는 사람·다른 자료)이 필요한 부분 — 화면과 보고에 그대로 보인다
LLM_NEEDED = (
    {"항목": "어문 자료 문장 단위 출처", "왜": "인용 부호 없이 남의 문장을 옮기거나 다듬어 쓴 문장은 규칙으로 못 찾음 → API 검토의 'LLM 검토'에서 '출처 표시 없는 인용'을 골라 실행하면 Claude가 출처가 필요해 보이는 문장(통계·정의·연구 결과·법령 문구·옮겨 온 문장)을 후보로 냄. 원 자료와 대조하지는 않음",
     "규칙이 하는 것": "인용 부호로 묶은 긴 문장 중 출처 표시가 없는 것을 후보로 냄"},
    {"항목": "'생성함'·'수정 보완함'이 실제 활용 유형과 맞는지(그림)", "왜": "그림 검수의 '⑦ AI 생성·수정 구분'에서 봄 — 출처 줄 짝(규칙), 서약서 비고, 그림 DB(같거나 비슷한 기존 그림), 그림 판독(Claude가 그림의 바탕이 실제 사진·화면·도표인지 추정)",
     "규칙이 하는 것": "표·본문은 출처 줄과 동사의 짝이 어긋난 경우(원 출처가 있는데 '생성함', 원 출처 없이 '수정 보완함')를 △로 냄"},
    {"항목": "출처 종류를 읽지 못한 출처의 판단", "왜": "F14 틀에 맞지 않는 출처(자유 서술)는 저작자·제목·쪽을 규칙으로 못 나눔. 무엇이 빠졌는지 읽는 데 LLM이 도움이 됨",
     "규칙이 하는 것": "틀과 다른 곳(연도 괄호·마침표 등)을 힌트로 냄"},
    {"항목": "출처가 그 그림·표·문장의 실제 원 출처인지", "왜": "적힌 출처가 사실인지는 원 자료를 찾아 대조해야 함. 웹 검색 기반 실존 확인은 별도 과제(제안서 p.17 외부 연계 제외)",
     "규칙이 하는 것": "하지 않음(적힌 대로 읽음)"},
)


def _row(entry: dict) -> dict:
    checks, notes, fixes = check_entry(entry)
    source = entry.get("source")
    label = entry.get("label")
    item = f"SRC-{entry['kind']}-{label.split(' ')[-1] if label else entry.get('source_para')}"
    return {
        "item_id": item, "구분": entry["kind"], "region_path": entry["region"],
        "원고": entry.get("source_line") or f"{entry.get('caption') or ''} (출처 줄 없음)".strip(),
        "그림·표": entry.get("caption"), "앞 문장": entry.get("before"),
        "체크": checks, "판정": verdict(checks), "비고": notes, "수정 제안": " / ".join(dict.fromkeys(fixes)) or None,
        "출처": None if source is None else {
            "종류": source.kind, "저작자": source.author, "연도": source.year, "URL": source.url, "확인 일자": source.checked_date,
            "쪽": source.cited_page, "공공누리": source.kogl_type, "인용 모듈": source.cited_module},
        "AI 표기": None if entry.get("ai") is None else {"원문": entry["ai"].raw, "도구": entry["ai"].tool, "동사": entry["ai"].action, "일자": entry["ai"].date},
        "문단": entry.get("source_para") if entry.get("source_para") is not None else entry.get("caption_para"),
    }


def _references(document, module_code: str) -> dict:
    """참고 자료 엔진(①~④)을 그대로 — 항목 목록과 점검 행. 모듈 코드를 못 읽으면 엔진이 멈추므로 사유를 남긴다."""
    try:
        from ncs_references.pipeline import evaluate_review, prepare_review
        context = prepare_review(document, module_code=module_code)
    except ValueError as error:
        return {"entries": [], "rows": [], "problem": str(error), "citations": 0}
    result = evaluate_review(context)
    return {"entries": [{"번호": e.get("n"), "항목": e["text"], "언어": e.get("script"), "저작자": (e.get("key") or {}).get("raw_author"),
                         "연도": (e.get("key") or {}).get("year")} for e in context.entries],
            "rows": result.checklist, "problem": None, "citations": len(context.citations)}


def review_sources(manuscript, *, module_code: str = "") -> dict:
    path = Path(manuscript)
    document = load_document(path)
    figures = [attach(e) for e in figure_sources(document)]
    tables = [attach(e) for e in table_sources(document)]
    used = {(e["section"], e["source_para"]) for e in figures + tables if e.get("source_para") is not None}
    refs = _references(document, module_code)
    end = None
    try:
        from ncs_references.pipeline import prepare_review
        end = (prepare_review(document, module_code=module_code).presence.get("참고 자료") or {}).get("k")
    except ValueError:
        pass
    body = [attach(e) for e in body_sources(document, used, end=end)]
    rows = [_row(e) for e in figures + tables + body]
    quotes = quote_candidates(document, end=end)
    count = Counter(r["구분"] for r in rows)
    problems = Counter(name for r in rows for name, v in r["체크"].items() if v in ("X", "△"))
    summary = {
        "그림 출처": count.get("그림", 0), "표": count.get("표", 0), "표 중 출처 있음": sum(1 for e in tables if e.get("source_line")),
        "본문 출처 줄": count.get("본문", 0), "참고 자료 항목": len(refs["entries"]), "문장 단위 출처 후보": len(quotes),
        "판정": dict(Counter(r["판정"] for r in rows)), "점검별 문제(X·△)": dict(problems),
        "출처 종류": dict(Counter((r["출처"] or {}).get("종류", "출처 없음") for r in rows)),
        "AI 표기": sum(1 for r in rows if r["AI 표기"]),
    }
    return {"manuscript": path.name, "summary": summary, "rows": rows, "references": refs,
            "quotes": quotes, "llm_needed": list(LLM_NEEDED)}
