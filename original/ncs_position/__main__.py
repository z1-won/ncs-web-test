"""python -m ncs_position --plan ... --manuscript ... --out 결과"""

import argparse
import json

from . import run_review, save_results


def main():
    parser = argparse.ArgumentParser(description="F02 위치 검수 (v1.1 판정 정책 유지)")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--manuscript", required=True)
    parser.add_argument("--module-code", default="")
    parser.add_argument("--out", default="결과")
    args = parser.parse_args()
    result = run_review(args.plan, args.manuscript, module_code=args.module_code)
    saved = save_results(result, args.out)
    print(json.dumps(saved.summary, ensure_ascii=False, indent=2))
    print(f"지적사항 {len(result.findings)}건 · {saved.zip_path}")


if __name__ == "__main__":
    main()
