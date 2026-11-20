"""검토의견서 반영 여부 검토(REQ-02-003) — 의견서 여러 개와 최종 원고(+ 출력본 PDF, 반영 전 원고)를 읽어 의견별 판정 후보표를 낸다.

읽기는 모두 ncs_core로 한다: 원고·hwp 의견서는 documents.load_document, PDF는 pdf.load_pdf(선택 extra pypdf).
의견서 PDF는 머리말·꼬리말 띠를 나누지 않도록 band를 음수로 주어 모든 줄을 본문으로 받는다(의견서에는 띠가 없고,
실물 PDF는 좌표계가 뒤집혀 있어 띠 계산이 맞지 않는다 — 코어 이슈로 보고). 줄 순서가 뒤집힌 PDF는 sheet.flipped로 바로 놓는다.
"""

from __future__ import annotations

from pathlib import Path

from ncs_core.documents import detect_format, load_document
from ncs_core.pdf import PdfUnavailable, load_pdf

from .config import CHECK, DEFAULT_CONFIG, KIND_TERM, LLM_TASK, NO_ACTION, NOT_REFLECTED, REFLECTED, VERDICTS, OpinionConfig
from .judge import judge
from .keys import compact, read_opinion
from .llm_check import refine
from .regions import Manuscript, map_manuscript, print_pages
from .sheet import OpinionSheet, flipped, parse_lines, parse_tables

ALL_BAND = -100.0   # load_pdf의 띠 비율: 음수면 모든 줄이 본문으로 온다


def read_sheet(path: Path | str, round_: str = "") -> OpinionSheet:
    """검토의견서 파일 하나(PDF·hwp·hwpx) → OpinionSheet."""
    path = Path(path)
    fmt = detect_format(path)
    if fmt == "pdf":
        pdf = load_pdf(path, band=ALL_BAND)
        pages = [list(page.body) for page in pdf.pages]
        flip = flipped(pages[0]) if pages else False
        lines = [line for page in pages for line in (reversed(page) if flip else page)]
        return parse_lines(lines, path.name, round_)
    document = load_document(path)
    return parse_tables(document.tables, path.name, round_)


def read_manuscript(path: Path | str) -> Manuscript:
    path = Path(path)
    document = load_document(path)
    return map_manuscript(path.name, document.sections)


def _llm_status(asker) -> tuple[bool, str]:
    if asker is not None:
        return True, "사용(주입된 응답)"
    from ncs_core.llm import settings, task_allowed

    if not task_allowed(LLM_TASK):
        return False, f"LLM 미사용 — '{LLM_TASK}'가 ncs_core.llm.ALLOWED_TASKS에 없음(팀장 승인 후 추가)"
    cfg = settings()
    if not cfg.ready:
        return False, f"LLM 미사용 — {cfg.why_not}"
    return True, f"사용({cfg.model})"


def summarize(rows: list[dict]) -> dict:
    counts = {verdict: sum(1 for r in rows if r["판정"] == verdict) for verdict in VERDICTS}
    return {
        "총 의견": len(rows),
        "조치 요구": len(rows) - counts[NO_ACTION],
        "반영 후보": counts[REFLECTED],
        "미반영 후보": counts[NOT_REFLECTED],
        "확인 필요": counts[CHECK],
        "조치 불필요": counts[NO_ACTION],
        "용어 변경(집필자 확인)": sum(1 for r in rows if r["유형"] == KIND_TERM),
    }


