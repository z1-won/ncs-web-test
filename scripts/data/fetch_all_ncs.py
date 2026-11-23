"""NCS 요소·수행준거를 세분류 전체에 대해 미리 받아 둔다 — 개발계획서 작성에서 세분류를 고를 때마다 받아 오지 않게.

  set -a; source .env; set +a                                  # NCS_API_KEY
  python scripts/data/fetch_all_ncs.py                         # 아직 없는 세분류를 코드 순서로, 오늘 한도(기본 9,000번)까지
  python scripts/data/fetch_all_ncs.py --only 20 1203          # 코드가 20 또는 1203으로 시작하는 세분류만(먼저 받고 싶은 분야)
  python scripts/data/fetch_all_ncs.py --dry-run               # 받지 않고 남은 세분류 수와 호출 수만

받은 것은 기준정보 폴더(--data, 기본 '기준정보')의 ncs_elements.tsv에 세분류 단위로 쓴다(ncs_core.ncs_fetch.save_duty — 웹 서버가 쓰는 곳과 같다).
이미 받아 둔 세분류(패키지 표 또는 기준정보 폴더)는 건너뛰므로, 한도에서 멈춘 뒤 다음 날 같은 명령을 다시 돌리면 이어서 받는다(--refresh는 다시 받는다).

호출 수: 세분류 하나에 1 + 능력단위 수 × 2번. NCS 목록 전체(세분류 1,086개, 능력단위 13,141개)는 약 27,400번이고,
공공데이터포털의 하루 한도가 10,000번이라 사흘에 나눠 받아야 한다. --budget은 그날 쓸 호출 수(웹 서버가 쓸 몫을 남기려고 기본 9,000).
한 세분류를 받다가 실패하면 그 세분류는 쓰지 않고 넘어간다(반만 받은 세분류를 남기지 않는다). 한도 초과 응답이나 연속 실패 5번이면 멈춘다.
웹 서버가 켜져 있으면 받는 동안 화면에서 [NCS에서 다시 받아 오기]를 누르지 않는다(두 쪽이 같은 파일을 고쳐 쓴다). 끝나면 서버를 다시 켠다.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ncs_core import ncs_catalog, ncs_fetch, refdata  # noqa: E402
from ncs_core.ncs_api import NcsApiError  # noqa: E402

DAILY_LIMIT = 10000
DEFAULT_BUDGET = 9000
MAX_FAILS_IN_A_ROW = 5
QUOTA_WORDS = ("LIMITED_NUMBER_OF_SERVICE_REQUESTS", "한도", "트래픽", "HTTP 429")
LOG_FILE = "ncs_fetch_all.log"


def calls_for(unit_count: int) -> int:
    return 1 + 2 * unit_count


def plan(catalog, only: list[str], refresh: bool) -> tuple[list[tuple[str, str, int]], int]:
    """받을 세분류 [(코드, 이름, 호출 수)]와 건너뛸(이미 있는) 세분류 수. 코드 순서."""
    todo, have = [], 0
    for duty in sorted(catalog.subclasses):
        if only and not any(duty.startswith(prefix) for prefix in only):
            continue
        sub = catalog.subclass(duty)
        if not refresh and catalog.units_with_detail(duty):
            have += 1
            continue
        todo.append((duty, sub.name, calls_for(len(sub.units))))
    return todo, have


def run(only: list[str] | None = None, *, budget: int = DEFAULT_BUDGET, refresh: bool = False, dry_run: bool = False, sleep: float = 0.0,
        out=print) -> dict:
    """→ {'받음': [코드…], '실패': [(코드, 까닭)…], '남음': 수, '남은 호출': 수, '쓴 호출': 수, '멈춘 까닭': str}."""
    catalog = ncs_catalog.catalog()
    if catalog is None:
        raise SystemExit("NCS 목록(ncs_units.tsv)이 없습니다")
    todo, have = plan(catalog, only or [], refresh)
    total_calls = sum(cost for _, _, cost in todo)
    out(f"받을 세분류 {len(todo)}개(호출 약 {total_calls:,}번), 이미 있는 세분류 {have}개. 오늘 쓸 호출 {budget:,}번")
    result = {"받음": [], "실패": [], "남음": len(todo), "남은 호출": total_calls, "쓴 호출": 0, "멈춘 까닭": ""}
    if dry_run or not todo:
        result["멈춘 까닭"] = "받지 않고 세기만 함" if dry_run else "받을 세분류가 없음"
        return result
    if not ncs_fetch.can_fetch():
        raise SystemExit("NCS_API_KEY와 기준정보 폴더(--data)가 필요합니다. 먼저 `set -a; source .env; set +a`를 실행해 주세요")
    fails_in_a_row = 0
    for index, (duty, name, cost) in enumerate(todo, 1):
        if result["쓴 호출"] + cost > budget:
            result["멈춘 까닭"] = f"오늘 쓸 호출 {budget:,}번에 닿음"
            break
        try:
            units = ncs_fetch.fetch_duty(duty)
            ncs_fetch.save_duty(duty, units)
        except NcsApiError as error:
            result["쓴 호출"] += cost          # 실패해도 호출은 나갔을 수 있다 — 넉넉히 센다
            message = str(error)
            if any(word in message for word in QUOTA_WORDS):
                result["멈춘 까닭"] = f"NCS가 한도 초과로 답함: {message}"
                break
            result["실패"].append((duty, message))
            fails_in_a_row += 1
            out(f"[{index}/{len(todo)}] {duty} {name}: 실패 — {message}")
            if fails_in_a_row >= MAX_FAILS_IN_A_ROW:
                result["멈춘 까닭"] = f"연속 {MAX_FAILS_IN_A_ROW}번 실패(연결이나 인증키를 확인해 주세요)"
                break
            continue
        fails_in_a_row = 0
        result["쓴 호출"] += cost
        result["받음"].append(duty)
        result["남음"] -= 1
        result["남은 호출"] -= cost
        out(f"[{index}/{len(todo)}] {duty} {name}: 능력단위 {len(units)}개, 요소 {sum(len(unit['elements']) for unit in units)}개 (오늘 호출 {result['쓴 호출']:,}번)")
        if sleep:
            time.sleep(sleep)
    else:
        result["멈춘 까닭"] = "끝까지 돌았음"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", default=[], metavar="코드", help="이 숫자로 시작하는 세분류만(대분류 2자리 ~ 세분류 8자리, 여러 개)")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help=f"오늘 쓸 호출 수(기본 {DEFAULT_BUDGET:,}, 하루 한도 {DAILY_LIMIT:,})")
    parser.add_argument("--refresh", action="store_true", help="이미 받아 둔 세분류도 다시 받는다")
    parser.add_argument("--dry-run", action="store_true", help="받지 않고 남은 세분류 수와 호출 수만 센다")
    parser.add_argument("--sleep", type=float, default=0.0, help="세분류 사이에 쉬는 초")
    parser.add_argument("--data", default="기준정보", help="기준정보 폴더(웹 서버의 --data와 같게, 기본 '기준정보')")
    args = parser.parse_args(argv)
    if any(not prefix.isdigit() or len(prefix) > 8 for prefix in args.only):
        parser.error("--only에는 숫자 8자리 이하의 코드를 적습니다")
    refdata.set_data_dir(args.data)
    ncs_catalog.reload()
    result = run(args.only, budget=args.budget, refresh=args.refresh, dry_run=args.dry_run, sleep=args.sleep)
    days = -(-result["남은 호출"] // max(args.budget, 1))
    print(f"\n받은 세분류 {len(result['받음'])}개, 실패 {len(result['실패'])}개, 남은 세분류 {result['남음']}개"
          f"(호출 약 {result['남은 호출']:,}번, 하루 {args.budget:,}번이면 {days}일). 멈춘 까닭: {result['멈춘 까닭']}")
    for duty, message in result["실패"]:
        print(f"  실패 {duty}: {message}")
    if not args.dry_run and (result["받음"] or result["실패"]):
        folder = refdata.data_dir()
        with open(folder / LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"{datetime.now().isoformat(timespec='seconds')}\t받음 {len(result['받음'])}\t실패 {len(result['실패'])}\t남음 {result['남음']}\t"
                      f"호출 {result['쓴 호출']}\t{result['멈춘 까닭']}\t실패 코드: {' '.join(duty for duty, _ in result['실패'])}\n")
    return 0 if not result["실패"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
