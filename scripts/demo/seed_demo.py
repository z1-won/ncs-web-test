"""시연용 계정과 세분류 건을 만든다(REQ-02-007 세분류 건 흐름). 여러 번 돌려도 된다 — 이미 있는 계정과 건은 건드리지 않는다.

    DATABASE_URL=postgresql://… python scripts/demo/seed_demo.py --password "시연용 비밀번호"
    DATABASE_URL=postgresql://… python scripts/demo/seed_demo.py --password "…" --subclass 12030202 --year 2026

만드는 것:
- 계정 여섯: demo-editor(에디터), demo-author·demo-author2(집필진), demo-krivet(직능연), demo-reviewer(검토진), demo-committee(위원)
- 세분류 건 하나(기본: 12030202 객실관리, 올해, 기존개선). 권은 NCS 목록의 학습모듈 전부, 앞의 두 권에 집필진을 한 명씩 붙인다.
원고는 넣지 않는다 — 시연은 개발계획서와 초고본을 올리는 데서 시작한다(끝에 순서를 찍어 준다).
비밀번호는 명령 줄에서 받는다. 저장소에 적어 두지 않는다. 로그인 화면에 시연 계정 표를 띄우려면 같은 값을 .env의 NCS_DEMO_PASSWORD에 둔다(시연 서버만). 이미 있는 계정의 비밀번호는 --reset-password를 줄 때만 바꾼다.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

ACCOUNTS = (
    ("demo-editor", "김에디터", "editor", "에디팅기관"),
    ("demo-author", "이집필", "author", "개발기관"),
    ("demo-author2", "박집필", "author", "개발기관"),
    ("demo-krivet", "정직능", "krivet", "직능연"),
    ("demo-reviewer", "최검토", "reviewer", "검토진"),
    ("demo-committee", "한위원", "committee", "소위원회"),
)
STEPS = """
시연 순서(세분류 건 화면 /cases)
 1. demo-author: 내 할 일의 '개발계획서'를 열어 계획서(hwp, hwpx)를 올리고 제출
 2. demo-editor: 그 문서로 개발계획서 점검 실행 → 완료(대신 기록)
 3. demo-author: 자기 권을 열어 초고본을 올리고 제출
 4. demo-editor: 이 판본으로 검수 실행 → 메모를 적고 보완 요청
 5. demo-author: 보완 요청 메모를 보고 고친 원고를 다시 제출
 6. demo-editor: 검수 다시 실행 → 완료. 권이 1차 검토로 넘어간다
 7. demo-author: 1차 검토에 제출 → demo-reviewer: 판정할 원고를 받고 판정 도착을 적는다
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="시연용 계정과 세분류 건 만들기")
    parser.add_argument("--password", required=True, help="시연 계정 여섯의 비밀번호(8자 이상)")
    parser.add_argument("--subclass", default="12030202", help="세분류 코드 8자리(기본 12030202 객실관리)")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--improvement", default="기존개선")
    parser.add_argument("--reset-password", action="store_true", help="이미 있는 시연 계정의 비밀번호도 바꾼다")
    args = parser.parse_args()
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL이 필요합니다", file=sys.stderr)
        return 2

    from ncs_core.ncs_catalog import catalog
    from ncs_service.auth import accounts
    from ncs_service.workflow import cases
    from ncs_service.postgres import migrate

    migrate(dsn)
    existing = {account["login"]: account for account in accounts.list_accounts(dsn)}
    for login, name, role, org in ACCOUNTS:
        if login in existing:
            if args.reset_password:
                accounts.set_password(dsn, login, args.password)
            print(f"계정 있음: {login}" + (" (비밀번호 바꿈)" if args.reset_password else ""))
        else:
            existing[login] = accounts.create_account(dsn, login=login, name=name, role=role, org=org, password=args.password)
            print(f"계정 만듦: {login} ({name}, {accounts.ROLES[role]})")

    editor = existing["demo-editor"]
    found = next((case for case in cases.list_cases(dsn, editor) if case["subclass"] == args.subclass and case["year"] == args.year), None)
    if found:
        print(f"건 있음: {found['name'] or found['subclass']} {found['year']}년")
        case_id = found["id"]
    else:
        listing = catalog()
        subclass = listing.subclass(args.subclass) if listing else None
        if subclass is None:
            print(f"NCS 목록에 없는 세분류 코드입니다: {args.subclass}", file=sys.stderr)
            return 2
        case_id = cases.create_case(dsn, subclass=args.subclass, year=args.year, improvement=args.improvement, account=editor, name=subclass.name,
                                    volumes=[{"module_code": "LM" + unit.code, "title": unit.name} for unit in subclass.units])
        print(f"건 만듦: {subclass.name} {args.year}년, {len(subclass.units)}권")
    case = cases.get_case(dsn, case_id, editor)
    for volume, login in zip(case["volumes"], ("demo-author", "demo-author2")):
        if volume["author"] is None:
            cases.assign_author(dsn, case_id, volume["id"], existing[login]["id"], account=editor)
            print(f"담당 정함: {volume['title'] or volume['module_code']} → {login}")
    print(STEPS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
