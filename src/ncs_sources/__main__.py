"""python -m ncs_sources <원고.hwpx> [--out 폴더] [--module-code LM…]

REQ-02-008 저작권 검토: 출처 목록(그림·표·본문 출처 줄·참고 자료)과 규칙 점검 결과를 JSON·CSV로 낸다.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .service import review_sources

COLUMNS = ("구분", "위치", "그림·표", "출처 원문", "출처 종류", "저작자", "연도", "URL", "확인 일자", "쪽", "공공누리", "인용 모듈",
           "AI 표기", "판정", "문제", "수정 제안")


def write_csv(result: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in result["rows"]:
            s = r["출처"] or {}
            problems = " / ".join(f"{k}: {r['비고'].get(k, '')}" for k, v in r["체크"].items() if v in ("X", "△"))
            w.writerow([r["구분"], r["region_path"], r["그림·표"], r["원고"] if r["출처"] else "", s.get("종류"), s.get("저작자"),
                        s.get("연도"), s.get("URL"), s.get("확인 일자"), s.get("쪽"), s.get("공공누리"), s.get("인용 모듈"),
                        (r["AI 표기"] or {}).get("원문"), r["판정"], problems, r["수정 제안"]])
        for e in result["references"]["entries"]:
            w.writerow(["참고 자료", "참고 자료", None, e["항목"], "참고 자료", e["저작자"], e["연도"], None, None, None, None, None, None, None, None, None])


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ncs_sources", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manuscript")
    parser.add_argument("--out", default="결과/출처검토")
    parser.add_argument("--module-code", default="")
    args = parser.parse_args(argv)
    result = review_sources(Path(args.manuscript), module_code=args.module_code)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(args.manuscript).stem
    (out / f"{stem}_출처검토.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_csv(result, out / f"{stem}_출처목록.csv")
    print(f"{result['summary']} → {out}")


if __name__ == "__main__":
    main()
