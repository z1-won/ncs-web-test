"""python -m ncs_upscale 원고.hwpx [원고2.hwpx … | 폴더] --out 결과/업스케일

원고마다 <원고>_업스케일제안.hwpx(원본은 그대로), <원고>_업스케일보고서.html·.json, <원고>_그림/(원본·결과 PNG)을 만든다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ncs_core.documents import load_document
from ncs_misc.images import picture_records

from . import report
from .engine import DEFAULT_ENGINE, ENGINES
from .pipeline import DEFAULT_MIN_DPI, DEFAULT_TARGET_DPI, plan, upscale, write_hwpx


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncs_upscale", description="저해상도 그림을 업스케일해 같은 자리에 넣은 hwpx 제안본과 보고서를 만든다.")
    parser.add_argument("inputs", nargs="+", type=Path, help="hwpx 파일 또는 hwpx가 든 폴더")
    parser.add_argument("--out", type=Path, default=Path("결과") / "업스케일", help="결과 폴더 (기본 결과/업스케일)")
    parser.add_argument("--engine", choices=sorted(ENGINES), default=DEFAULT_ENGINE,
                        help="; ".join(f"{k}: {v.note}" for k, v in ENGINES.items()))
    parser.add_argument("--target-dpi", type=int, default=DEFAULT_TARGET_DPI, help="목표 실효 DPI (기본 300)")
    parser.add_argument("--min-dpi", type=int, default=DEFAULT_MIN_DPI, help="보고서 판정용: 이보다 낮으면 X (기본 200)")
    parser.add_argument("--max-scale", type=int, default=2, help="엔진 배율 상한 (기본 2). 4로 두면 목표까지 키우지만 waifu2x는 약 4배 느림")
    parser.add_argument("--limit", type=int, help="원고마다 앞에서부터 이만큼만 업스케일 (시연·시험용)")
    parser.add_argument("--dry-run", action="store_true", help="엔진을 돌리지 않고 대상 목록만 보고")
    parser.add_argument("--tools", type=Path, help="ncnn-vulkan 도구 폴더 (기본: 환경 변수 NCS_UPSCALE_TOOLS 또는 저장소 위 tools)")
    args = parser.parse_args(argv)
    if not 0 < args.min_dpi <= args.target_dpi:
        parser.error("0 < --min-dpi ≤ --target-dpi 여야 합니다")

    engine = ENGINES[args.engine]
    if not args.dry_run:
        engine.find_exe(args.tools)          # 엔진이 없으면 원고를 읽기 전에 멈춘다
    files = [f for p in args.inputs for f in (sorted(p.glob("*.hwpx")) if p.is_dir() else [p])]
    if not files:
        parser.error("hwpx 파일이 없습니다")
    args.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for path in files:
        print(f"[{path.name}]")
        try:
            document = load_document(path)
        except ValueError as error:
            print(f"  읽기 실패: {error}")
            failed += 1
            continue
        if document.format != "hwpx":
            print("  hwp는 그림을 읽지 못함 — hwpx로 바꿔서 실행")
            failed += 1
            continue
        records = picture_records(document)
        jobs, skipped = plan(records, document.binaries, engine, target_dpi=args.target_dpi, max_scale=args.max_scale)
        total = len(jobs)
        if args.limit is not None:
            jobs = jobs[: args.limit]
        limited = f" — 이번에는 앞 {len(jobs)}개만(--limit)" if len(jobs) < total else ""
        print(f"  그림 {len(records)}개 중 {args.target_dpi} DPI 미만 그림 파일 {total}개 업스케일 대상{limited}, 건너뜀 {len(skipped)}개")
        summary = {"원고": path.name, "엔진": f"{engine.name} — {engine.note}", "목표 DPI": args.target_dpi,
                   "배율 상한": args.max_scale, "그림 수": len(records), "대상 그림 파일": len(jobs)}
        if args.dry_run:
            for job in jobs:
                print(f"    {job.bin_id}: {job.px[0]}×{job.px[1]}px {job.dpi} DPI → x{job.scale} (필요 x{job.need:.1f})")
            continue
        started = time.perf_counter()
        upscale(jobs, engine, tools=args.tools)
        content = write_hwpx(path, jobs) if jobs else None
        done = [j for j in jobs if j.status == "완료"]
        summary.update({"완료": len(done), "목표 충족": sum(j.reaches_target for j in done),
                        "실패": sum(j.status == "실패" for j in jobs), "걸린 시간(초)": round(time.perf_counter() - started, 1)})
        if content and done:
            target = args.out / f"{path.stem}_업스케일제안.hwpx"
            target.write_bytes(content)
            summary["제안본"] = target.name
            print(f"  제안본: {target}")
        table = report.rows(jobs, skipped, engine=engine.name, target_dpi=args.target_dpi, min_dpi=args.min_dpi)
        saved = report.save(args.out, path.stem, jobs, table, summary)
        print(f"  보고서: {saved['html']}")
        print(f"  완료 {summary['완료']} (목표 충족 {summary['목표 충족']}) / 실패 {summary['실패']} / {summary['걸린 시간(초)']}초")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
