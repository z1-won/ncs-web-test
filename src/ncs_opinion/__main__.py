"""python -m ncs_opinion 최종원고.hwp 1차의견서.pdf 2차의견서.pdf [--print 출력본.pdf] [--previous 반영전원고.hwp] [--json 결과.json] [--labels 정답.json]

검토의견서의 의견별 반영 여부 후보(반영 후보·미반영 후보·확인 필요·조치 불필요)와 근거 문단을 출력한다(REQ-02-003).
판정은 LLM이 한다 — .env의 LLM 설정·반출 승인(LLM_ALLOW_UPLOAD=1)이 있으면 자동으로 부르고, 없으면 모든 의견이 '확인 필요'와 이유다.
--labels: {의견 번호: "반영"|"미반영"} JSON을 주면 판단 오차율(기준 6% 이내)을 함께 낸다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import error_rate, review


def render(result: dict) -> str:
    """사람이 읽는 표(터미널용)."""
    out = [f"[{result['원고']}] 검토의견서 반영 여부 — LLM: {result['LLM']}"]
    for sheet in result["의견서"]:
        out.append(f"  의견서 {sheet['파일']} ({sheet['차수'] or '차수 모름'}, {sheet['학습모듈명']}) 의견 {sheet['의견 수']}개")
    summary = result["요약"]
    out.append("요약: " + " / ".join(f"{k} {v}" for k, v in summary.items()))
    for row in result["의견"]:
        where = " ".join(filter(None, [row["차수"], row["구분"], row["구성"], f"{row['쪽']}쪽" if row["쪽"] else ""]))
        out.append(f"{row['번호']:>3}. [{row['판정']}] ({where}) [{row['유형']}] {row['의견'][:80]}")
        for evidence in row["근거"][:2]:
            page = f", 출력본 {evidence['출력본 쪽']}쪽" if evidence.get("출력본 쪽") else ""
            out.append(f"       근거({evidence['위치']}{page}): {evidence['문단'][:90]}")
        for note in row["비고"]:
            out.append(f"       - {note}")
        if row["집필자 확인"]:
            out.append(f"       ? {row['집필자 확인']}")
        if row["수정 제안"]:
            out.append(f"       → 수정 제안: {row['수정 제안']}")
    out += [f"알림: {note}" for note in result["알림"]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncs_opinion", description="검토의견서 반영 여부를 검토한다(REQ-02-003).")
    parser.add_argument("manuscript", type=Path, help="의견을 반영한 최종 원고(hwp/hwpx)")
    parser.add_argument("opinions", type=Path, nargs="+", help="검토의견서(PDF·hwp·hwpx), 1차·2차 여러 개")
    parser.add_argument("--rounds", nargs="+", help="의견서 차수를 순서대로(예: 1차 2차) — 없으면 의견서 제목에서 읽음")
    parser.add_argument("--print", dest="print_pdf", type=Path, help="최종 원고 출력본 PDF(근거 쪽 표시, 선택)")
    parser.add_argument("--previous", type=Path, help="의견 반영 전 원고(초고본·완성본, 선택)")
    parser.add_argument("--json", type=Path, help="결과를 이 JSON 파일로도 저장")
    parser.add_argument("--labels", type=Path, help="사람이 정한 정답 {번호: 반영|미반영} JSON — 오차율을 낸다")
    args = parser.parse_args(argv)
    try:
        result = review(args.opinions, args.manuscript, rounds=args.rounds, print_pdf=args.print_pdf, previous=args.previous)
        if args.labels:
            labels = {int(k): v for k, v in json.loads(args.labels.read_text(encoding="utf-8")).items()}
            result["오차율"] = error_rate(result["의견"], labels)
    except ValueError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(render(result))
    if "오차율" in result:
        rate = result["오차율"]
        print(f"오차율: {rate['오차율']} ({rate['기준']}, {rate['결과']}) — 판정 {rate['판정 수']}, 틀림 {rate['틀림']}, 보류 {rate['보류(확인 필요)']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
