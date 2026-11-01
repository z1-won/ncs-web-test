"""NCS API로 능력단위 수준 표(src/ncs_core/data/ncs_levels.tsv)를 만든다. 개요 ④(선수학습 능력단위 수준)가 쓴다.

  set -a; source .env; set +a            # NCS_API_KEY
  python scripts/build_ncs_levels.py 12030204 20010217          # 세분류 코드 직접
  python scripts/build_ncs_levels.py --from-catalog              # ncs_units.tsv의 세분류 전부(1,086건 ≈ 1,086회 호출, 일일 한도 10,000)
  python scripts/build_ncs_levels.py --from-catalog --refresh    # 이미 있는 세분류도 다시 받음
  python scripts/build_ncs_levels.py --from-csv 능력단위목록.csv     # NCS 포털 '능력단위 목록' CSV(분류번호,명칭,수준,훈련시간; cp949)로 한 번에

세분류 단위로 이어받는다(이미 표에 있는 세분류는 건너뜀). 출력: 세분류코드  능력단위코드  능력단위명  수준  훈련시간
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ncs_core import ncs_api  # noqa: E402
from ncs_core.ncs_catalog import LEVELS_FILE, Catalog, read_levels  # noqa: E402

OUT = ROOT / "src" / "ncs_core" / "data" / LEVELS_FILE
HEADER = "# NCS 능력단위 수준·훈련시간 — NCS 포털 능력단위 목록 CSV 또는 공공데이터포털 B490007/ncsInfo/ncsCompeUnitInfo. 갱신: scripts/build_ncs_levels.py\n# 세분류코드\t능력단위코드\t능력단위명\t수준\t훈련시간\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("duties", nargs="*", help="세분류 코드 8자리(또는 모듈 코드)")
    parser.add_argument("--from-catalog", action="store_true", help="ncs_units.tsv의 세분류 전부")
    parser.add_argument("--refresh", action="store_true", help="이미 받은 세분류도 다시 받음")
    parser.add_argument("--from-csv", type=Path, help="NCS 포털 능력단위 목록 CSV(분류번호,명칭,수준,훈련시간)")
    parser.add_argument("--sleep", type=float, default=0.2, help="호출 간격(초)")
    args = parser.parse_args()

    if args.from_csv:
        import csv
        raw = args.from_csv.read_bytes()
        text = next(raw.decode(enc) for enc in ("utf-8-sig", "cp949") if _decodes(raw, enc))
        rows = list(csv.reader(text.splitlines()))
        header, body = rows[0], rows[1:]
        if header[:3] != ["분류번호", "명칭", "수준"]:
            parser.exit(2, f"예상 밖의 CSV 머리: {header}\n")
        existing = {r[0][:10]: {"duty": r[0][:8], "code": r[0], "name": r[1].strip(), "level": int(r[2]) if r[2].strip() else None,
                                "hours": r[3].strip() if len(r) > 3 else ""} for r in body if r and r[0]}
        _write(existing)
        return

    duties = [d.replace("LM", "")[:8] for d in args.duties]
    if args.from_catalog:
        units_file = OUT.with_name("ncs_units.tsv")
        if not units_file.is_file():
            parser.exit(2, "ncs_units.tsv가 없습니다 (scripts/build_ncs_catalog.py 먼저)\n")
        duties += sorted(Catalog(units_file).subclasses)
    duties = list(dict.fromkeys(duties))
    if not duties:
        parser.exit(2, "세분류 코드를 주거나 --from-catalog를 쓰세요\n")

    existing = read_levels(OUT) if OUT.is_file() else {}
    done = {row["duty"] for row in existing.values()}
    todo = [d for d in duties if args.refresh or d not in done]
    print(f"대상 {len(duties)}개 세분류, 호출 {len(todo)}개 (이미 있음 {len(duties) - len(todo)})")
    failed = []
    for i, duty in enumerate(todo, 1):
        try:
            units = ncs_api.units(duty)
        except ncs_api.NcsApiError as error:
            failed.append((duty, str(error)))
            print(f"  {i}/{len(todo)} {duty} 실패: {error}", file=sys.stderr)
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in str(error) or "SERVICE_KEY" in str(error):
                break
            continue
        existing = {k: v for k, v in existing.items() if v["duty"] != duty}
        for u in units:
            existing[u.code[:10]] = {"duty": duty, "code": u.code, "name": u.name, "level": u.level, "hours": ""}
        print(f"  {i}/{len(todo)} {duty} 능력단위 {len(units)}개")
        time.sleep(args.sleep)
    _write(existing)
    if failed:
        print(f"실패 {len(failed)}개 — 다시 실행하면 이어받습니다", file=sys.stderr)


def _decodes(raw: bytes, encoding: str) -> bool:
    try:
        raw.decode(encoding)
        return True
    except UnicodeDecodeError:
        return False


def _write(existing: dict) -> None:
    lines = [HEADER.rstrip("\n").replace("갱신:", f"{date.today().isoformat()} 갱신:")]
    for key in sorted(existing):
        row = existing[key]
        lines.append(f"{row['duty']}\t{row['code']}\t{row['name']}\t{row['level'] if row['level'] is not None else ''}\t{row.get('hours', '')}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"저장: {OUT} (능력단위 {len(existing)}개, 세분류 {len({r['duty'] for r in existing.values()})}개)")


if __name__ == "__main__":
    main()
