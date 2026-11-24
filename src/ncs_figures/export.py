"""009 내보내기 — 원고별 태깅 결과를 폴더에 쌓고(재실행 시 끝난 원고 건너뜀), 마지막에 image_id로 합친다(설계 7.1·7.6·7.7).

<out>/
  manifest.json                원고마다 처리 기록 + 합계
  modules/<모듈코드 또는 파일>.jsonl   원고 하나의 레코드(합치기 전)
  images/<image_id>.png        원본 그림(PNG로만 바꿈)
  figures.jsonl                (merge) image_id당 1건 — 010·014로 넘기는 것
  figures.csv                  (merge) 메타데이터 표 — 그림이 쓰인 자리당 1줄(엑셀에서 열림)
  review.tsv                   (merge) 사람 확인 표 — 우선순위 순. '필드'·'고친 값'을 채워 overrides.tsv로 저장
  overrides.tsv                사람이 고친 값(image_id·필드·고친 값). merge가 읽어 덮어쓰고 overridden에 남긴다
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from pathlib import Path

from .tagging import TAG_VERSION, priority, tag_manuscript

MANIFEST = "manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _module_file(out: Path, manuscript: Path, code: str | None) -> Path:
    return out / "modules" / f"{code or manuscript.stem}.jsonl"


MANUSCRIPT_SUFFIXES = (".hwpx", ".hwp", ".pdf")


def _code(path: Path) -> str | None:
    from ncs_core.module_code import CODE_IN_NAME
    codes = list(dict.fromkeys(CODE_IN_NAME.findall(path.name)))
    return codes[0] if len(codes) == 1 else None


def manuscripts_in(paths) -> list[tuple[Path, Path | None]]:
    """[(원고, 출력본 PDF 또는 None)]. 폴더는 hwpx·hwp·pdf를 모두 찾는다.
    같은 모듈 코드의 hwpx(또는 hwp)와 PDF가 함께 있으면 hwpx를 원고로 쓰고 PDF는 그 원고의 출력본(쪽 번호)으로 쓴다 —
    hwpx가 표·문단 구조를 더 정확히 주기 때문. PDF만 있는 모듈은 PDF를 원고로 읽는다."""
    found: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            found.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in MANUSCRIPT_SUFFIXES and not f.name.startswith("~")))
        else:
            found.append(p)
    order = {".hwpx": 0, ".hwp": 1, ".pdf": 2}
    by_code: dict[str, list[Path]] = {}
    alone: list[Path] = []
    for f in found:
        code = _code(f)
        (by_code.setdefault(code, []) if code else alone).append(f)
    out = [(f, None) for f in alone]
    for files in by_code.values():
        files.sort(key=lambda f: order.get(f.suffix.lower(), 9))
        main = files[0]
        pdf = next((f for f in files[1:] if f.suffix.lower() == ".pdf"), None) if main.suffix.lower() != ".pdf" else None
        out.append((main, pdf))
    return sorted(out, key=lambda pair: str(pair[0]))


def tag_folder(paths, out: Path, *, model=None, force: bool = False, log=print, submissions=None, **kwargs) -> dict:
    """원고(또는 폴더)들을 태깅해 out에 쌓는다. 같은 파일·같은 판·같은 모델·같은 제출 서류면 건너뜀.
    submissions: 원고 하나를 돌릴 때 그 원고의 제출 서류 파일들(수록 현황 목록·제작 목록·서약서 hwp/hwpx, 출력본 PDF)."""
    from .submissions import read_documents
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = _read_json(out / MANIFEST, {"원고": {}})
    model_name = getattr(model, "name", None)
    for manuscript, print_pdf in manuscripts_in(paths):
        sha = _sha256(manuscript)
        key = str(manuscript.resolve())
        papers = [*map(str, submissions or []), *([str(print_pdf)] if print_pdf else [])]
        old = manifest["원고"].get(key, {})
        target = Path(old.get("결과", "")) if old.get("결과") else None
        if (not force and old.get("status") == "완료" and old.get("sha256") == sha and old.get("판") == TAG_VERSION
                and old.get("모델") == model_name and old.get("제출 서류", []) == papers and target and (out / target).exists()):
            log(f"  건너뜀 {manuscript.name}")
            continue
        started = time.perf_counter()
        try:
            listed = read_documents(papers) if papers else None
            records, summary = tag_manuscript(manuscript, model=model, images_dir=out / "images", submissions=listed, **kwargs)
        except Exception as error:  # noqa: BLE001 — 원고 하나가 실패해도 다음 원고로
            manifest["원고"][key] = {"file": manuscript.name, "sha256": sha, "status": "실패", "오류": str(error), "판": TAG_VERSION}
            log(f"  실패 {manuscript.name}: {error}")
            continue
        path = _module_file(out, manuscript, summary["모듈"]["code"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        manifest["원고"][key] = {"file": manuscript.name, "sha256": sha, "status": "완료", "판": TAG_VERSION, "모델": model_name,
                                 "제출 서류": papers,
                                 "module_code": summary["모듈"]["code"], "결과": str(path.relative_to(out)),
                                 "시간(초)": round(time.perf_counter() - started, 1),
                                 **{k: v for k, v in summary.items() if k not in ("원고", "모듈")}}
        log(f"  완료 {manuscript.name}: 그림 {summary['그림(image_id)']}개, 양식 제외 {summary['양식 제외']}, 사람 확인 {summary['사람 확인']}")
    rows = manifest["원고"].values()
    manifest["합계"] = {"원고": len(rows), "완료": sum(r["status"] == "완료" for r in rows), "실패": sum(r["status"] == "실패" for r in rows),
                       "그림 자리": sum(r.get("그림 자리", 0) for r in rows), "양식 제외": sum(r.get("양식 제외", 0) for r in rows),
                       "사람 확인": sum(r.get("사람 확인", 0) for r in rows)}
    manifest["판"] = TAG_VERSION
    (out / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


# ---------------------------------------------------------------- 합치기

def read_overrides(path: Path) -> dict[str, dict[str, str]]:
    """overrides.tsv(review.tsv와 같은 열 이름) → {image_id: {필드: 값}}. 필드·고친 값이 빈 줄은 무시."""
    if not path or not Path(path).is_file():
        return {}
    out: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            key, field, value = (row.get("image_id") or "").strip(), (row.get("필드") or "").strip(), row.get("고친 값")
            if key and field and value is not None and value.strip():
                out.setdefault(key, {})[field] = value.strip()
    return out


def _set(record: dict, dotted: str, value: str) -> None:
    node = record
    *parents, last = dotted.split(".")
    for name in parents:
        if not isinstance(node.get(name), dict):
            node[name] = {}
        node = node[name]
    node[last] = [v.strip() for v in value.split(",")] if isinstance(node.get(last), list) else value


def apply_fixes(record: dict, fields: dict[str, str]) -> int:
    """사람이 고친 값({필드: 값})을 레코드에 넣고 overridden에 남긴다. 넣은 칸 수를 돌려준다. merge(overrides.tsv)와 웹의 사람 확인이 함께 쓴다."""
    for field, value in fields.items():
        _set(record, field, value)
        if field not in record.setdefault("overridden", []):
            record["overridden"].append(field)
    return len(fields)


def merge(out: Path, *, overrides: Path | None = None) -> dict:
    """modules/*.jsonl → figures.jsonl·figures.csv·review.tsv. image_id가 같으면 하나로 합치고 uses를 모은다."""
    out = Path(out)
    merged: dict[str, dict] = {}
    broken: list[dict] = []
    for path in sorted((out / "modules").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            module = record.pop("module", None)
            for use in record["uses"]:
                use["module_info"] = module
            if record["image_id"] is None:
                broken.append(record)
                continue
            have = merged.get(record["image_id"])
            if have is None:
                record["modules"] = [module["code"] or module["file"]] if module else []
                merged[record["image_id"]] = record
                continue
            if (have["source"] or {}).get("text") != (record["source"] or {}).get("text") and \
                    "같은 그림인데 원고마다 출처가 다름" not in have["review_reasons"]:
                have["review_reasons"].append("같은 그림인데 원고마다 출처가 다름")
            have["uses"].extend(record["uses"])
            if module and (module["code"] or module["file"]) not in have["modules"]:
                have["modules"].append(module["code"] or module["file"])
            for reason in record["review_reasons"]:
                if reason not in have["review_reasons"]:
                    have["review_reasons"].append(reason)
            if have["llm"].get("status") != "완료" and record["llm"].get("status") == "완료":
                have["llm"] = record["llm"]
    fixes = read_overrides(overrides) if overrides else {}
    applied = 0
    for key, fields in fixes.items():
        record = merged.get(key)
        if record is None:
            continue
        applied += apply_fixes(record, fields)
    records = list(merged.values()) + broken
    for record in records:
        record["needs_human_review"] = bool(record["review_reasons"]) and not record.get("overridden")
    with open(out / "figures.jsonl", "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    write_csv(records, out / "figures.csv")
    review = write_review(records, out / "review.tsv")
    summary = {"그림(image_id)": len(merged), "그림 파일 깨짐": len(broken), "쓰인 자리": sum(len(r["uses"]) for r in records),
               "여러 원고에 쓰인 그림": sum(1 for r in merged.values() if len(r["modules"]) > 1),
               "사람 확인": review, "고친 값 반영": applied}
    (out / "merge_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


CSV_COLUMNS = ("image_id", "이미지 파일", "모듈 코드", "모듈명", "능력단위 코드", "능력단위명", "카탈로그 대응",
               "그림 번호", "그림 제목", "쪽", "쪽 근거", "본문 참조 문장", "학습", "학습 내용", "능력단위요소 코드", "능력단위요소명", "요소 이름 확인", "수행준거",
               "출처 문장", "출처 종류", "저작자", "연도", "URL", "확인 일자", "공공누리 유형", "인용 모듈", "인용 쪽", "출처 형식 문제",
               "AI 표기", "AI 활용 유형 후보", "AI 활용 유형", "AI 활용 유형 근거",
               "유형", "유형 근거", "유형(규칙)", "설명", "그림 속 글자", "키워드", "맥락 요약", "판독",
               "수록 현황(제작 방식)", "제작 목록", "AI 결과물 현황", "제출 서류 어긋남",
               "가로mm", "세로mm", "DPI", "300dpi 필요 픽셀", "형식", "가로px", "세로px",
               "사람 확인", "사유", "고친 필드", "위치(구역·문단)", "원고 파일")


def _flat(values) -> str:
    return " | ".join(str(v) for v in values if v not in (None, ""))


def write_csv(records: list[dict], path: Path) -> None:
    """메타데이터 표 — 자리(use)당 1줄. 엑셀이 한글을 깨지 않게 UTF-8 BOM."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for r in records:
            s, ai, llm = r.get("source") or {}, r.get("ai_marker") or {}, r.get("llm") or {}
            kind, listed = r.get("image_type") or {}, r.get("submissions") or {}
            decided = ai.get("ai_type") or {}
            status, made, ai_list = listed.get("수록 현황") or {}, listed.get("제작 목록") or {}, listed.get("AI 결과물 현황") or {}
            for u in r["uses"]:
                m = u.get("module_info") or {}
                writer.writerow([
                    r["image_id"], r.get("image_file"), m.get("code"), m.get("title"), m.get("unit_code"), m.get("unit_name"), m.get("unit_code_match"),
                    u["figure_label"], u["figure_title"], u.get("page"), u.get("page_from"),
                    _flat((u.get("context") or {}).get("본문 참조") or []), u["lesson"], u["content_no"], u["element_code"], u["element_name"], u["element_check"],
                    _flat(u["performance_criteria"]),
                    u.get("source_text"), s.get("kind"), s.get("author"), s.get("year"), s.get("url"), s.get("checked_date"), s.get("kogl_type"),
                    s.get("cited_module"), s.get("cited_page"), _flat(s.get("format_issues") or []),
                    ai.get("raw"), _flat(ai.get("ai_type_candidates") or []),
                    f"{decided['type']}. {decided['name']}" if decided.get("type") else "", _flat(decided.get("basis") or []),
                    kind.get("value"), kind.get("from"), r.get("rule_type"), llm.get("description"), _flat(llm.get("text_in_image") or []),
                    _flat(llm.get("keywords") or []), llm.get("context_summary"), llm.get("status"),
                    _flat([status.get("제작 방식"), status.get("종류")]) if listed else "", made.get("제목") if made else "",
                    _flat([ai_list.get("결과물 명"), ai_list.get("활용 AI"), f"p.{ai_list['쪽']}" if ai_list.get("쪽") else None]) if ai_list else "",
                    _flat(listed.get("어긋남") or []),
                    *(u["mm"] or [None, None])[:2], u["dpi"], _flat(u.get("min_px_300dpi") or []), r.get("format"), *(r.get("px") or [None, None])[:2],
                    "예" if r["needs_human_review"] else "", _flat(r["review_reasons"]), _flat(r.get("overridden") or []),
                    f"구역 {u['section']} 문단 {u['para']}", u.get("file"),
                ])


REVIEW_COLUMNS = ("우선", "image_id", "모듈", "그림", "캡션", "사유", "출처 문장", "유형", "필드", "고친 값", "메모")


def write_review(records: list[dict], path: Path) -> int:
    """사람 확인 표. '필드'(예: source.kind, source.author, image_type.value, ai_marker.ai_type.type)와 '고친 값'을 채운 줄을 overrides.tsv로 저장하면 다음 merge에 반영."""
    rows = [r for r in records if r["needs_human_review"]]
    rows.sort(key=lambda r: (priority(r["review_reasons"]), r["uses"][0].get("module") or "", r["uses"][0]["para"]))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(REVIEW_COLUMNS)
        for r in rows:
            first = r["uses"][0]
            writer.writerow([priority(r["review_reasons"]), r["image_id"], _flat(r.get("modules") or [first.get("module")]),
                             first["figure_label"] or f"구역 {first['section']} 문단 {first['para']}", first["caption"],
                             _flat(r["review_reasons"]), (r.get("source") or {}).get("text"),
                             (r.get("image_type") or {}).get("value") or (r.get("llm") or {}).get("image_type") or r.get("rule_type"), "", "", ""])
    return len(rows)
