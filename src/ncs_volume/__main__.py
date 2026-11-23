"""python -m ncs_volume 최종원고.hwp [--print 출력본.pdf] [--previous 기존원고.hwp] [--manual 쪽수] [--unit-price 원]
                       [--contract-pages 매] [--exclude-appendix] [--json 결과.json]

모듈별 분량 산정표(구성별 행·쪽, 합계 쪽·행, 기입 분량)와 권고 분량(75~85쪽) 표시, 기존 원고 대비 변경 분량,
출력본 PDF로 잰 쪽(한글 계산값과 나란히), 계약서 기준 집필료를 출력한다.
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
        out.append(f"기존 원고 대비({change['기존 원고']}): 변경 {change['변경 행']:,}행 = 이어 붙여 {amount['쪽 환산']}쪽 환산 → "
                   f"변경 분량 {amount['기입 분량']}매 (전체 행의 {change['변경 비율']})")
        out.append(f"  방법: {amount['방법']}")
        ref = change["물리 쪽 기준(참고)"]
        out.append(f"  참고(물리 쪽마다 ½쪽 규칙, 산정에 쓰지 않음): {ref['쪽']}쪽 {ref['행']}행 → {ref['기입 분량']}매")
        out.append("  구성별 변경 행: " + ", ".join(f"{r['구성']} {r['변경 행']}" for r in change["구성별 변경 행"]))
    printed = result.get("출력본")
    if printed:
        out += _render_printed(printed)
    adopted = result.get("채택 분량")
    if adopted:
        out.append(f"채택 분량: {adopted['기입 분량']}매 — {adopted['근거']}")
    fee = result.get("집필료")
    if fee:
        out.append(f"집필료: {fee['산식']} (단가 근거: {fee['단가 근거']}"
                   + (f", 계약 분량 {fee['계약 분량']}매 → 인정 {fee['인정 분량']}매" if fee["계약 분량"] else "") + ")")
        if fee["개선 기준"]:
            out.append(f"  개선 기준(변경 분량): {fee['개선 기준']['산식']}")
        out.append(f"  세금: {fee['세금']}")
        out += [f"  알림: {note}" for note in fee["알림"]]
    manual = result["수작업 대조"]
    if manual:
        out.append(f"수작업 대조: 자동 {manual['자동']} / 수작업 {manual['수작업']} → 오차율 {manual['오차율']} ({manual['기준']}, {manual['결과']})")
    out += [f"알림: {note}" for note in result["알림"]]
    return "\n".join(out)


def _render_printed(printed: dict) -> list[str]:
    out = [f"출력본({printed['파일']}): " + ("측정에 사용" if printed["사용"] else printed["사유"])]
    if not printed["사용"]:
        return out
    diff = printed["쪽 수 차이"]
    out.append(f"  전체 쪽 수: 출력본 {printed['전체 쪽 수']}쪽 / 한글 줄 배치 {printed['한글 물리 쪽 수'] or '-'}쪽"
               + (f" (차이 {diff:+d})" if diff is not None else ""))
    out.append(f"  {'구성':<18}{'출력본 쪽':>10}{'인쇄 쪽':>10}{'쪽 환산(PDF)':>13}{'쪽 환산(한글)':>13}{'차이':>8}")
    for row in printed["구성"]:
        def show(value):
            return "-" if value is None else value
        out.append(f"  {row['구성']:<18}{row['출력본 쪽'] or '-':>10}{row['인쇄 쪽'] or '-':>10}"
                   f"{show(row['쪽 환산(출력본)']):>13}{show(row['쪽 환산(한글)']):>13}{show(row['차이']):>8}")
    total = printed["합계"]
    out.append(f"  합계(출력본): {total['쪽']}쪽 {total['행']}행 → 기입 분량 {total['기입 분량']}매 "
               f"(한글 계산 {total['한글 계산 기입 분량']}매, 차이 {total['차이']:+d})")
    out.append("  측정 구분: " + " / ".join(f"{m['항목']}={m['방법']}" for m in printed["측정 구분"]))
    out += [f"  알림: {note}" for note in printed["알림"]]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncs_volume", description="원고 분량(쪽·행)을 구성별로 자동 산정한다(REQ-02-013).")
    parser.add_argument("manuscript", type=Path, help="최종 원고(hwp/hwpx)")
    parser.add_argument("--previous", type=Path, help="비교할 기존 학습모듈 원고(hwp/hwpx, 선택)")
    parser.add_argument("--manual", type=float, help="수작업으로 산정한 쪽수 — 주면 오차율을 낸다")
    parser.add_argument("--print", dest="print_pdf", type=Path, help="원고를 한글에서 PDF로 저장한 출력본(선택) — 주면 쪽을 PDF에서 잰다")
    parser.add_argument("--unit-price", type=int, help="원고료 단가(원/쪽). 없으면 예산·정산지침 상한 50,000원")
    parser.add_argument("--contract-pages", type=int, help="계약서(과업지시서)에 적은 원고 분량(매) — 주면 초과분을 빼고 인정")
    parser.add_argument("--exclude-appendix", action="store_true", help="부록을 산정에서 뺀다(기본: 계약서 제13조 4항대로 포함)")
    parser.add_argument("--json", type=Path, help="결과를 이 JSON 파일로도 저장")
    args = parser.parse_args(argv)
    config = replace(DEFAULT_CONFIG, include_appendix=not args.exclude_appendix)
    try:
        result = measure(args.manuscript, previous=args.previous, manual_pages=args.manual, config=config,
                         print_pdf=args.print_pdf, fee_unit=args.unit_price, contract_pages=args.contract_pages)
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
