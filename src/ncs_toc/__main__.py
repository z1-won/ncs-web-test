"""python -m ncs_toc 원고.hwpx [개발계획서.hwpx] [--module-code LM...] [--out 결과]"""

import argparse
import json

from . import CheckConfig, run_review, save_results


def main() -> None:
    parser = argparse.ArgumentParser(description="F02 차례 ①·③·④·⑤·⑥ 검수")
    parser.add_argument("paths", nargs="+", help="원고와 (선택) 개발계획서. 순서 무관, 내용으로 역할 판별")
    parser.add_argument("--manuscript", help="자동 역할 판별 대신 원고로 지정할 입력 경로")
    parser.add_argument("--plan", help="자동 역할 판별 대신 개발계획서로 지정할 입력 경로")
    parser.add_argument("--module-code", default="", help="비우면 원고 파일명에서 추출")
    parser.add_argument("--front-section", type=int, default=0)
    parser.add_argument("--body-section", type=int, default=1)
    parser.add_argument("--out", default="결과")
    args = parser.parse_args()
    roles = {}
    if args.manuscript:
        roles[args.manuscript] = "manuscript"
    if args.plan:
        roles[args.plan] = "plan"
    try:
        config = CheckConfig(front_section=args.front_section, body_section=args.body_section)
        result = run_review(args.paths, roles=roles, module_code=args.module_code, config=config)
        saved = save_results(result, args.out)
    except (OSError, ValueError) as error:
        parser.exit(2, f"검수 실행 실패: {error}\n")
    print(json.dumps({"요약": saved.summary, "진단": result.diagnostics}, ensure_ascii=False, indent=2))
    print(f"지적사항 {len(result.findings)}건 · {saved.zip_path}")


if __name__ == "__main__":
    main()
