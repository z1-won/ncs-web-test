"""009 이미지 추출·출처 태깅 — 원고 하나 → 그림 레코드(image_id당 하나, 쓰인 자리는 uses).

입력: hwpx·hwp(그림 개체를 바로 읽음), PDF(쪽마다 글 줄과 그림을 위치 순으로 늘어놓아 같은 방법으로 읽음 — ncs_core.pdf_figures).
공통 앞부분(prepare_figures: 맥락·식별·양식 제외·출처 해석)은 005와 같다. 여기서 더하는 것(설계 7.4):
- 원 학습모듈(파일 이름의 코드)과 NCS 카탈로그(ncs_elements.tsv)로 능력단위·능력단위요소·수행준거 연결
- 쪽: PDF는 그림이 놓인 쪽, hwp·hwpx는 출력본 PDF(submissions.print_pdf)에서 캡션이 있는 쪽
- 유형: 그림 판독(Claude)이 있으면 그것, 없으면 규칙 후보(픽셀 색 분포 — 사진 / 도표·삽화)
- AI 활용 유형(F08 표기 예 1~5): 출처 종류 + 생성/수정 보완으로 후보, 그림 유형·AI 표기 문구·서약서 비고로 좁힘
- 제출 서류 대응: 수록 현황 목록·제작 목록·AI 결과물 현황과 그림 번호·제목을 맞대 항목과 어긋남을 적음
- (선택) 그림 판독 — 005와 같은 read_figure·같은 캐시·같은 전송 조건
- 사람 확인 사유(7.6)

출처는 원고에 적힌 출처 줄을 규칙으로 읽은 것이다(인터넷에서 찾아오지 않는다).
"""

from __future__ import annotations

import difflib
import io
import re
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from ncs_core.documents import detect_format, load_document
from ncs_core.figure_context import body_structure, figure_contexts, parse_toc
from ncs_core.goals import normalize
from ncs_core.module_code import CODE_IN_NAME
from ncs_core.ncs_catalog import catalog as load_catalog
from ncs_core.source_line import ai_type_candidates, parse_ai_marker, parse_source

from .checks.submission import check_ai_list, check_status
from .config import DEFAULT_CONFIG, FigureConfig
from .ids import file_sha256, image_id, phash
from .models import FigureItem
from .reading import read_figure
from .select import classify, transfer_of
from .templates import load_templates

TAG_VERSION = "figures-tag-3"            # 2: hwp·PDF 입력, 쪽, 유형 후보, AI 유형 좁히기, 제출 서류 대응
CRITERIA_MIN = 0.5            # 학습 목표 ↔ 수행준거 짝을 인정하는 최소 유사도(difflib 비율)
CRITERION_CODE = re.compile(r"^\s*(\d+\.\d+)")
BULLET = re.compile(r"^[\s•·▪ㆍ‧◦○\-]+")

# 사람 확인 사유 → 우선(1이 먼저). 설계 7.6
REASON_PRIORITY = {
    "출처 줄 없음": 1, "같은 그림인데 원고마다 출처가 다름": 1, "그림 파일을 읽지 못함": 1,
    "출처 형식 문제": 2, "캡션 없는 그림": 2, "AI 활용 유형 못 정함": 2,
    "캡션 학습 번호와 본문 구조 학습 번호가 다름": 3, "학습명과 능력단위요소명이 다름": 3,
    "수행준거 연결 약함": 3, "학습 목표를 읽지 못함": 3, "카탈로그 버전 다름": 3, "카탈로그에 없는 능력단위": 3,
    "모듈 코드 못 찾음": 2, "판독 실패": 3,
    "수록 현황 목록과 다름": 1, "제작 목록에 없음": 1, "AI 결과물 현황과 다름": 1, "그림 유형 모름": 3,
}
AI_TYPES = {1: "집필진 작성 내용 기반 AI 생성", 2: "집필진 삽화 AI 수정 보완", 3: "기존 이미지 보정", 4: "AI 창작", 5: "원본 사진 AI 수정"}
# AI 표기 문구·서약서 비고에서 표기 예를 가리키는 말(F08 표기 예의 제목에서 뽑음)
AI_TYPE_WORDS = ((4, re.compile(r"창작")), (2, re.compile(r"삽화|보완|보정|수정")), (1, re.compile(r"학습\s*내용|본문|내용을?\s*(바탕|기반)|흐름도|작성")))


