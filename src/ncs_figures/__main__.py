"""python -m ncs_figures <명령>

  check     <원고.hwpx> [--out 결과] [--memo] [--vlm [--model 제공자:모델] [--read]]
            005 원고 이미지 검수: 행·요약·검수표(HTML, 인쇄하면 PDF)·03-003 기록(+메모 원고).
            --vlm: ③ 캡션 일치를 그림 모델로 본다(그림을 외부로 보냄 — LLM_ALLOW_UPLOAD·LLM_ALLOW_IMAGE_UPLOAD 필요).
            --read: 점검 대상 그림마다 판독(유형·설명·글자·키워드·맥락 요약)도 해서 검수표에 보인다.
  read      <원고.hwpx> [--model 제공자:모델] [--limit N] [--out 폴더]
            그림 판독 + 캡션 판정만 — 모델 비교 시험용(같은 원고를 --model만 바꿔 돌리고 결과 파일을 비교).
  tag       <원고·폴더...> --out 폴더 [--read [--model 제공자:모델]] [--force]
            009 기존 학습모듈 그림 태깅: 원고마다 modules/<코드>.jsonl + images/ + manifest.json.
            이미 끝난 원고(같은 파일·같은 판·같은 모델)는 건너뛴다. 끝나면 merge를 돌린다.
  merge     <out 폴더> [--overrides overrides.tsv]
            image_id로 합쳐 figures.jsonl(010·014로) · figures.csv(메타데이터 표) · review.tsv(사람 확인 표).
            review.tsv의 '필드'·'고친 값'을 채워 overrides.tsv로 저장하면 다음 merge에 반영(필드 예: source.kind, llm.image_type,
            확인 → 완료: 고칠 것 없이 확인만 끝냄).
  db build  <009 결과 폴더 또는 figures.jsonl...> [--db 경로]
            ④ DB 대조용 스텁 이미지 DB(SQLite)를 009 결과로 채운다. 기본 경로: 결과/figure_db.sqlite (FIG_DB로 바꿈).
            check는 --db를 주거나 기본 경로에 DB가 있으면 ④ DB 대조·③-2 출처-DB 일치를 한다.
  templates <최종본 폴더> [--out 목록.tsv]       양식 그림 목록 만들기

메모 원고는 여기(상위 계층)에서 ncs_service.annotate로 만든다 — ncs_figures 본체는 ncs_service를 모른다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def cmd_check(args) -> None:
    from .link import RecordingLink
    from .models import Resources
    from .pipeline import REPORT_NAME, run_review, save_result
    from .vision import load_model

    manuscript = Path(args.manuscript)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    link = RecordingLink(out / "_03-003_호출.jsonl")
    from .db import open_lookup
    from .marks import open_marks
    asker = load_model(args.model) if args.vlm else None
    lookup = open_lookup(args.db or None)
    marks = open_marks()                       # ② 로컬 OCR(Windows 내장 또는 PaddleOCR) — FIG_OCR=0이면 끔
    submissions = None
    if args.submit:                            # ⑥⑦ 집필자 제출 서류(+출력본 PDF는 쪽수 맞대기)
        from .submissions import read_documents
        submissions = read_documents([*args.submit, *([args.print] if args.print else [])])
    result = run_review(manuscript, resources=Resources(link=link, asker=asker, lookup=lookup, marks=marks, submissions=submissions),
                        module_code=args.module_code, read=args.read)
    folder = save_result(result, out, title=manuscript.stem)
    if link.count:
        (out / "_03-003_호출.jsonl").replace(folder / "03-003_호출.jsonl")
    if args.memo:
        from ncs_service.annotate import annotate_hwpx
        content, info = annotate_hwpx(manuscript.read_bytes(), result.rows)
        (folder / f"{result.module_code or '코드없음'}_{REPORT_NAME}_메모.hwpx").write_bytes(content)
        print(f"메모 {info['memos']}개(행 {info['placed']}개 배치, 못 단 행 {info['unplaced']}개)")
    s = result.summary
    if s["위험도"].get("판정 안 함"):
        print(f"위험도 판정 안 함 {s['위험도']['판정 안 함']}개 — ③ 캡션 일치를 안 함. --vlm을 붙여 다시 실행하세요(그림을 Claude로 보냄)")
    if s.get("목록에만 있음"):
        print(f"제출 서류 목록에만 있고 원고에 없는 그림: {s['목록에만 있음']}")
    print(f"그림 {s['그림']} · 검수 대상 {s['검수 대상']} · 양식 제외 {s['양식 제외']} · 위험도 {s['위험도']} · 모델 {s['모델 사용']} → {folder}")


def cmd_read(args) -> None:
    """모델 비교 시험용: 본문 그림마다 판독·캡션 판정 결과를 JSONL로. 같은 원고를 --model만 바꿔 돌려 비교한다."""
    from ncs_core.documents import load_document

    from .pipeline import prepare_figures
    from .reading import read_and_judge
    from .vision import cost, load_model

    manuscript = Path(args.manuscript)
    model = load_model(args.model)
    items = [i for i in prepare_figures(load_document(manuscript)) if i.kind == "본문 그림"]
    if args.limit:
        items = items[:args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{manuscript.stem}__{model.name.replace(':', '_')}.jsonl"
    totals = {"그림": 0, "새 호출": 0, "입력": 0, "출력": 0, "비용": 0.0, "실패": 0}
    started = time.perf_counter()
    with open(target, "w", encoding="utf-8") as f:
        for item in items:
            reading, caption = read_and_judge(item, model, module_name=manuscript.stem)
            for call in (reading, caption):
                if call.get("status") == "완료" and not call.get("cached"):
                    totals["새 호출"] += 1
                    totals["입력"] += call["usage"].get("input", 0)
                    totals["출력"] += call["usage"].get("output", 0)
                    totals["비용"] += cost(call["model"], call["usage"]) or 0.0
                elif call.get("status") != "완료":
                    totals["실패"] += 1
            totals["그림"] += 1
            record = {"image_id": item.image_id, "그림": item.ctx.figure_label, "캡션": item.ctx.caption,
                      "위치": item.ctx.region_path, "모델": model.name, "판독": reading, "캡션 판정": caption}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"  {item.ctx.figure_label}: {reading.get('유형') or reading.get('reason')} / 캡션 {caption.get('판정') or caption.get('reason')}")
    totals["비용"] = round(totals["비용"], 4)
    print(f"{model.name} · {totals} · {time.perf_counter() - started:.0f}초 → {target}")


def cmd_tag(args) -> None:
    from .export import merge, tag_folder
    from .vision import load_model

    model = load_model(args.model) if args.read else None
    manifest = tag_folder(args.paths, Path(args.out), model=model, force=args.force,
                          submissions=[*args.submit, *([args.print] if args.print else [])])
    print(f"합계 {manifest['합계']}")
    if not args.no_merge:
        print(f"합치기 {merge(Path(args.out), overrides=Path(args.out) / 'overrides.tsv')} → {args.out}")


def cmd_merge(args) -> None:
    from .export import merge

    out = Path(args.out)
    overrides = Path(args.overrides) if args.overrides else out / "overrides.tsv"
    print(f"{merge(out, overrides=overrides)} → {out}")


def cmd_db_build(args) -> None:
    from .db import build, default_db_path

    print(build(args.paths, Path(args.db) if args.db else default_db_path()))


def cmd_templates(args) -> None:
    from .config import DEFAULT_CONFIG
    from .templates import build_templates, write_templates

    rows = build_templates(sorted(Path(args.folder).glob("*.hwpx")))
    target = Path(args.out) if args.out else DEFAULT_CONFIG.templates_path
    write_templates(rows, target)
    print(f"양식 그림 {len(rows)}개 → {target}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ncs_figures", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("manuscript")
    p.add_argument("--out", default="결과")
    p.add_argument("--module-code", default="")
    p.add_argument("--memo", action="store_true", help="메모 단 원고 사본도 만든다")
    p.add_argument("--vlm", action="store_true", help="그림 모델로 ③ 캡션 일치를 본다(그림 외부 전송)")
    p.add_argument("--read", action="store_true", help="(--vlm과 함께) 그림 판독도 해서 검수표에 보인다")
    p.add_argument("--model", default="", help="제공자:모델 (기본 FIG_VISION_MODEL 또는 anthropic:claude-sonnet-5-5)")
    p.add_argument("--db", default="", help="④ DB 대조에 쓸 이미지 DB(비우면 FIG_DB 또는 결과/figure_db.sqlite가 있을 때만)")
    p.add_argument("--submit", nargs="+", default=[], help="⑥⑦ 제출 서류(수록 현황 목록·제작 목록·동의서·서약서 hwp/hwpx)")
    p.add_argument("--print", default="", help="(--submit과 함께) 출력본 PDF — 서약서 쪽수를 맞댄다")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("read")
    p.add_argument("manuscript")
    p.add_argument("--model", default="")
    p.add_argument("--limit", type=int, default=0, help="앞에서부터 그림 N장만")
    p.add_argument("--out", default="결과/그림판독")
    p.set_defaults(func=cmd_read)
    p = sub.add_parser("tag")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--read", action="store_true", help="그림 판독도 한다(그림을 Claude로 보냄)")
    p.add_argument("--model", default="")
    p.add_argument("--force", action="store_true", help="끝난 원고도 다시")
    p.add_argument("--submit", nargs="+", default=[], help="(원고 하나일 때) 수록 현황 목록·제작 목록·서약서(hwp/hwpx)")
    p.add_argument("--print", default="", help="(원고 하나일 때) 출력본 PDF(쪽 번호). 폴더에 같은 모듈 PDF가 있으면 자동")
    p.add_argument("--no-merge", action="store_true", help="합치기는 나중에")
    p.set_defaults(func=cmd_tag)
    p = sub.add_parser("merge")
    p.add_argument("out")
    p.add_argument("--overrides", default="")
    p.set_defaults(func=cmd_merge)
    p = sub.add_parser("db")
    db_sub = p.add_subparsers(dest="db_cmd", required=True)
    q = db_sub.add_parser("build")
    q.add_argument("paths", nargs="+")
    q.add_argument("--db", default="")
    q.set_defaults(func=cmd_db_build)
    p = sub.add_parser("templates")
    p.add_argument("folder")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_templates)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
