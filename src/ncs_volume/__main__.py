"""python -m ncs_volume 최종원고.hwp [--previous 기존원고.hwp] [--manual 쪽수] [--exclude-appendix] [--json 결과.json]

모듈별 분량 산정표(구성별 행·쪽, 합계 쪽·행, 기입 분량)와 권고 분량(75~85쪽) 표시, 기존 원고 대비 변경 분량을 출력한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .config import DEFAULT_CONFIG
from .pipeline import measure


def render(result: dict) -> str:
    """사람이 읽는 산정표(터미널용)."""
    out = [f"[{result['원고']}] {result['측정 방식']}"]
    out.append("가정: " + " / ".join(f"{k} {v}" for k, v in result["가정"].items()))
    if result["물리 쪽 수"] is not None:
        out.append(f"물리 쪽 수: {result['물리 쪽 수']}쪽(표지·개발진 포함 전체)")
    out.append(f"{'구성':<18}{'반영':>4}{'행':>8}{'쪽 환산':>9}{'물리 쪽':>10}{'그림 제외(쪽)':>14}")
    for row in result["구성"]:
        out.append(f"{row['구성']:<18}{'O' if row['반영'] else '-':>4}{row['행']:>8,}{row['쪽 환산']:>9}{row['물리 쪽']:>10}{row['시각 자료 제외(쪽)']:>14}")
    total = result["합계"]
    out.append(f"합계(반영 구성): {total['쪽']}쪽 {total['행']}행 → 기입 분량 {total['기입 분량']}매 "
               f"(행 합계 {total['행 합계']:,}, 쪽 환산 {total['쪽 환산']})")
    band = result["권고 분량"]
    out.append(f"권고 분량: {band['상태']} — {band['비고']}")
    change = result["변경"]
    if change:
        amount = change["변경 분량"]
        out.append(f"기존 원고 대비({change['기존 원고']}): 변경 {change['변경 행']:,}행 = {amount['쪽']}쪽 {amount['행']}행 → "
                   f"변경 분량 {amount['기입 분량']}매 (전체 행의 {change['변경 비율']})")
        out.append("  구성별 변경 행: " + ", ".join(f"{r['구성']} {r['변경 행']}" for r in change["구성별 변경 행"]))
    manual = result["수작업 대조"]
    if manual:
        out.append(f"수작업 대조: 자동 {manual['자동']} / 수작업 {manual['수작업']} → 오차율 {manual['오차율']} ({manual['기준']}, {manual['결과']})")
    out += [f"알림: {note}" for note in result["알림"]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncs_volume", description="원고 분량(쪽·행)을 구성별로 자동 산정한다(REQ-02-013).")
    parser.add_argument("manuscript", type=Path, help="최종 원고(hwp/hwpx)")
    parser.add_argument("--previous", type=Path, help="비교할 기존 학습모듈 원고(hwp/hwpx, 선택)")
    parser.add_argument("--manual", type=float, help="수작업으로 산정한 쪽수 — 주면 오차율을 낸다")
    parser.add_argument("--exclude-appendix", action="store_true", help="부록을 산정에서 뺀다(기본: 계약서 제13조 4항대로 포함)")
    parser.add_argument("--json", type=Path, help="결과를 이 JSON 파일로도 저장")
    args = parser.parse_args(argv)
    config = replace(DEFAULT_CONFIG, include_appendix=not args.exclude_appendix)
    try:
        result = measure(args.manuscript, previous=args.previous, manual_pages=args.manual, config=config)
    except ValueError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(render(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