def priority(reasons) -> int:
    return min((REASON_PRIORITY.get(r.split(" — ")[0], 3) for r in reasons), default=9)


# ---------------------------------------------------------------- 모듈·카탈로그

def module_info(path: Path, cat=None) -> dict:
    """원고 파일 이름 → 모듈 코드·제목, 카탈로그의 능력단위."""
    codes = list(dict.fromkeys(CODE_IN_NAME.findall(path.name)))
    code = codes[0] if len(codes) == 1 else None
    title = (path.stem.split(code, 1)[-1].strip("_ -") or path.stem) if code else path.stem   # 코드 뒤의 글자 = 모듈명
    info = {"code": code, "title": title, "file": path.name, "unit_code": None, "unit_name": None, "unit_code_match": "없음"}
    detail = cat.unit_detail(code) if (cat is not None and code) else None
    if detail:
        info.update(unit_code=detail["code"], unit_name=detail["name"],
                    unit_code_match="정확" if detail["code"] == code[2:] else "버전 다름")
    return info


def _clean(text: str) -> str:
    return normalize(BULLET.sub("", text or ""))


def link_element(detail: dict | None, lesson: int | None, lesson_title: str | None) -> dict:
    """학습 N → 능력단위요소 {unit}.N. 학습명과 요소명이 다르면 사람 확인."""
    if not detail or not lesson:
        return {"element_code": None, "element_name": None, "element_check": None}
    element = next((e for e in detail["elements"] if e["no"] == lesson), None)
    if element is None:
        return {"element_code": None, "element_name": None, "element_check": "요소 없음"}
    same = lesson_title is not None and re.sub(r"\s", "", _clean(lesson_title)) == re.sub(r"\s", "", _clean(element["name"]))
    check = "일치" if same else ("학습명 모름" if lesson_title is None else "이름 다름")
    return {"element_code": element["code"], "element_name": element["name"], "element_check": check}


def link_criteria(detail: dict | None, lesson: int | None, goals: list[str]) -> tuple[list[str], str | None]:
    """학습 내용 N-M의 학습 목표 문장마다 요소 N의 수행준거 중 가장 비슷한 것. (코드 목록, 문제)."""
    if not detail or not lesson:
        return [], None
    element = next((e for e in detail["elements"] if e["no"] == lesson), None)
    if element is None:
        return [], None
    if not goals:
        return [], "학습 목표를 읽지 못함"
    codes = []
    for goal in goals:
        g = _clean(goal)
        scored = []
        for criterion in element["criteria"]:
            m = CRITERION_CODE.match(criterion)
            body = _clean(CRITERION_CODE.sub("", criterion, count=1))
            scored.append((difflib.SequenceMatcher(None, g, body, autojunk=False).ratio(), m.group(1) if m else None))
        score, code = max(scored, default=(0.0, None))
        if code and score >= CRITERIA_MIN:
            codes.append(code)
    codes = sorted(dict.fromkeys(codes), key=lambda c: tuple(int(x) for x in c.split(".")))
    return codes, (None if codes else "수행준거 연결 약함")


# ---------------------------------------------------------------- 그림 하나

PHOTO_COLORS = 1500          # 128px로 줄여 색을 단계(32)로 묶었을 때 서로 다른 색 수 — 사진은 많고 도표·삽화는 적음
PHOTO_TOP_SHARE = 0.2        # 가장 많은 색(보통 흰 바탕)의 비율 — 도표·삽화는 바탕이 넓음


