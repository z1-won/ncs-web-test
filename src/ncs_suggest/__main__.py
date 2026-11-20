"""python -m ncs_suggest 원고.hwp [--json 결과.json] [--ai]  |  python -m ncs_suggest --sentence "문장" --kind "교수 방법"

원고를 주면 구성별로 규정 꼴을 어긴 문장과 순위 붙인 정정 후보(최대 5개)·참고 예문을 출력한다. 원고는 고치지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import KINDS
from .pipeline import suggest_manuscript, suggest_sentence


def render_card(card: dict) -> list[str]:
    out = [f"[{card['번호']}] {card['자리']} ({card['종류']}, {card['상태']}) {card['원문']}"]
    out += [f"    사유: {reason}" for reason in card["사유"]]
    for item in card["후보"]:
        out.append(f"    {item['순위']}. {item['문장']}  [{item['출처']} · 신뢰도 {item['신뢰도']}] {' / '.join(item['근거'])}")
    if card["추천 없음"]:
        out.append(f"    {card['추천 없음']}")
    out += [f"    참고 예문({example['유사도']}): {example['문장']}  — {example['자리']}" for example in card["참고 예문"]]
    return out


def render(result: dict) -> str:
    summary = result["요약"]
    out = [f"[{result['원고']}] 검사 {summary['검사한 문장']}문장 · 규칙 위반 {summary['규칙 위반']} · 표현 다듬기 {summary['표현 다듬기']} · "
           f"추천 있음 {summary['추천 있음']} · 추천 없음 {summary['추천 없음']} · {result['AI']['상태']}"]
    for part in result["구성"]:
        out.append(f"\n== {part['구성']} ({len(part['문장'])})")
        for card in part["문장"]:
            out += render_card(card)
    out += [f"알림: {note}" for note in result["알림"]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncs_suggest", description="원고 문장 정정 후보를 순위와 함께 낸다(REQ-02-004).")
    parser.add_argument("manuscript", nargs="?", type=Path, help="원고(hwp/hwpx)")
    parser.add_argument("--sentence", help="원고 대신 문장 하나를 추천받는다")
    parser.add_argument("--kind", choices=list(KINDS), help="--sentence의 문장 종류")
    parser.add_argument("--ai", action="store_true", help="AI 후보도 묻는다(LLM 설정·반출 승인·허용 목록이 있을 때만 실제 호출)")
    parser.add_argument("--json", type=Path, help="결과를 이 JSON 파일로도 저장")
    args = parser.parse_args(argv)
    if bool(args.manuscript) == bool(args.sentence):
        parser.error("원고 경로 또는 --sentence 가운데 하나만 주세요")
    if args.sentence and not args.kind:
        parser.error("--sentence에는 --kind가 필요합니다")
    try:
        if args.sentence:
            result = suggest_sentence(args.sentence, args.kind, use_llm=args.ai)
            text = "\n".join(render_card(result)) if result["상태"] != "규정에 맞음" else f"규정에 맞음: {result['원문']}"
        else:
            result = suggest_manuscript(args.manuscript, use_llm=args.ai)
            text = render(result)
    except (ValueError, OSError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
