"""검수 엔진 공용 CLI. 각 엔진의 `python -m ncs_<엔진>`은 이 run_cli를 부른다.

엔진마다 다른 것은 레지스트리와 설정에서 읽는다: 개발계획서 필수 여부는 `Engine.required`,
`--body-section` 유무는 엔진 `CheckConfig`에 `body_section` 필드가 있는지. 저장 경로 선택은
`save_cli_review`(`--out` → 그 폴더, 없으면 DATABASE_URL → DB 이력, 둘 다 없으면 `결과/`).
"""

import argparse
import json
import os
from dataclasses import fields
from pathlib import Path

from .models import ReviewRequest
from .registry import get_engine
from .service import execute_review
from .store import save_cli_review, saved_location


def run_cli(check: str, description: str, argv: list[str] | None = None) -> None:
    engine = get_engine(check)
    config_class = engine.load().CheckConfig
    has_body = "body_section" in {field.name for field in fields(config_class)}
    plan_help = "원고와 개발계획서" if "plan" in engine.required else "원고와 (선택) 개발계획서"

    parser = argparse.ArgumentParser(prog=f"python -m {engine.package}", description=description)
    parser.add_argument("paths", nargs="+", help=f"{plan_help}. 순서 무관, 내용으로 역할 판별")
    parser.add_argument("--manuscript", help="자동 역할 판별 대신 원고로 지정할 입력 경로")
    parser.add_argument("--plan", help="자동 역할 판별 대신 개발계획서로 지정할 입력 경로")
    parser.add_argument("--module-code", default="", help="비우면 원고 파일명에서 추출")
    parser.add_argument("--front-section", type=int, default=0)
    if has_body:
        parser.add_argument("--body-section", type=int, default=1)
    parser.add_argument("--out", help="결과 폴더. 비우면 DATABASE_URL이 있을 때 DB 이력에, 없을 때 '결과' 폴더에 저장")
    args = parser.parse_args(argv)

    roles = {}
    if args.manuscript:
        roles[args.manuscript] = "manuscript"
    if args.plan:
        roles[args.plan] = "plan"
    sections = {"front_section": args.front_section}
    if has_body:
        sections["body_section"] = args.body_section
    try:
        execution = execute_review(
            ReviewRequest(
                paths=tuple(Path(path) for path in args.paths),
                check=check,
                roles=roles,
                module_code=args.module_code,
                config=config_class(**sections),
            )
        )
        result = execution.result
        saved = save_cli_review(execution, args.paths, out=args.out, database_url=os.getenv("DATABASE_URL"))
    except (OSError, ValueError) as error:
        parser.exit(2, f"검수 실행 실패: {error}\n")
    print(json.dumps({"요약": saved.summary, "진단": result.diagnostics}, ensure_ascii=False, indent=2))
    print(f"지적사항 {len(result.findings)}건 · {saved_location(saved)}")
