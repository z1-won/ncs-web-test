"""python -m ncs_knowledge 원고.hwpx [개발계획서.hwp] [--module-code LM...] [--out 결과]"""

import argparse
import json
import os
from pathlib import Path

from ncs_service import ReviewRequest, execute_review, save_cli_review, saved_location

from . import CheckConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="F02 필요 지식 ①~⑧ 검수")
    parser.add_argument("paths", nargs="+", help="원고와 (선택) 개발계획서. 순서 무관, 내용으로 역할 판별")
    parser.add_argument("--manuscript", help="자동 역할 판별 대신 원고로 지정할 입력 경로")
    parser.add_argument("--plan", help="자동 역할 판별 대신 개발계획서로 지정할 입력 경로")
    parser.add_argument("--module-code", default="", help="비우면 원고 파일명에서 추출")
    parser.add_argument("--front-section", type=int, default=0)
    parser.add_argument("--body-section", type=int, default=1)
    parser.add_argument("--out", help="결과 폴더. 비우면 DATABASE_URL이 있을 때 DB 이력에, 없을 때 '결과' 폴더에 저장")
    args = parser.parse_args()
    roles = {}
    if args.manuscript:
        roles[args.manuscript] = "manuscript"
    if args.plan:
        roles[args.plan] = "plan"
    try:
        config = CheckConfig(front_section=args.front_section, body_section=args.body_section)
        execution = execute_review(
            ReviewRequest(
                paths=tuple(Path(path) for path in args.paths),
                check="knowledge",
                roles=roles,
                module_code=args.module_code,
                config=config,
            )
        )
        result = execution.result
        saved = save_cli_review(execution, args.paths, out=args.out, database_url=os.getenv("DATABASE_URL"))
    except (OSError, ValueError) as error:
        parser.exit(2, f"검수 실행 실패: {error}\n")
    print(json.dumps({"요약": saved.summary, "진단": result.diagnostics}, ensure_ascii=False, indent=2))
    print(f"지적사항 {len(result.findings)}건 · {saved_location(saved)}")


if __name__ == "__main__":
    main()
