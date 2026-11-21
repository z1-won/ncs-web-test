"""python -m ncs_suggest 원고.hwp [--json 결과.json]  |  python -m ncs_suggest --sentence "문장" --kind "교수 방법"

원고를 주면 구성별로 AI가 고칠 문장이라고 본 문장과 순위 붙인 정정 후보(최대 5개)·참고 예문을 출력한다. 원고는 고치지 않는다.
AI는 .env의 LLM 설정·반출 승인(LLM_ALLOW_UPLOAD=1)이 있으면 자동으로 부르고, 없으면 이유만 출력한다(규칙으로 대신 판정하지 않음).
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
        out.append(f"    {item['순위']}. {item['문장']}  [{item['출처']}] {' / '.join(item['근거'])}")
    if card["추천 없음"]:
        out.append(f"    {card['추천 없음']}")
    out += [f"    참고 예문({example['유사도']}): {example['문장']}  — {example['자리']}" for example in card["참고 예문"]]
    out += [f"    버린 AI 후보: {dropped['문장']} — {dropped['이유']}" for dropped in card["버린 AI 후보"]]
    return out


def render(result: dict) -> str:
    summary = result["요약"]
    reasons = " · ".join(f"{name} {count}" for name, count in summary["사유별"].items())
    out = [f"[{result['원고']}] 검사 {summary['검사한 문장']}문장 · 고칠 문장 {summary['고칠 문장']}" + (f"({reasons})" if reasons else "")
           + f" · 추천 있음 {summary['추천 있음']} · 추천 없음 {summary['추천 없음']} · 버린 AI 후보 {summary['버린 AI 후보']}"
           + f" · {result['AI']['상태']}"]
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
    parser.add_argument("--json", type=Path, help="결과를 이 JSON 파일로도 저장")
    args = parser.parse_args(argv)
    if bool(args.manuscript) == bool(args.sentence):
        parser.error("원고 경로 또는 --sentence 가운데 하나만 주세요")
    if args.sentence and not args.kind:
        parser.error("--sentence에는 --kind가 필요합니다")
    try:
        if args.sentence:
            result = suggest_sentence(args.sentence, args.kind)
            text = "\n".join(render_card(result) + [f"    {result['AI']}"])
        else:
            result = suggest_manuscript(args.manuscript)
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
