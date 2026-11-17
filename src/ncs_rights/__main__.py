"""python -m ncs_rights 원고.hwpx [서류.hwp …] [--first-review 날짜] [--submitted 날짜] [--transfer-author] [--transfer-maker]
                        [--portrait unknown|none|submitted] [--pledge] [--print 출력본.pdf] [--xlsx 현황표.xlsx]"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .check import Options
from .report import build_xlsx
from .service import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="권리 증빙 제출 현황 점검(REQ-02-014)")
    parser.add_argument("manuscript", type=Path, help="원고(hwpx 또는 hwp)")
    parser.add_argument("forms", type=Path, nargs="*", help="제출 서류(작성된 한글 양식)")
    parser.add_argument("--first-review", type=date.fromisoformat, help="1차 검토일 YYYY-MM-DD")
    parser.add_argument("--submitted", type=date.fromisoformat, help="수록 현황 목록 제출일 YYYY-MM-DD")
    parser.add_argument("--transfer-author", action="store_true", help="집필자 양도 동의서 제출됨")
    parser.add_argument("--transfer-maker", action="store_true", help="제작자 양도 동의서 제출됨")
    parser.add_argument("--portrait", choices=("unknown", "none", "submitted"), default="unknown", help="초상권: 확인 안 함 / 인물 없음 / 동의서 제출")
    parser.add_argument("--pledge", action="store_true", help="생성형 AI 결과물 집필자 서약서 제출됨")
    parser.add_argument("--print", dest="print_copy", type=Path, help="출력본 PDF — 그림이 놓인 쪽을 읽어 결과물 현황의 쪽수와 대조")
    parser.add_argument("--xlsx", type=Path, help="현황표를 이 파일로 저장")
    args = parser.parse_args(argv)
    try:
        report = run(args.manuscript, args.forms, Options(
            first_review_on=args.first_review, submitted_on=args.submitted, transfer_author=args.transfer_author,
            transfer_maker=args.transfer_maker, portrait=args.portrait, pledge=args.pledge), print_copy=args.print_copy)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if args.xlsx:
        args.xlsx.write_bytes(build_xlsx(report))
    print(json.dumps({key: report[key] for key in ("요약", "기한", "지적사항", "알림", "안내")}, ensure_ascii=False, indent=2))
    return 0 if report["요약"]["판정"] == "적합" else 1


if __name__ == "__main__":
    sys.exit(main())
