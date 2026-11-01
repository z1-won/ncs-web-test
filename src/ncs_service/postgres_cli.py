"""PostgreSQL 스키마 준비 및 기존 결과 폴더 이관 명령."""

import argparse
import json
import os
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .postgres import import_review, migrate, reporting_for
from .registry import ENGINES, get_engine


def import_directory(dsn: str, directory: Path) -> bool | None:
    for check in ENGINES:
        name = reporting_for(check).REPORT_NAME
        suffix = f"_{name}_00_요약.json"
        matches = list(directory.glob(f"*{suffix}"))
        if not matches:
            continue
        if len(matches) != 1:
            raise ValueError(f"요약 파일이 중복되었습니다: {directory}")
        summary_file = matches[0]
        code = summary_file.name.removesuffix(suffix)

        def read(tail):
            return json.loads((directory / f"{code}_{name}_{tail}.json").read_text(encoding="utf-8"))

        diagnostics = read("진단")
        checklist = read("전체")
        sheet_file = directory / f"{code}_{name}_검수확인서.json"
        if sheet_file.exists():
            sheet = read("검수확인서")
        else:
            sheet = import_module(get_engine(check).package + ".sheet").sheet(checklist)
            diagnostics.setdefault("warnings", []).append(
                "과거 결과에 검수확인서 파일이 없어 현재 표 형식으로 재구성했습니다"
            )
        diagnostics["inputs"] = {
            role: Path(path).name if path else None
            for role, path in diagnostics.get("inputs", {}).items()
        }
        return import_review(
            dsn, run_id=str(uuid5(NAMESPACE_URL, f"ncs-review-import:{directory.name}")),
            created_at=datetime.fromtimestamp(summary_file.stat().st_mtime, timezone.utc),
            check=check, module_code=code, summary=json.loads(summary_file.read_text(encoding="utf-8")),
            sheet=sheet, diagnostics=diagnostics,
            findings=read("지적사항"), checklist=checklist,
        )
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="PostgreSQL 검수 이력 관리")
    parser.add_argument("command", choices=("migrate", "import"))
    parser.add_argument("directory", nargs="?", type=Path)
    args = parser.parse_args()
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL 환경 변수가 필요합니다")
    applied = migrate(dsn)
    if args.command == "migrate":
        print("PostgreSQL 스키마 준비 완료" + (f" (적용: {', '.join(applied)})" if applied else " (변경 없음)"))
        return
    if args.directory is None or not args.directory.is_dir():
        parser.error("import에는 기존 결과 폴더 경로가 필요합니다")
    imported = skipped = unknown = 0
    for directory in sorted(path for path in args.directory.iterdir() if path.is_dir()):
        try:
            result = import_directory(dsn, directory)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            parser.exit(1, f"이관 실패: {directory}: {error}\n")
        if result is True:
            imported += 1
        elif result is False:
            skipped += 1
        else:
            unknown += 1
    print(f"이관 {imported}건, 기존 이력 {skipped}건, 인식 불가 {unknown}건")


if __name__ == "__main__":
    main()