def review(opinions: list[Path | str], manuscript: Path | str, *, rounds: list[str] | None = None,
           print_pdf: Path | str | None = None, previous: Path | str | None = None, use_llm: bool = False,
           asker=None, config: OpinionConfig = DEFAULT_CONFIG) -> dict:
    """의견서들 × 최종 원고 → 판정 후보표(JSON으로 그대로 내보낼 수 있는 dict).

    rounds: 의견서와 같은 순서의 차수('1차'·'2차') — 주면 파일 안의 표기 대신 쓴다. print_pdf: 최종 원고 출력본(근거 쪽 표시).
    previous: 반영 전 원고(초고본·완성본, 선택). use_llm: LLM 2차 판정을 시도(설정·승인·허용 목록이 없으면 판정은 그대로).
    asker: 테스트용 가짜 LLM.
    """
    if not opinions:
        raise ValueError("검토의견서를 하나 이상 올려 주세요")
    notes: list[str] = []
    sheets = [read_sheet(path, (rounds or [])[i] if i < len(rounds or []) else "") for i, path in enumerate(opinions)]
    final = read_manuscript(manuscript)
    before = read_manuscript(previous) if previous else None
    pages = None
    if print_pdf:
        try:
            pages = print_pages(load_pdf(print_pdf))
        except PdfUnavailable as error:
            notes.append(f"출력본을 읽지 못해 쪽 표시 없이 진행: {error}")
    names = {s.module_name for s in sheets if s.module_name}
    if len(names) > 1:
        notes.append(f"의견서의 학습모듈명이 서로 다름: {', '.join(sorted(names))}")
    llm_on, llm_state = _llm_status(asker) if use_llm else (False, "끔")

    rows, seen = [], set()
    for sheet in sheets:
        for opinion in sheet.opinions:
            key = (opinion.round, compact(opinion.text))
            if key in seen:       # 2차 의견서 파일에 1차 표가 함께 든 경우 — 같은 의견은 한 번만
                continue
            seen.add(key)
            reading = read_opinion(opinion.text, max_keys=config.max_keys)
            row = judge(opinion, reading, final, previous=before, pages=pages, config=config)
            if llm_on:
                row = refine(row, opinion, reading, final, asker=asker, config=config)
            row.pop("범위", None)
            rows.append({
                "번호": len(rows) + 1,
                "차수": opinion.round,
                "의견서": opinion.source,
                "구분": opinion.group,
                "구성": opinion.part or "",
                "쪽": opinion.page or "",
                "의견": opinion.text,
                "유형": reading.kind,
                "참조": [ref.label for ref in reading.refs],
                "핵심어": reading.keys if reading.kind != KIND_TERM else [],
                "용어 변경": {"옛": reading.old_terms, "새": reading.new_terms} if reading.kind == KIND_TERM else None,
                "의견서 읽기 추정": opinion.notes,
                **row,
            })
    return {
        "원고": final.name,
        "의견서": [{"파일": s.source, "차수": s.round, "학습모듈명": s.module_name, "의견 수": len(s.opinions)} for s in sheets],
        "출력본": Path(print_pdf).name if print_pdf else None,
        "반영 전 원고": before.name if before else None,
        "요약": summarize(rows),
        "의견": rows,
        "LLM": llm_state,
        "알림": notes,
        "판정 원칙": "모두 후보다(사람이 확정). 근거가 약하거나 원고 글로 확인할 수 없는 의견은 '확인 필요', 용어 변경은 집필자 확인.",
    }


def error_rate(rows: list[dict], labels: dict[int, str]) -> dict:
    """반영 여부 판단 오차율(검증 기준 6% 이내)을 재는 방법.

    labels: {의견 번호: '반영' | '미반영'} — 사람이 원고를 보고 정한 정답. 조치 불필요 의견은 빼고 센다.
    오차 = 판정 후보가 정답과 반대인 것(반영 후보 ↔ 미반영). '확인 필요'는 틀린 것이 아니라 '보류'로 따로 센다.
    """
    judged = wrong = held = 0
    for row in rows:
        truth = labels.get(row["번호"])
        if truth not in ("반영", "미반영") or row["판정"] == NO_ACTION:
            continue
        if row["판정"] == CHECK:
            held += 1
            continue
        judged += 1
        if (row["판정"] == REFLECTED) != (truth == "반영"):
            wrong += 1
    rate = wrong / judged if judged else None
    return {"정답 수": judged + held, "판정 수": judged, "틀림": wrong, "보류(확인 필요)": held,
            "오차율": None if rate is None else f"{rate * 100:.1f}%", "기준": "6% 이내",
            "결과": "판단불가" if rate is None else ("통과" if rate <= 0.06 else "미달")}
