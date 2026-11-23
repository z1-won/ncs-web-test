"""⑥ 수록 현황·제작 방식별 증빙, ⑦ AI 결과물 현황(서약서) 대조 — 집필자 제출 서류(Resources.submissions)와 원고를 맞댄다.
⑧ AI 결과물·외부 제작 그림이 기존 그림과 비슷한가 — 그림 DB(Resources.lookup)에서 지각 해시로 비슷한 후보.

모두 규칙(모델 없음). 결과는 후보와 근거이고, 의거성·실질적 유사성 같은 판단은 사람이 한다.
"""

from __future__ import annotations

import re

from ncs_core.text import NA, O, TRI, X

from ..models import CheckOutcome

# 수록 현황의 제작 방식 ↔ 원고 출처 줄 종류가 맞는가
METHOD_SOURCES = {
    "집필자 직접제작": {"집필진 제작"},
    "외부 제작의뢰": {"집필진 제작"},              # 제작 의뢰한 그림도 권리는 양도받아 '집필진 제작'으로 적는 것이 보통
    "공공누리·공유마당": {"공공누리", "웹·검색"},
    "포괄적 이용 허락": {"문헌", "웹·검색", "스크린숏", "법령", "알 수 없음"},
    "기개발 학습모듈": {"기존 학습모듈"},
}
SIMILAR_NEAR = 16          # ⑧: 복제(10)보다 느슨하게 — 다른 그림끼리는 16 이하가 0.2%뿐(2026-11-21 시험)


def _label_title(item):
    return item.ctx.figure_label, item.ctx.caption


def check_status(item, res, cfg, prior) -> list[CheckOutcome]:
    sub = res.submissions
    if not sub.status:
        return [CheckOutcome("⑥수록 현황", None, skipped="수록 현황 목록을 내지 않음"),
                CheckOutcome("⑥증빙", None, skipped="수록 현황 목록을 내지 않음")]
    label, caption = _label_title(item)
    entry = sub.status_of(label, caption)
    if entry is None:
        return [CheckOutcome("⑥수록 현황", X, f"수록 현황 목록에 {label or '이 그림'}이 없음",
                             suggestion="수록 현황 목록에 그림 번호·제목과 제작 방식 추가"), CheckOutcome("⑥증빙", NA)]
    out = []
    problems = []
    title = (item.ctx.figure_title or "").replace(" ", "")
    if title and title not in entry.title.replace(" ", ""):
        problems.append(f"제목이 다름 — 원고 「{caption}」, 목록 「{entry.title}」")
    kind = item.source.kind if item.source else None
    if entry.method is None:
        problems.append("목록에 제작 방식 ✓가 없음")
    elif kind and kind not in METHOD_SOURCES.get(entry.method, {kind}):
        problems.append(f"목록은 '{entry.method}'인데 원고 출처는 '{kind}'")
    out.append(CheckOutcome("⑥수록 현황", TRI if problems else O,
                            " / ".join(problems) or f"목록: {entry.method}{' ' + entry.kind if entry.kind else ''}",
                            suggestion="수록 현황 목록과 원고(그림 제목·출처)를 맞추기" if problems else None))
    out.append(_evidence(item, sub, entry))
    return out


def _evidence(item, sub, entry) -> CheckOutcome:
    """제작 방식별 증빙 — 외부 제작의뢰: 제작 목록(+사진이면 초상권 동의서), 포괄적 이용 허락: 이용허락 동의서,
    공공누리·공유마당: 출처 줄의 URL·검색 일자·사용 요건, 기개발 학습모듈: 출처 줄의 모듈 코드."""
    label, caption = _label_title(item)
    method = entry.method
    if method in (None, "집필자 직접제작"):
        return CheckOutcome("⑥증빙", NA, "직접 제작 — 따로 낼 증빙 없음" if method else "")
    if method == "외부 제작의뢰":
        if not sub.production:
            return CheckOutcome("⑥증빙", TRI, "외부 제작의뢰인데 사진·삽화 제작 목록(제작 계약서 붙임 1)을 내지 않음")
        if sub.production_of(label, caption) is None:
            return CheckOutcome("⑥증빙", X, "외부 제작의뢰인데 제작 목록에 이 그림이 없음", suggestion="제작 목록에 추가")
        if (entry.kind == "사진") and not sub.portrait_consents:
            return CheckOutcome("⑥증빙", TRI, "제작 목록에 있음. 사진에 인물이 있으면 초상권 사용 동의서가 필요한데 제출된 것이 없음")
        return CheckOutcome("⑥증빙", O, "제작 목록에 있음")
    if method == "포괄적 이용 허락":
        if sub.permission_of(label, caption) is None:
            return CheckOutcome("⑥증빙", X, "포괄적 이용 허락인데 지식재산권 이용허락 동의서(집필 계약서 붙임 3)에 이 저작물이 없음",
                                suggestion="이용허락 동의서 또는 이용허락 사실 증빙 제출")
        return CheckOutcome("⑥증빙", O, "이용허락 동의서에 있음")
    source = item.source
    if method == "공공누리·공유마당":
        missing = [name for name, ok in (("URL", source and source.url), ("검색 일자", source and source.checked_date),
                                         ("사용 요건(공공누리 유형)", source and (source.kogl_type or "공유마당" in source.text))) if not ok]
        return CheckOutcome("⑥증빙", X if missing else O,
                            f"공공누리·공유마당은 본문 출처에 원 출처(URL·검색 일자)와 사용 요건을 적어야 함 — 빠짐: {', '.join(missing)}" if missing
                            else "출처에 URL·검색 일자·사용 요건 있음")
    if method == "기개발 학습모듈":
        return CheckOutcome("⑥증빙", O if source and source.cited_module else X,
                            "출처에 인용한 학습모듈 코드 있음" if source and source.cited_module else "기개발 학습모듈인데 출처에 학습모듈 코드가 없음")
    return CheckOutcome("⑥증빙", NA)


