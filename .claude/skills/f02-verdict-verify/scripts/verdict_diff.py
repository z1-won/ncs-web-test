"""배치 작업 폴더 두 개(수정 전·후)를 대조해 '판정 변화' 표를 만든다.

  python .claude/skills/f02-verdict-verify/scripts/verdict_diff.py \\
      --before _workspace/batch_before --after _workspace/batch_after [--engines toc overview] [--remarks] [--out 경로.md]

입력은 scripts/batch/batch_review.py run 이 만든 체크포인트 폴더다. 두 폴더에 모두 있는 문서의 54개 항목 판정을 비교해
달라진 것만 PR 템플릿의 '판정 변화' 표(원고 | 체크 항목 | 이전 | 이후) 모양으로 낸다.

--remarks 를 주면 수정 후 비고를 함께 적는다. 비고에는 원고 문구가 들어 있으므로 _workspace 안에서 볼 때만 쓰고,
PR·커밋에 붙일 표는 --remarks 없이 만든다.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "batch"))

from batch_review import item_columns, load_results, remark_of, verdict_of  # noqa: E402
from ncs_service.registry import ENGINES  # noqa: E402


def diff(before: Path, after: Path, engines: set[str]) -> dict:
    docs_b, results_b, _ = load_results(before)
    docs_a, results_a, _ = load_results(after)
    ids_b, ids_a = {d.doc_id for d in docs_b}, {d.doc_id for d in docs_a}
    columns = [c for c in item_columns() if c[0] in engines]
    changes, same = [], 0
    for doc in docs_a:
        if doc.doc_id not in ids_b:
            continue
        for check, component, no, _text, implemented in columns:
            old = verdict_of(results_b[doc.doc_id].get(check), no, implemented)
            new = verdict_of(results_a[doc.doc_id].get(check), no, implemented)
            if old == new:
                same += 1
                continue
            changes.append({"원고": doc.doc_id, "체크 항목": f"{component} {no}", "이전": old, "이후": new,
                            "비고(이후)": remark_of(results_a[doc.doc_id].get(check), no)})
    return {"compared": len(ids_a & ids_b), "same": same, "changes": changes,
            "only_before": sorted(ids_b - ids_a), "only_after": sorted(ids_a - ids_b)}


def render(report: dict, engines: list[str], remarks: bool) -> str:
    changes = report["changes"]
    kinds = Counter(f"{c['이전']}→{c['이후']}" for c in changes)
    lines = [f"# 판정 변화 (엔진: {', '.join(engines)})", "",
             f"- 대조한 문서 {report['compared']}개, 변화 없는 항목 {report['same']}건, **변화 {len(changes)}건**"]
    if kinds:
        lines.append("- 유형: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    if report["only_before"] or report["only_after"]:
        lines.append(f"- 한쪽에만 있는 문서: 이전만 {len(report['only_before'])}개, 이후만 {len(report['only_after'])}개 — 같은 --root 로 돌렸는지 확인")
    lines.append("")
    cols = ["원고", "체크 항목", "이전", "이후"] + (["비고(이후)"] if remarks else [])
    if not changes:
        lines.append("(판정 변화 없음)")
    else:
        lines += ["| " + " | ".join(cols) + " |", "|" + " ---- |" * len(cols)]
        for c in changes:
            lines.append("| " + " | ".join(str(c[k]).replace("|", "¦").replace("\n", " ") for k in cols) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", required=True, help="수정 전 코드로 돌린 배치 작업 폴더")
    parser.add_argument("--after", required=True, help="수정 후 코드로 돌린 배치 작업 폴더")
    parser.add_argument("--engines", nargs="*", default=list(ENGINES), help="대조할 엔진(check 이름). 기본 전부")
    parser.add_argument("--remarks", action="store_true", help="수정 후 비고를 함께 적는다(원고 문구 포함 — 내부 확인용)")
    parser.add_argument("--out", help="마크다운 출력 경로(없으면 표준 출력)")
    args = parser.parse_args()
    unknown = set(args.engines) - set(ENGINES)
    if unknown:
        parser.error(f"모르는 엔진: {sorted(unknown)} (가능: {list(ENGINES)})")
    text = render(diff(Path(args.before), Path(args.after), set(args.engines)), args.engines, args.remarks)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, "utf-8")
        print(f"저장: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
