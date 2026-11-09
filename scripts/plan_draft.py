"""개발계획서 초안 만들기(REQ-02-001 '작성'): T01 양식에 NCS 정보를 채운 hwpx를 만든다.

입력은 둘 중 하나:
  python scripts/plan_draft.py --from-plan 기존계획서.hwp[x] --out 초안.hwpx     # 기존 계획서의 NCS(수정 금지) 쪽을 그대로 옮겨 새 양식에
  python scripts/plan_draft.py --spec spec.json --out 초안.hwpx                  # JSON spec(ncs_plan.fill 모듈 docstring 참조)
  python scripts/plan_draft.py --from-ncs 12030202 [--units 01 02] --out 초안.hwpx # 세분류 코드만으로(NCS 목록 + ncs_elements.tsv)
만든 초안은 바로 점검(ncs_plan)에 넣어 결과를 같이 보여 준다(--no-check로 끌 수 있다).
"""

import argparse
import json
from pathlib import Path

from ncs_core import load_document
from ncs_plan import run_review
from ncs_plan.fill import build_plan, spec_from_catalog, spec_from_plan
from ncs_plan.parsers import read_plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-plan", help="NCS 쪽을 옮겨 올 기존 개발계획서(hwp/hwpx)")
    source.add_argument("--spec", help="spec JSON 파일")
    source.add_argument("--from-ncs", help="세분류 코드 8자리 — NCS 목록·요소 표에서 spec을 만든다")
    parser.add_argument("--units", nargs="*", help="--from-ncs에서 일부 능력단위 번호(2자리)만")
    parser.add_argument("--agency", default="", help="--from-ncs에서 개발기관명")
    parser.add_argument("--out", required=True, help="만들 초안 hwpx 경로")
    parser.add_argument("--dump-spec", help="(선택) 읽은 spec을 JSON으로 저장할 경로")
    parser.add_argument("--no-check", action="store_true", help="만든 뒤 ncs_plan 점검을 돌리지 않음")
    args = parser.parse_args()

    if args.from_plan:
        spec = spec_from_plan(read_plan(load_document(args.from_plan).tables))
    elif args.from_ncs:
        spec = spec_from_catalog(args.from_ncs, units=args.units, agency=args.agency)
    else:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if args.dump_spec:
        Path(args.dump_spec).write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_plan(spec))
    print(f"초안 저장: {out} (모듈 {len(spec['모듈'])}개, 요소 {sum(len(m['요소']) for m in spec['모듈'])}개)")
    if args.no_check:
        return
    result = run_review([out])
    for row in result.sheet:
        print(f"  {row['번호']} {row['검수결과']}" + (f" — {row['비고'].splitlines()[0][:100]}" if row["비고"] else ""))


if __name__ == "__main__":
    main()
