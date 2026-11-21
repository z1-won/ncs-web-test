"""batch_review.py 결과(체크포인트)를 기대 판정 표와 대조해 미탐·오탐 후보를 뽑는다.

  python scripts/batch/batch_compare.py --work _batch/20261109_x --expected scripts/batch/batch_expected_테스트데이터.tsv \\
      --baseline "LM2001021701_기타_hwp" --engines position toc overview knowledge colophon --out _batch/20261109_x/대조.md

기대 표(TSV): 경로(root 기준 상대 경로, fnmatch 글로브) · 구성요소 · 번호 · 기대(부적합|적합|판단불가|미검사) · 수정사항 · 비고.
'#'으로 시작하는 줄과 머리 행은 건너뛴다.

대조 결과 세 가지:
  미탐  — 기대가 부적합인데 엔진은 적합(또는 판단불가·오류·미실행). 기대가 판단불가·미검사·적합인 행은 '일치/불일치'로만 적는다.
  오탐 후보 — 기대 표에 그 항목이 없는데 엔진이 부적합이고, 원본(--baseline)도 부적합이 아닌 것. 조작하지 않은 항목이 X가 됐다는 뜻.
            (기대 표의 '부수' 행은 오탐으로 세지 않는다. 원본도 X인 항목은 '원본 자체 X'로 따로 모은다 — 원본 문제인지 규칙 오탐인지 사람이 가른다.)
  원본 자체 X — 원본(조작 전) 원고에서 부적합인 항목.

오차율(요구사항정의서 REQ-02-002 검증 기준과 견줄 값)도 함께 낸다. 세는 법:
  정답이 있는 판정 = ① 기대가 부적합·적합인 행(문서 × 항목) + ② 조작하지 않은 항목 중 원본과 조작본이 모두 적합·부적합으로 판정된 것
                    (정답 = 원본의 판정. 원본을 지정하지 않으면 ②는 세지 않는다).
  틀림 = 미탐(기대 부적합을 잡지 못함) + 오탐(기대 적합인데 부적합, 조작하지 않은 항목이 원본과 다르게 나옴).
  보류 = 정답은 있는데 엔진이 판단불가로 둔 것(기대 적합 행, 조작하지 않은 항목). 틀림에 넣지 않고 따로 센다.
  기대가 판단불가·미검사인 행은 자동 판정 대상이 아니어서 뺀다. 원본 자체 X는 정답을 사람이 정하지 않았으므로 원본 판정을 그대로 정답으로 쓴다
  (원본의 X가 규칙 오탐이면 오차율이 그만큼 낮게 나온 것이다 — 결과에 건수를 함께 적는다).
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "batch"))

from batch_review import ERROR, item_columns, load_results, verdict_of  # noqa: E402
from ncs_core import FAIL, PASS, UNDECIDED  # noqa: E402
from ncs_core.sheet import NOT_CHECKED  # noqa: E402
from ncs_service.registry import ENGINES  # noqa: E402

COLUMNS = ("경로", "구성요소", "번호", "기대", "수정사항", "비고")


def read_expected(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.reader(handle, delimiter="\t"):
            if not raw or raw[0].startswith("#") or raw[0] == COLUMNS[0]:
                continue
            raw += [""] * (len(COLUMNS) - len(raw))
            rows.append(dict(zip(COLUMNS, (v.strip() for v in raw))))
    return rows


def compare(work: Path, expected_rows: list[dict], baseline_id: str | None, engines: set[str]) -> dict:
    docs, results, _facts = load_results(work)
    columns = [c for c in item_columns() if c[0] in engines]
    engine_of = {(comp, no): check for check, comp, no, _, _ in columns}
    verdicts = {d.doc_id: {(comp, no): verdict_of(results[d.doc_id].get(check), no, impl) for check, comp, no, _, impl in columns} for d in docs}
    baseline = next((d for d in docs if baseline_id and (d.doc_id == baseline_id or fnmatch.fnmatch(d.path, baseline_id))), None)
    base_v = verdicts[baseline.doc_id] if baseline else {}

    matched: list[dict] = []           # 기대 행 × 문서
    expected_keys: dict[str, set] = defaultdict(set)  # doc_id → {(구성요소, 번호)} (부수 포함)
    unmatched_patterns = []
    for row in expected_rows:
        key = (row["구성요소"], row["번호"])
        if key not in engine_of:
            continue  # 선택한 엔진의 항목이 아니면 건너뜀
        hits = [d for d in docs if fnmatch.fnmatch(d.path, row["경로"]) or fnmatch.fnmatch(d.path.replace("\\", "/"), row["경로"])]
        if not hits:
            unmatched_patterns.append(row["경로"])
            continue
        for d in hits:
            actual = verdicts[d.doc_id][key]
            expected_keys[d.doc_id].add(key)
            if row["기대"] == FAIL:
                outcome = "일치" if actual == FAIL else ("미탐" if actual in (PASS, NOT_CHECKED) else f"미탐({actual})")
            else:
                outcome = "일치" if actual == row["기대"] else f"불일치({actual})"
            matched.append({"문서": d.doc_id, "경로": d.path, "구성요소": key[0], "번호": key[1], "기대": row["기대"], "실제": actual,
                            "결과": outcome, "수정사항": row["수정사항"], "비고": row["비고"]})

    false_alarms, baseline_fail = [], []
    for d in docs:
        if baseline and d.doc_id == baseline.doc_id:
            baseline_fail = [{"구성요소": comp, "번호": no, "실제": v} for (comp, no), v in verdicts[d.doc_id].items() if v == FAIL]
            continue
        if d.doc_id not in expected_keys:
            continue  # 기대 표에 없는 문서(다른 담당 폴더)는 오탐 집계에서 제외
        for key, v in verdicts[d.doc_id].items():
            if v == FAIL and key not in expected_keys[d.doc_id] and base_v.get(key) != FAIL:
                false_alarms.append({"문서": d.doc_id, "경로": d.path, "구성요소": key[0], "번호": key[1], "원본": base_v.get(key, "없음")})
    errors = [{"문서": d.doc_id, "엔진": c, "오류": r["error"]} for d in docs for c, r in results[d.doc_id].items() if c in engines and not r["ok"]]
    rates = error_rates(matched, {d.doc_id: verdicts[d.doc_id] for d in docs if d.doc_id in expected_keys and not (baseline and d.doc_id == baseline.doc_id)},
                        expected_keys, base_v if baseline else None, [comp for _, comp, _, _, _ in columns])
    return {"docs": len(docs), "baseline": baseline.doc_id if baseline else None, "matched": matched, "false_alarms": false_alarms,
            "baseline_fail": baseline_fail, "errors": errors, "unmatched_patterns": unmatched_patterns, "rates": rates}


def error_rates(matched: list[dict], verdicts: dict[str, dict], expected_keys: dict[str, set], base_v: dict | None,
                components: list[str]) -> list[dict]:
    """구성요소별·전체 오차율 행(모듈 설명의 '세는 법'). base_v가 None이면 조작하지 않은 항목은 세지 않는다."""
    order = list(dict.fromkeys(components))
    tally = {comp: Counter() for comp in order}
    for m in matched:
        if (m["문서"] not in verdicts) or m["기대"] not in (FAIL, PASS):
            continue
        t = tally[m["구성요소"]]
        if m["기대"] == FAIL:
            t["판정"] += 1
            t["기대 부적합"] += 1
            t["미탐"] += m["결과"].startswith("미탐")
        elif m["실제"] in (FAIL, PASS):
            t["판정"] += 1
            t["오탐"] += m["실제"] == FAIL
        else:
            t["보류"] += 1
    for doc_id, items in verdicts.items():
        for (comp, no), actual in items.items():
            if (comp, no) in expected_keys[doc_id] or base_v is None:
                continue
            t = tally[comp]
            if base_v.get((comp, no)) not in (FAIL, PASS):
                t["제외"] += 1      # 원본도 판단불가·미검사 — 정답이 없다
                continue
            if actual in (FAIL, PASS):
                t["판정"] += 1
                t["오탐" if actual == FAIL else "원본과 다른 적합"] += actual != base_v[(comp, no)]
            elif actual == UNDECIDED:
                t["보류"] += 1
    rows = []
    total = Counter()
    for comp in order + ["전체"]:
        t = tally.get(comp, total)
        if comp != "전체":
            total.update(t)
        wrong = t["미탐"] + t["오탐"] + t["원본과 다른 적합"]
        rows.append({"구성요소": comp, "정답이 있는 판정": t["판정"], "틀림": wrong, "미탐": t["미탐"], "오탐": t["오탐"],
                     "원본과 다른 적합": t["원본과 다른 적합"], "보류(판단불가)": t["보류"],
                     "오차율": f"{wrong / t['판정'] * 100:.2f}%" if t["판정"] else "-",
                     "기대 부적합": t["기대 부적합"], "미탐율": f"{t['미탐'] / t['기대 부적합'] * 100:.2f}%" if t["기대 부적합"] else "-",
                     "제외(원본도 판단불가·미검사)": t["제외"]})
    return rows


def _table(rows: list[dict], cols: list[str]) -> list[str]:
    if not rows:
        return ["(없음)"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")).replace("|", "¦").replace("\n", " ") for c in cols) + " |")
    return out


def render(report: dict, engines: list[str]) -> str:
    matched = report["matched"]
    counts = Counter(m["결과"].split("(")[0] for m in matched)
    lines = [f"# 배치 결과 ↔ 기대 판정 대조 (엔진: {', '.join(engines)})", "",
             f"- 문서 {report['docs']}개, 원본(기준) = {report['baseline'] or '지정 안 함'}",
             f"- 기대 행 대조 {len(matched)}건: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
             f"- 오탐 후보 {len(report['false_alarms'])}건, 원본 자체 X {len(report['baseline_fail'])}건, 실행 오류 {len(report['errors'])}건", ""]
    if report["unmatched_patterns"]:
        lines += ["기대 표의 경로와 맞는 문서가 없음: " + ", ".join(sorted(set(report["unmatched_patterns"]))), ""]
    lines += ["## 오차율", "",
              "정답이 있는 판정(기대가 부적합·적합인 행" + (" + 조작하지 않은 항목, 정답 = 원본의 판정" if report["baseline"] else "만. 원본을 지정하지 않아 조작하지 않은 항목은 세지 않음")
              + ") 가운데 틀린 비율. 요구사항정의서 REQ-02-002 기준: 형식·필수항목·코드·명칭 0.5% 이내, 출처·구성·분량 5% 이내, 수행준거–학습목표 대응 6% 이내.", ""]
    lines += _table(report["rates"], ["구성요소", "정답이 있는 판정", "틀림", "미탐", "오탐", "원본과 다른 적합", "보류(판단불가)", "오차율",
                                      "기대 부적합", "미탐율", "제외(원본도 판단불가·미검사)"])
    lines += ["", "오차율은 조작하지 않은 항목까지 넣은 값이고, 미탐율은 조작한 항목(기대 부적합)만 본 값이다. 제외는 원본에서도 판단불가·미검사라 정답이 없는 판정 수다."]
    if report["baseline_fail"]:
        lines += ["", f"원본 자체 부적합 {len(report['baseline_fail'])}건은 사람이 정답을 정하지 않아 원본 판정을 그대로 정답으로 썼다. 규칙 오탐으로 확인되면 그만큼 틀림에 더한다."]
    lines += ["", "## 미탐 (기대 부적합인데 잡지 못함)", ""]
    lines += _table([m for m in matched if m["결과"].startswith("미탐")], ["경로", "구성요소", "번호", "실제", "수정사항", "비고"])
    lines += ["", "## 기대와 다른 판정 (기대가 적합·판단불가·미검사인 행)", ""]
    lines += _table([m for m in matched if m["결과"].startswith("불일치")], ["경로", "구성요소", "번호", "기대", "실제", "수정사항", "비고"])
    lines += ["", "## 오탐 후보 (조작하지 않은 항목이 부적합)", ""]
    lines += _table(report["false_alarms"], ["경로", "구성요소", "번호", "원본"])
    lines += ["", "## 원본 자체 부적합 (원본 문제인지 규칙 오탐인지 확인)", ""]
    lines += _table(report["baseline_fail"], ["구성요소", "번호", "실제"])
    lines += ["", "## 실행 오류", ""]
    lines += _table(report["errors"], ["문서", "엔진", "오류"])
    lines += ["", "## 기대 행 전체", ""]
    lines += _table(matched, ["경로", "구성요소", "번호", "기대", "실제", "결과", "수정사항", "비고"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work", required=True, help="batch_review.py run 의 작업 폴더")
    parser.add_argument("--expected", required=True, help="기대 판정 TSV")
    parser.add_argument("--baseline", help="조작 전 원본 문서의 문서ID 또는 경로 글로브")
    parser.add_argument("--engines", nargs="*", default=list(ENGINES), help="대조할 엔진(check 이름). 기본 전부")
    parser.add_argument("--out", help="마크다운 출력 경로(없으면 표준 출력)")
    args = parser.parse_args()
    unknown = set(args.engines) - set(ENGINES)
    if unknown:
        parser.error(f"모르는 엔진: {sorted(unknown)} (가능: {list(ENGINES)})")
    report = compare(Path(args.work), read_expected(Path(args.expected)), args.baseline, set(args.engines))
    text = render(report, args.engines)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, "utf-8")
        print(f"저장: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