def _tool_key(text: str | None) -> str:
    """'ChatGPT 6.0' · 'chat gpt' → 'chatgpt' (판 번호·띄어쓰기 무시)."""
    return re.sub(r"[\s\d.\-_]+|(?<=[a-z])v(?=\d)", "", (text or "").lower())


def check_ai_list(item, res, cfg, prior) -> list[CheckOutcome]:
    sub = res.submissions
    label, caption = _label_title(item)
    if not sub.ai:
        if item.ai is not None:
            return [CheckOutcome("⑦AI 현황 대조", None, skipped="서약서(생성형 AI 결과물 현황)를 내지 않음")]
        return [CheckOutcome("⑦AI 현황 대조", NA)]
    entry = sub.ai_of(label, caption)
    if item.ai is None and entry is None:
        return [CheckOutcome("⑦AI 현황 대조", NA)]
    if item.ai is None:
        return [CheckOutcome("⑦AI 현황 대조", X, f"서약서에는 AI 결과물('{entry.name}', {entry.tool})인데 원고에 AI 활용 표기가 없음",
                             suggestion="출처 줄 다음에 '○○를 활용하여 생성함(또는 수정 보완함). YYYY. M. D.' 추가")]
    if entry is None:
        return [CheckOutcome("⑦AI 현황 대조", X, f"원고에 AI 활용 표기({item.ai.tool})가 있는데 서약서 결과물 현황에 없음",
                             suggestion="서약서 결과물 현황에 결과물명·쪽수·활용 AI 추가")]
    problems = []
    if entry.tool and item.ai.tool and _tool_key(entry.tool) not in _tool_key(item.ai.tool) and _tool_key(item.ai.tool) not in _tool_key(entry.tool):
        problems.append(f"활용 AI가 다름 — 원고 '{item.ai.tool}', 서약서 '{entry.tool}'")
    page = sub.page_of(label)
    if entry.page and page and str(entry.page) != str(page):
        problems.append(f"쪽수가 다름 — 서약서 p.{entry.page}, 출력본 p.{page}")
    note = " / ".join(problems) or f"서약서와 맞음: {entry.name} · {entry.tool}" + (f" · p.{entry.page}" if entry.page else "")
    if not page and entry.page:
        note += " (출력본 PDF가 없어 쪽수는 못 맞댐)"
    return [CheckOutcome("⑦AI 현황 대조", TRI if problems else O, note,
                         suggestion="서약서 현황과 원고 표기를 맞추기" if problems else None)]


def check_similar(item, res, cfg, prior) -> list[CheckOutcome]:
    """⑧ AI로 만든 그림·외부에 제작 의뢰한 그림이 기존 그림(그림 DB)과 비슷한가 — 의거성·실질적 유사성 판단의 후보."""
    sub = getattr(res, "submissions", None)
    label, caption = _label_title(item)
    commissioned = bool(sub and sub.production and sub.production_of(label, caption))
    if item.ai is None and not commissioned:
        return [CheckOutcome("⑧AI 결과물 유사", NA)]
    lookup = res.lookup
    old_near = lookup.near
    lookup.near = SIMILAR_NEAR
    try:
        pairs = lookup.find(item.image_id, item.phash, exclude_module=prior.get("module_code", ""))
    finally:
        lookup.near = old_near
    prior["similar_matches"] = pairs           # ⑦생성·수정 구분이 쓴다('생성함'인데 기존 그림과 비슷함)
    what = "AI 결과물" if item.ai is not None else "외부 제작 그림"
    if not pairs:
        return [CheckOutcome("⑧AI 결과물 유사", O, f"{what} — 그림 DB에 비슷한 그림 없음(지각 해시 거리 {SIMILAR_NEAR} 초과)")]
    m = pairs[0][0]
    distance = round((1 - m.score) * 64)
    return [CheckOutcome("⑧AI 결과물 유사", TRI,
                         f"{what}이 기존 그림과 비슷함(거리 {distance}): {m.module} {m.figure_label or ''} {m.figure_title or ''} — "
                         "의거성·실질적 유사성은 사람이 판단(서약서 1항, 제작 계약서 붙임 1 개작 금지)",
                         suggestion="기존 그림을 따라 만들었는지 확인하고, 그렇다면 원 출처 이용허락 또는 새로 제작")]