def pixel_type(data: bytes) -> str | None:
    """픽셀 색 분포로 '사진' / '도표·삽화'. 읽지 못하면 None."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = image.convert("RGB")
        image.thumbnail((128, 128))
    except Exception:  # noqa: BLE001
        return None
    pixels = list(image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata())
    if not pixels:
        return None
    counts: dict[tuple, int] = {}
    for r, g, b in pixels:
        key = (r >> 3, g >> 3, b >> 3)
        counts[key] = counts.get(key, 0) + 1
    top = max(counts.values()) / len(pixels)
    return "사진" if len(counts) >= PHOTO_COLORS and top < PHOTO_TOP_SHARE else "도표·삽화"


def rule_type(item: FigureItem) -> str | None:
    """판독 없이 고르는 유형(규칙) — 캡션의 '화면'이 먼저, 그다음 픽셀 색 분포. 판독과는 image_type.from으로 구분."""
    if re.search(r"화면|스크린|캡처", item.ctx.caption or ""):
        return "화면 캡처"
    found = pixel_type(item.ctx.data) if item.ctx.data else None
    return found


def ai_type(item: FigureItem, image_type: str | None, note: str = "") -> dict | None:
    """F08 표기 예 1~5 — 후보에서 그림 유형·AI 표기 문구·서약서 비고로 좁힌다. {'candidates', 'type', 'name', 'basis'}."""
    if item.ai is None:
        return None
    candidates = list(ai_type_candidates(item.source, item.ai))
    basis = [f"{item.source.kind if item.source else '출처 없음'} + {item.ai.action}함 → {', '.join(map(str, candidates))}"]
    if set(candidates) == {2, 5} and image_type:
        keep = 5 if image_type.startswith("사진") else 2
        candidates = [keep]
        basis.append(f"그림 유형 {image_type} → {keep}")
    if len(candidates) > 1:
        said = re.sub(r"생성\s*함|수정\s*보완\s*함", "", item.ai.raw or "")      # 표기 동사 자체는 근거가 아님
        for where, text in (("AI 표기 문구", said), ("서약서 비고", note)):
            hit = next((n for n, word in AI_TYPE_WORDS if n in candidates and word.search(text or "")), None)
            if hit:
                candidates = [hit]
                basis.append(f"{where} '{(text or '').strip()[:40]}' → {hit}")
                break
    chosen = candidates[0] if len(candidates) == 1 else None
    return {"candidates": candidates, "type": chosen, "name": AI_TYPES.get(chosen) if chosen else None, "basis": basis}


def submission_part(item: FigureItem, submissions) -> tuple[dict | None, list[str]]:
    """수록 현황 목록·제작 목록·AI 결과물 현황에서 이 그림의 항목과 어긋남(005 ⑥⑦과 같은 규칙). 서류가 없으면 (None, [])."""
    if submissions is None or not (submissions.status or submissions.production or submissions.ai):
        return None, []
    label, caption = item.ctx.figure_label, item.ctx.caption
    status = submissions.status_of(label, caption) if submissions.status else None
    made = submissions.production_of(label, caption) if submissions.production else None
    ai = submissions.ai_of(label, caption) if submissions.ai else None
    part = {"수록 현황": {"제목": status.title, "제작 방식": status.method, "종류": status.kind} if status else None,
            "제작 목록": {"제목": made.title, "종류": made.kind} if made else None,
            "AI 결과물 현황": {"결과물 명": ai.name, "쪽": ai.page, "활용 AI": ai.tool, "비고": ai.note} if ai else None,
            "어긋남": []}
    reasons = []
    res = SimpleNamespace(submissions=submissions)
    outcomes = (check_status(item, res, DEFAULT_CONFIG, {}) if submissions.status else []) + check_ai_list(item, res, DEFAULT_CONFIG, {})
    names = {"⑥수록 현황": "수록 현황 목록과 다름", "⑥증빙": "제작 목록에 없음", "⑦AI 현황 대조": "AI 결과물 현황과 다름"}
    for outcome in outcomes:
        if outcome.value in ("X", "△") and outcome.note:
            if outcome.name == "⑥증빙" and "제작 목록" not in outcome.note:
                continue                               # 009는 세 목록과의 대응만 본다(동의서·URL 같은 증빙은 005 ⑥)
            part["어긋남"].append(outcome.note)
            reasons.append(f"{names[outcome.name]} — {outcome.note}")
    return part, reasons


def min_px_300dpi(mm) -> list[int] | None:
    if not mm or not all(mm):
        return None
    return [round(v / 25.4 * 300) for v in mm]


def to_png(data: bytes) -> bytes | None:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return buffer.getvalue()
    except Exception:  # noqa: BLE001
        return None


def llm_part(reading: dict | None) -> dict:
    if reading is None:
        return {"status": "미실행", "reason": "판독 안 함"}
    if reading.get("status") != "완료":
        return {"status": reading.get("status"), "reason": reading.get("reason"), "model": reading.get("model")}
    return {"status": "완료", "model": reading.get("model"), "prompt_version": reading.get("prompt_version", "fig_read"),
            "image_type": reading.get("유형"), "description": reading.get("설명"), "text_in_image": reading.get("그림 속 글자") or [],
            "keywords": reading.get("키워드") or [], "context_summary": reading.get("맥락 요약") or "",
            "confidence": reading.get("확신도"), "problems": reading.get("problems") or []}


def page_of(item: FigureItem, pdf_pages: dict, submissions) -> tuple[str | None, str | None]:
    """(쪽, 어디서 읽었나). PDF 원고면 그림이 놓인 쪽, 아니면 출력본 PDF에서 캡션이 있는 쪽."""
    info = pdf_pages.get(item.ctx.bin_id or "")
    if info:
        return info["folio"] or str(info["page"]), ("PDF" if info["folio_source"] == "읽음" else
                                                     "PDF(추정)" if info["folio"] else "PDF 장 순서")
    print_pdf = getattr(submissions, "print_pdf", None)
    if print_pdf is not None and item.ctx.figure_label:
        page = submissions.page_of(item.ctx.figure_label)
        if page:
            return page, "출력본 PDF"
    return None, None


def load_figure_document(path: Path):
    """hwpx·hwp → (Document, {}), PDF → (Document, {그림 id: 쪽 정보})."""
    if detect_format(path) == "pdf":
        from ncs_core.pdf_figures import load_pdf_figures
        return load_pdf_figures(path)
    return load_document(path), {}


def use_of(item: FigureItem, module: dict, detail: dict | None, lesson_titles: dict, goals: dict) -> tuple[dict, list[str]]:
    """그림이 놓인 자리 하나 + 그 자리에서 생긴 사람 확인 사유."""
    ctx = item.ctx
    reasons: list[str] = []
    element = link_element(detail, ctx.lesson, lesson_titles.get(ctx.lesson))
    criteria, problem = link_criteria(detail, ctx.lesson, goals.get(ctx.content_no, []) if ctx.content_no else [])
    if ctx.lesson and not ctx.content_no and detail:
        # 구조 파서가 학습 1을 놓치는 경우(코어 과제 C1)가 대부분 — 고치면 이 사유가 사라진다
        problem = f"학습 목표를 읽지 못함 — 본문 구조에서 학습 {ctx.lesson}의 위치를 못 찾음"
    if element["element_check"] == "이름 다름":
        reasons.append("학습명과 능력단위요소명이 다름")
    if problem:
        reasons.append(problem)
    if ctx.lesson and ctx.lesson_by_structure and ctx.lesson != ctx.lesson_by_structure:
        reasons.append(f"캡션 학습 번호와 본문 구조 학습 번호가 다름 — 캡션 {ctx.lesson}, 구조 {ctx.lesson_by_structure}")
    if item.kind == "캡션 없는 그림":
        reasons.append("캡션 없는 그림")
    use = {"module": module["code"], "file": module["file"], "section": ctx.section, "para": ctx.para,
           "figure_label": ctx.figure_label, "figure_title": ctx.figure_title, "caption": ctx.caption or None,
           "region_path": ctx.region_path, "lesson": ctx.lesson, "content_no": ctx.content_no,
           **element, "performance_criteria": criteria,
           "source_text": item.source.text if item.source else None,
           "page": ctx.page, "page_estimate": ctx.page_estimate,
           "mm": list(ctx.mm), "dpi": ctx.dpi, "min_px_300dpi": min_px_300dpi(ctx.mm), "in_table": ctx.in_table, "in_frame": ctx.in_frame,
           # 그림이 무엇에 대한 것인지 — 원고에서 코드가 모은 주변 글(모델 판독과 별개, 011 추천·사람 확인 재료)
           "context": {"본문 참조": list(ctx.references), "앞": list(ctx.before), "뒤": list(ctx.after),
                       "표": list(ctx.table_context)}}
    return use, reasons


def source_part(item: FigureItem) -> dict | None:
    if item.source is None:
        return None
    s = asdict(item.source)
    s["format_issues"] = list(s["format_issues"])
    return s


def ai_part(item: FigureItem) -> dict | None:
    if item.ai is None:
        return None
    return {**asdict(item.ai), "ai_type_candidates": list(ai_type_candidates(item.source, item.ai))}


# ---------------------------------------------------------------- 원고 하나

def tag_manuscript(path: Path, *, cfg: FigureConfig = DEFAULT_CONFIG, model=None, cat=None,
                   templates: frozenset[str] | None = None, images_dir: Path | None = None,
                   submissions=None) -> tuple[list[dict], dict]:
    """원고 하나(hwpx·hwp·pdf) → (레코드 목록, 요약). model이 있으면 그림 판독도 한다(전송 조건은 read_figure가 본다).
    submissions(ncs_figures.submissions.Submissions): 이 원고의 수록 현황 목록·제작 목록·AI 결과물 현황·출력본 PDF."""
    path = Path(path)
    document, pdf_pages = load_figure_document(path)
    cat = cat if cat is not None else load_catalog()
    module = module_info(path, cat)
    detail = cat.unit_detail(module["code"]) if (cat is not None and module["code"]) else None
    structure = body_structure(document)
    toc = parse_toc([document.sections[0], document.sections[1]]) if len(document.sections) > 1 else None
    lesson_titles = {row["no"]: row["text"] for row in (toc or {}).get("학습", [])}
    goals = {f"{u['no']}-{u['sub']}": u.get("goal") or [] for u in (structure or {}).get("units", [])}
    if templates is None:
        templates = load_templates(cfg.templates_path)

    records: dict[str, dict] = {}
    broken: list[dict] = []
    counts = {"그림 자리": 0, "양식 제외": 0, "내보냄(자리)": 0, "그림 파일 깨짐": 0, "판독 완료": 0, "판독 미실행·실패": 0}
    labels: set[str] = set()
    for ctx in figure_contexts(document, structure=structure, lookback=cfg.lookback):
        counts["그림 자리"] += 1
        key = image_id(ctx.data)
        source = parse_source(ctx.source_line) if ctx.source_line else None
        transfer, why = transfer_of(source, cfg)
        item = FigureItem(ctx=ctx, image_id=key, file_sha256=file_sha256(ctx.data), phash=phash(ctx.data),
                          kind=classify(ctx, key, templates=templates, cfg=cfg), source=source,
                          ai=parse_ai_marker(ctx.ai_marker_line) if ctx.ai_marker_line else None,
                          transfer=transfer, transfer_reason=why)
        if item.kind in ("양식", "양식 후보"):
            counts["양식 제외"] += 1
            continue
        use, reasons = use_of(item, module, detail, lesson_titles, goals)
        use["page"], use["page_from"] = page_of(item, pdf_pages, submissions)
        if ctx.figure_label:
            labels.add(ctx.figure_label)
        if key is None:
            counts["그림 파일 깨짐"] += 1
            broken.append({"image_id": None, "uses": [use], "review_reasons": ["그림 파일을 읽지 못함"], "needs_human_review": True,
                           "pipeline_version": TAG_VERSION})
            continue
        counts["내보냄(자리)"] += 1
        record = records.get(key)
        if record is None:
            reading = read_figure(item, model, module_name=module["title"]) if model is not None else None
            llm = llm_part(reading)
            counts["판독 완료" if llm["status"] == "완료" else "판독 미실행·실패"] += 1
            guess = rule_type(item)
            image_type = llm.get("image_type") if llm["status"] == "완료" else guess
            listed, listed_reasons = submission_part(item, submissions)
            reasons.extend(listed_reasons)
            ai_note = ((listed or {}).get("AI 결과물 현황") or {}).get("비고", "")
            marker = ai_part(item)
            if marker is not None:
                marker["ai_type"] = ai_type(item, image_type, ai_note)
            record = records[key] = {
                "image_id": key, "file_sha256": item.file_sha256, "phash": item.phash,
                "format": ctx.format, "px": list(ctx.px),
                "source": source_part(item), "ai_marker": marker,
                "rule_type": guess, "llm": llm,
                "image_type": {"value": image_type, "from": "그림 판독" if llm["status"] == "완료" else "규칙" if guess else None},
                "submissions": listed,
                "transfer": {"value": item.transfer, "reason": item.transfer_reason},
                "uses": [], "review_reasons": [], "needs_human_review": False, "overridden": [],
                "pipeline_version": TAG_VERSION,
            }
            if images_dir is not None:
                png = to_png(ctx.data)
                if png:
                    images_dir.mkdir(parents=True, exist_ok=True)
                    target = images_dir / f"{key}.png"
                    if not target.exists():
                        target.write_bytes(png)
                    record["image_file"] = f"images/{key}.png"
            if source is None:
                reasons.append("출처 줄 없음")
            elif source.format_issues:
                reasons.append("출처 형식 문제 — " + "; ".join(source.format_issues))
            if item.ai is not None and record["ai_marker"]["ai_type"]["type"] is None:
                reasons.append("AI 활용 유형 못 정함 — " + ", ".join(map(str, record["ai_marker"]["ai_type"]["candidates"])) + " 중 하나")
            if image_type is None:
                reasons.append("그림 유형 모름")
            if llm["status"] == "실패":
                reasons.append("판독 실패")
        elif (record["source"] or {}).get("text") != (source.text if source else None):
            reasons.append("같은 그림인데 원고마다 출처가 다름")
        record["uses"].append(use)
        for reason in reasons:
            if reason not in record["review_reasons"]:
                record["review_reasons"].append(reason)
    if not module["code"]:
        for record in records.values():
            record["review_reasons"].append("모듈 코드 못 찾음")
    elif detail is None:
        for record in records.values():
            record["review_reasons"].append("카탈로그에 없는 능력단위")
    elif module["unit_code_match"] == "버전 다름":
        for record in records.values():
            record["review_reasons"].append(f"카탈로그 버전 다름 — 원고 {module['code'][2:]}, 카탈로그 {module['unit_code']}")
    out = list(records.values()) + broken
    for record in out:
        record["module"] = module
        record["needs_human_review"] = bool(record["review_reasons"])
    only = submissions.unmatched(labels) if submissions is not None else {}
    summary = {"원고": path.name, "형식": document.format, "모듈": module, "그림(image_id)": len(records), **counts,
               "쪽": "PDF" if pdf_pages else ("출력본 PDF" if getattr(submissions, "print_pdf", None) is not None else "없음"),
               **({"제출 서류": getattr(submissions, "files", []), "목록에만 있음": only} if submissions is not None else {}),
               "사람 확인": sum(1 for r in out if r["needs_human_review"]),
               "구조": "읽음" if structure else "못 읽음"}
    return out, summary
