"""도표·표·그래프 생성(REQ-02-006 ①)을 실제 생성형 AI로 돌려 본다 — 문단 파일을 읽어 명세 후보와 검사 결과를 찍고, 통과한 후보를 PNG로 쓴다.

  source .venv/bin/activate; set -a; source .env; set +a
  PYTHONPATH=src python scripts/probe/diagram_probe.py docs/examples/diagram_paragraphs.example.txt --out 결과/도표
  선택: --criterion "수행준거 글"  --kind diagram|graph|sequence|cycle|structure|compare|table|bar|line|pie  --width 150
        --report 결과/판정.tsv   후보마다 한 줄(문단, 종류, 검사 결과와 까닭, 빠진 듯한 내용, 명세, 그림 파일) + 사람이 채울 '사람 판정'·'메모' 칸
        --tally 결과/판정.tsv    사람이 채운 판정을 센다(생성형 AI를 부르지 않는다). 판정 값: 맞음 | 틀림 | 그릴 것 없음
  실제 원고의 문단은 scripts/probe/manuscript_paragraphs.py로 뽑는다.
문단 파일은 빈 줄로 나눈 문단 여러 개여도 된다(문단마다 따로 묻는다). 예시 파일은 순서, 순환, 구성, 비교, 표, 그릴 것이 없는 문단, 막대 그래프, 원 그래프 하나씩이다. 문단은 외부로 전송된다(LLM_ALLOW_UPLOAD=1이어야 돈다).
끝에 문단 수, 후보 수, 통과한 후보 수, 통과한 후보가 하나라도 있는 문단 수, 떨어진 까닭의 개수를 찍는다 — 근거 검사가 너무 빡빡한지 느슨한지 보는 데 쓴다.
검사를 통과한 후보가 문단의 뜻과 맞는지(칸의 자리, 그릴 것이 없는 문단에 그렸는지)는 규칙이 보지 못한다 — --report의 '사람 판정' 칸을 사람이 채우고 --tally로 센다.
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from ncs_aiimage import propose, render


HEAD = ["문단 번호", "문단", "후보", "종류", "검사", "까닭", "빠진 듯한 내용", "명세", "그림 파일", "사람 판정", "메모"]
VERDICTS = ("맞음", "틀림", "그릴 것 없음")


def tally(path: Path) -> None:
    """사람이 채운 판정 TSV를 센다. 검사를 통과한 후보만 본다(떨어진 후보는 화면에서 쓰이지 않는다)."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = [row for row in csv.DictReader(file, delimiter="\t")]
    passed = [row for row in rows if row.get("검사") == "통과"]
    judged = [row for row in passed if (row.get("사람 판정") or "").strip() in VERDICTS]
    counts = Counter((row["사람 판정"].strip(), row["종류"]) for row in judged)
    print(f"통과한 후보 {len(passed)}개 가운데 판정한 것 {len(judged)}개")
    for verdict in VERDICTS:
        total = sum(count for (name, _), count in counts.items() if name == verdict)
        kinds = ", ".join(f"{kind} {count}" for (name, kind), count in sorted(counts.items()) if name == verdict)
        print(f"  {verdict}: {total}" + (f" ({kinds})" if kinds else ""))
    if judged:
        wrong = sum(count for (name, _), count in counts.items() if name != "맞음")
        print(f"  검사를 통과했지만 쓸 수 없는 후보의 비율: {wrong}/{len(judged)} = {wrong / len(judged):.1%}")
    unknown = sorted({(row.get("사람 판정") or "").strip() for row in passed} - set(VERDICTS) - {""})
    if unknown:
        print(f"  세지 않은 판정 값: {', '.join(unknown)} (쓸 수 있는 값: {' | '.join(VERDICTS)})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paragraphs", type=Path, nargs="?")
    parser.add_argument("--criterion", default="")
    parser.add_argument("--kind", default="")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--width", type=float, default=150.0)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--tally", type=Path, default=None)
    args = parser.parse_args()
    if args.tally:
        tally(args.tally)
        return
    if args.paragraphs is None:
        parser.error("문단 파일이 필요합니다(예시: docs/examples/diagram_paragraphs.example.txt)")
    if not args.paragraphs.is_file():
        parser.error(f"문단 파일이 없습니다: {args.paragraphs} (예시: docs/examples/diagram_paragraphs.example.txt)")
    texts = [part.strip() for part in re.split(r"\n\s*\n", args.paragraphs.read_text(encoding="utf-8")) if part.strip()]
    totals: Counter = Counter()
    can_draw = True
    report: list[list] = []
    for number, text in enumerate(texts, 1):
        result = propose(text, args.criterion, kind=args.kind)
        totals.update(문단=1, 후보=len(result["candidates"]), 통과=result["usable"], **{"통과 후보가 있는 문단": 1 if result["usable"] else 0})
        if not result["candidates"]:
            report.append([number, text, "", "", "후보 없음", result["note"], "", "", "", "", ""])
        print(f"\n[{number}] {text[:50]}… → {result['note']}" + (f" / {result['reason']}" if result["reason"] else ""))
        for index, entry in enumerate(result["candidates"], 1):
            if entry["ok"]:
                print(f"  후보 {index} 통과: {json.dumps(entry['spec'], ensure_ascii=False)}")
                for missing in entry["omissions"]:
                    totals.update(["빠진 듯한 내용"])
                    print(f"    빠진 듯: {missing['reason']} — {missing['sentence'][:60]}")
                name = ""
                if args.out and can_draw:
                    try:
                        png = render(entry["spec"], width_mm=args.width).png
                    except (ImportError, RuntimeError) as error:      # Pillow가 없거나(가상 환경 밖) 한글 글꼴이 없음 — 후보는 계속 찍는다
                        can_draw = False
                        print(f"  그림은 쓰지 않습니다: {error} (가상 환경에서 돌리세요: source .venv/bin/activate)")
                    else:
                        args.out.mkdir(parents=True, exist_ok=True)
                        name = f"{number:02d}_{index}_{entry['spec']['kind']}.png"
                        (args.out / name).write_bytes(png)
                report.append([number, text, index, entry["spec"]["kind"], "통과", "", " / ".join(m["reason"] for m in entry["omissions"]),
                               json.dumps(entry["spec"], ensure_ascii=False), name, "", ""])
                continue
            reasons = [entry["error"]] if entry["error"] else [problem["reason"] for problem in entry["problems"]]
            totals.update("모양" if entry["error"] else re.sub(r"\s*'.*", "", reason) for reason in reasons)
            print(f"  후보 {index} 떨어짐: {' / '.join(reasons)}")
            if entry["spec"]:
                print(f"    {json.dumps(entry['spec'], ensure_ascii=False)}")
            report.append([number, text, index, entry["spec"]["kind"] if entry["spec"] else "", "떨어짐", " / ".join(reasons), "",
                           json.dumps(entry["spec"], ensure_ascii=False) if entry["spec"] else "", "", "", ""])
    print("\n합계:", dict(totals))
    if totals["문단"]:
        print(f"통과한 후보가 하나라도 있는 문단: {totals['통과 후보가 있는 문단']}/{totals['문단']} = {totals['통과 후보가 있는 문단'] / totals['문단']:.1%}"
              + (f", 후보 통과율 {totals['통과']}/{totals['후보']} = {totals['통과'] / totals['후보']:.1%}" if totals["후보"] else ""))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("w", encoding="utf-8-sig", newline="") as file:      # 엑셀에서 바로 열리게 BOM을 붙인다
            writer = csv.writer(file, delimiter="\t")
            writer.writerow(HEAD)
            writer.writerows([[" ".join(str(cell).split()) for cell in row] for row in report])
        print(f"판정표: {args.report} — '사람 판정' 칸에 {' | '.join(VERDICTS)} 가운데 하나를 적고 --tally로 셉니다")


if __name__ == "__main__":
    main()
