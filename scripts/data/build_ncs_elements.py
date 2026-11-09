"""능력단위요소·수행준거 표(src/ncs_core/data/ncs_elements.tsv) 만들기 — 공공데이터포털 B490007/ncsInfo.

  set -a; source .env; set +a                       # NCS_API_KEY
  python3 scripts/data/build_ncs_elements.py --duty 12030202 [--duty 20010217 …]   # 세분류 단위(능력단위 전부)
  python3 scripts/data/build_ncs_elements.py --duty 12030202 --unit 01 02             # 일부 능력단위만
호출: ncsCompeUnitInfo(능력단위·정의·수준) + 능력단위마다 ncsKsaInfo(요소별 수행준거). 세분류 하나에 능력단위 수 + 1번 호출.
이미 표에 있는 능력단위는 건너뛴다(--refresh로 다시). 열: 세분류 \\t 능력단위코드 \\t 능력단위명 \\t 수준 \\t 정의 \\t 요소코드 \\t 요소명 \\t 수행준거(‖ 구분)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ncs_core.ncs_api import NcsApiError, criteria, elements, units  # noqa: E402
from ncs_core.ncs_catalog import CRITERIA_SEP, ELEMENTS_FILE, read_elements  # noqa: E402

TABLE = ROOT / "src" / "ncs_core" / "data" / ELEMENTS_FILE
HEADER = ("# NCS 능력단위요소·수행준거 — 공공데이터포털 B490007/ncsInfo(ncsCompeUnitInfo·ncsKsaInfo). 갱신: scripts/data/build_ncs_elements.py\n"
          "# 세분류코드\t능력단위코드\t능력단위명\t수준\t정의\t요소코드\t요소명\t수행준거(‖ 구분)\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duty", action="append", required=True, help="세분류 코드 8자리(여러 번 가능)")
    parser.add_argument("--unit", nargs="*", default=None, help="능력단위 번호 2자리(비우면 세분류 전부)")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--table", default=str(TABLE))
    args = parser.parse_args()

    table = Path(args.table)
    if not table.exists():
        table.write_text(HEADER, encoding="utf-8")
    known = set() if args.refresh else set(read_elements(table))
    added = 0
    with table.open("a", encoding="utf-8") as handle:
        for duty in args.duty:
            try:
                unit_list = units(duty)
            except NcsApiError as error:
                print(f"[오류] {duty}: {error}")
                continue
            for unit in unit_list:
                unit_no = unit.code[8:10]
                if args.unit and unit_no not in args.unit:
                    continue
                if unit.code[:10] in known:
                    continue
                try:
                    names = {e["no"]: e["name"] for e in elements(duty, unit_no) if e["code"] == unit.code}
                    sentences = criteria(duty, unit_no)
                except NcsApiError as error:
                    print(f"[오류] {unit.code}: {error}")
                    continue
                for no in sorted(set(names) | set(sentences)):
                    handle.write("\t".join([duty, unit.code, unit.name, str(unit.level or ""), unit.definition.replace("\t", " "),
                                            f"{unit.code}.{no}", names.get(no, ""), CRITERIA_SEP.join(sentences.get(no, []))]) + "\n")
                added += 1
                print(f"{unit.code} {unit.name}: 요소 {len(names)}개, 수행준거 {sum(len(v) for v in sentences.values())}개")
    print(f"능력단위 {added}개 추가 → {table}")


if __name__ == "__main__":
    main()
