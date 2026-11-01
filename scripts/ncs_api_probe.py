"""공공데이터포털 'NCS 국가직무능력표준 정보'(B490007/ncsInfo) API의 실제 호출 경로·응답 모양을 알아내는 탐색 스크립트.

포털 상세 페이지에는 오퍼레이션 13개(NCS 분류체계·능력단위·능력단위요소 …)만 있고 각 호출 경로가 없다.
이 스크립트는 후보 경로를 하나씩 호출해 상태 코드와 응답 머리 부분을 보여 준다. 인증키는 .env의 NCS_API_KEY에서 읽고
출력에는 가린다(KEY=****).

  set -a; source .env; set +a
  python scripts/ncs_api_probe.py                # 기본 후보 탐색
  python scripts/ncs_api_probe.py getNcsList      # 경로를 직접 지정(여러 개 가능)
  python scripts/ncs_api_probe.py --duty 12030204 getCompUnitList   # dutyCd를 붙여 호출
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://apis.data.go.kr/B490007/ncsInfo"
# 포털 '상세기능'의 실제 경로(2026-11 확인): 분류체계 / 직무정보 / 능력단위 / 능력단위요소 / 수행준거 KSA / 직무 직책(수준) 등
CANDIDATES = ["ncsCdInfo", "ncsDutyInfo", "ncsCompeUnitInfo", "ncsCompeUnitFactrInfo", "ncsClposInfo"]


def call(path: str, key: str, duty: str | None, rows: int = 3, unit: str | None = None) -> tuple[int | str, str]:
    params = {"serviceKey": key, "returnType": "json", "numOfRows": rows, "pageNo": 1}
    if duty:
        params["dutyCd"] = duty
    if unit:
        params["compUnitCd"] = unit
    url = f"{BASE}/{path}" if path else BASE
    full = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(full, headers={"User-Agent": "ncs-f02-review/0.1", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(3000).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(600).decode("utf-8", "replace")
    except Exception as error:  # noqa: BLE001
        return type(error).__name__, str(error)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="직접 시험할 경로(없으면 기본 후보)")
    parser.add_argument("--duty", help="dutyCd(세분류 8자리)를 붙여 호출")
    parser.add_argument("--unit", help="compUnitCd(능력단위 번호 2자리)를 붙여 호출")
    args = parser.parse_args()
    key = os.getenv("NCS_API_KEY")
    if not key:
        sys.exit("NCS_API_KEY가 없습니다 (.env에 넣고 set -a; source .env; set +a)")
    for path in args.paths or CANDIDATES:
        status, body = call(path, key, args.duty, unit=args.unit)
        body = body.replace(key, "****").replace(urllib.parse.quote(key, safe=""), "****").replace("\n", " ")
        print(f"[{status}] {BASE}/{path}  duty={args.duty} unit={args.unit}\n    {body[:1500]}\n")


if __name__ == "__main__":
    main()
