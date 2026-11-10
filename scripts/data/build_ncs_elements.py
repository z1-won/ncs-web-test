"""능력단위요소·수행준거 표(src/ncs_core/data/ncs_elements.tsv) 만들기 — 공공데이터포털 B490007/ncsInfo.

  set -a; source .env; set +a                       # NCS_API_KEY
  python3 scripts/data/build_ncs_elements.py --duty 12030202 [--duty 20010217 …]   # 세분류 단위(능력단위 전부)
  python3 scripts/data/build_ncs_elements.py --duty 12030202 --unit 01 02             # 일부 능력단위만
  python3 scripts/data/build_ncs_elements.py --from-plan 계획서.hwpx                   # API 대신 기존 계획서의 'NCS(수정 금지)' 쪽에서
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


def clean(value: str) -> str:
    """표 한 칸에 들어갈 글 — API 문장 안의 줄바꿈·탭을 공백으로(줄바꿈이 섞이면 다음 줄이 다른 행으로 읽힌다)."""
    return " ".join(str(value or "").split())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duty", action="append", default=[], help="세분류 코드 8자리(여러 번 가능)")
    parser.add_argument("--from-plan", action="append", default=[], help="기존 개발계획서(hwp/hwpx) — API가 비어 있는 세분류의 NCS 쪽을 옮겨 적는다")
    parser.add_argument("--unit", nargs="*", default=None, help="능력단위 번호 2자리(비우면 세분류 전부)")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--table", default=str(TABLE))
    args = parser.parse_args()

    table = Path(args.table)
    if not table.exists():
        table.write_text(HEADER, encoding="utf-8")
    if not args.duty and not args.from_plan:
        sys.exit("--duty 또는 --from-plan 중 하나는 있어야 합니다")
    known = set() if args.refresh else set(read_elements(table))
    added = 0
    with table.open("a", encoding="utf-8") as handle:
        for path in args.from_plan:
            from ncs_core import load_document
            from ncs_plan.parsers import read_plan

            data = read_plan(load_document(path).tables)
            levels = {}
            try:
                from ncs_core.ncs_catalog import catalog
                cat = catalog()
                levels = {m["코드"][:10]: cat.level(m["코드"]) for m in data["모듈"]} if cat else {}
            except Exception:  # noqa: BLE001 — 수준은 보조 정보
                pass
            for module in data["모듈"]:
                if not module["코드"] or module["코드"][:10] in known:
                    continue
                duty = module["코드"][:8]
                for element in module["요소"]:
                    handle.write("\t".join(clean(v) for v in [duty, module["코드"], module["명칭"], str(levels.get(module["코드"][:10]) or ""),
                                                              module["정의"], element["코드"], element["명칭"], CRITERIA_SEP.join(element["수행준거"])]) + "\n")
                added += 1
                print(f"{module['코드']} {module['명칭']}: 요소 {len(module['요소'])}개, 수행준거 {sum(len(e['수행준거']) for e in module['요소'])}개 (계획서 {Path(path).name})")
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
                    handle.write("\t".join(clean(v) for v in [duty, unit.code, unit.name, str(unit.level or ""), unit.definition,
                                                              f"{unit.code}.{no}", names.get(no, ""), CRITERIA_SEP.join(sentences.get(no, []))]) + "\n")
                added += 1
                print(f"{unit.code} {unit.name}: 요소 {len(names)}개, 수행준거 {sum(len(v) for v in sentences.values())}개")
    print(f"능력단위 {added}개 추가 → {table}")


if __name__ == "__main__":
    main()
