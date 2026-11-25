"""도표·표 생성(REQ-02-006 ①)을 실제 생성형 AI로 돌려 본다 — 문단 파일을 읽어 명세 후보와 검사 결과를 찍고, 통과한 후보를 PNG로 쓴다.

  source .venv/bin/activate; set -a; source .env; set +a
  PYTHONPATH=src python scripts/probe/diagram_probe.py docs/examples/diagram_paragraphs.example.txt --out 결과/도표
  선택: --criterion "수행준거 글"  --kind sequence|cycle|structure|compare|table  --width 150
문단 파일은 빈 줄로 나눈 문단 여러 개여도 된다(문단마다 따로 묻는다). 예시 파일은 순서, 순환, 구성, 비교, 표, 그릴 것이 없는 문단 하나씩이다. 문단은 외부로 전송된다(LLM_ALLOW_UPLOAD=1이어야 돈다).
끝에 문단 수, 후보 수, 통과한 후보 수, 떨어진 까닭의 개수를 찍는다 — 근거 검사가 너무 빡빡한지 느슨한지 보는 데 쓴다.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from ncs_aiimage import propose, render


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paragraphs", type=Path)
    parser.add_argument("--criterion", default="")
    parser.add_argument("--kind", default="")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--width", type=float, default=150.0)
    args = parser.parse_args()
    if not args.paragraphs.is_file():
        parser.error(f"문단 파일이 없습니다: {args.paragraphs} (예시: docs/examples/diagram_paragraphs.example.txt)")
    texts = [part.strip() for part in re.split(r"\n\s*\n", args.paragraphs.read_text(encoding="utf-8")) if part.strip()]
    totals: Counter = Counter()
    can_draw = True
    for number, text in enumerate(texts, 1):
        result = propose(text, args.criterion, kind=args.kind)
        totals.update(문단=1, 후보=len(result["candidates"]), 통과=result["usable"])
        print(f"\n[{number}] {text[:50]}… → {result['note']}" + (f" / {result['reason']}" if result["reason"] else ""))
        for index, entry in enumerate(result["candidates"], 1):
            if entry["ok"]:
                print(f"  후보 {index} 통과: {json.dumps(entry['spec'], ensure_ascii=False)}")
                for missing in entry["omissions"]:
                    totals.update(["빠진 듯한 내용"])
                    print(f"    빠진 듯: {missing['reason']} — {missing['sentence'][:60]}")
                if args.out and can_draw:
                    try:
                        png = render(entry["spec"], width_mm=args.width).png
                    except (ImportError, RuntimeError) as error:      # Pillow가 없거나(가상 환경 밖) 한글 글꼴이 없음 — 후보는 계속 찍는다
                        can_draw = False
                        print(f"  그림은 쓰지 않습니다: {error} (가상 환경에서 돌리세요: source .venv/bin/activate)")
                        continue
                    args.out.mkdir(parents=True, exist_ok=True)
                    (args.out / f"{number:02d}_{index}_{entry['spec']['kind']}.png").write_bytes(png)
                continue
            reasons = [entry["error"]] if entry["error"] else [problem["reason"] for problem in entry["problems"]]
            totals.update("모양" if entry["error"] else re.sub(r"\s*'.*", "", reason) for reason in reasons)
            print(f"  후보 {index} 떨어짐: {' / '.join(reasons)}")
            if entry["spec"]:
                print(f"    {json.dumps(entry['spec'], ensure_ascii=False)}")
    print("\n합계:", dict(totals))


if __name__ == "__main__":
    main()
