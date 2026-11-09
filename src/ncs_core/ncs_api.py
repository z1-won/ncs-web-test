"""공공데이터포털 '한국산업인력공단_국가직무능력표준 정보'(B490007/ncsInfo) 조회.

인증키는 환경 변수 NCS_API_KEY. 네트워크가 막힌 곳(검수 서버)에서는 호출하지 않고, 운용 전에 scripts/data/build_ncs_levels.py로
능력단위 수준 표(data/ncs_levels.tsv)를 만들어 두고 ncs_catalog가 그것을 읽는다. 일일 트래픽 10,000건.

응답(returnType=json): {"data": [...], "dataInfo": {"code": "000", "message": "정상", "totalPage": n, "pageNo": "1", "totCnt": m}}
  /ncsCompeUnitInfo?dutyCd=12030204 → data[]: dutyCd, ncsClCd(1203020401_23v3), compUnitCd(01), compUnitName("01.연회 판촉"),
                                     compUnitDef, compUnitLevel(4)
  /ncsCompeUnitFactrInfo?dutyCd=…&compUnitCd=01 → 능력단위요소: compUnitFactrNo, compUnitFactrName("1.연회 행사 고객사 분류하기")
  /ncsKsaInfo?dutyCd=…&compUnitCd=01 → 요소별 수행준거·지식·기술·태도 한 줄씩: compUnitFactrNo, compUnitFactrName,
                                      gbnCd/gbnName("수행준거"|"지식"|"기술"|"태도"), gbnVal("1.호텔의 객실 유형에 따라 … 구분 할 수 있다.")
오류는 XML(OpenAPI_ServiceResponse/cmmMsgHeader/errMsg)로 온다.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE_URL = "https://apis.data.go.kr/B490007/ncsInfo"
PAGE_SIZE = 100
NUMBERED = re.compile(r"^\d{1,2}\.\s*")


def _text(value) -> str:
    """응답 문자열 정리 — HTML 엔티티(&amp; 등)를 풀고 앞뒤 공백 제거."""
    return html.unescape(str(value or "")).strip()


class NcsApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApiUnit:
    duty: str        # 세분류 8자리
    code: str        # 1203020401_23v3
    name: str        # 연회 판촉 (앞 '01.' 제거)
    level: int | None
    definition: str


def _key() -> str:
    key = os.getenv("NCS_API_KEY")
    if not key:
        raise NcsApiError("NCS_API_KEY 환경 변수가 없습니다 (.env에 넣고 set -a; source .env; set +a)")
    return key


def _get(path: str, params: dict, timeout: float = 20.0) -> dict:
    query = {"serviceKey": _key(), "returnType": "json", **params}
    url = f"{BASE_URL}/{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "ncs-f02-review/0.1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        raise NcsApiError(f"HTTP {error.code} {path}: {_error_message(body)}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise NcsApiError(f"{path} 연결 실패: {error}") from None
    if body.lstrip().startswith("<"):
        raise NcsApiError(f"{path}: {_error_message(body)}")
    payload = json.loads(body)
    info = payload.get("dataInfo") or {}
    if str(info.get("code", "000")) != "000":
        raise NcsApiError(f"{path}: {info.get('code')} {info.get('message')}")
    return payload


def _error_message(xml: str) -> str:
    m = re.search(r"<errMsg>(.*?)</errMsg>.*?<returnAuthMsg>(.*?)</returnAuthMsg>", xml, re.S)
    return f"{m.group(1)} — {m.group(2)}" if m else xml[:200]


def _pages(path: str, params: dict) -> list[dict]:
    rows, page = [], 1
    while True:
        payload = _get(path, {**params, "numOfRows": PAGE_SIZE, "pageNo": page})
        data = payload.get("data") or []
        if isinstance(data, dict):  # ncsClposInfo처럼 묶음으로 오는 응답
            return [data]
        rows += data
        total_pages = int((payload.get("dataInfo") or {}).get("totalPage") or 1)
        if page >= total_pages or not data:
            return rows
        page += 1


def units(duty: str) -> list[ApiUnit]:
    """세분류(8자리)의 현행 능력단위 — 코드·명칭·수준·정의."""
    out = []
    for row in _pages("ncsCompeUnitInfo", {"dutyCd": duty[:8]}):
        level = row.get("compUnitLevel")
        out.append(ApiUnit(row.get("dutyCd", duty[:8]), row["ncsClCd"], NUMBERED.sub("", _text(row.get("compUnitName"))),
                           int(level) if level not in (None, "") else None, _text(row.get("compUnitDef"))))
    return sorted(out, key=lambda u: u.code)


def elements(duty: str, unit_no: str | None = None) -> list[dict]:
    """능력단위요소 — [{'code': 1203020401_23v3, 'no': 1, 'name': '연회 행사 고객사 분류하기'}]."""
    params = {"dutyCd": duty[:8]}
    if unit_no:
        params["compUnitCd"] = unit_no
    return [{"code": r["ncsClCd"], "no": int(r.get("compUnitFactrNo") or 0), "name": NUMBERED.sub("", _text(r.get("compUnitFactrName")))}
            for r in _pages("ncsCompeUnitFactrInfo", params)]


def ksa(duty: str, unit_no: str | None = None) -> list[dict]:
    """요소별 수행준거·지식·기술·태도 — [{'code', 'no', 'name', 'kind', 'text'}] (kind: 수행준거/지식/기술/태도, text는 머리 번호 제거)."""
    params = {"dutyCd": duty[:8]}
    if unit_no:
        params["compUnitCd"] = unit_no
    return [{"code": r["ncsClCd"], "no": int(r.get("compUnitFactrNo") or 0), "name": NUMBERED.sub("", _text(r.get("compUnitFactrName"))),
             "kind": _text(r.get("gbnName")), "text": NUMBERED.sub("", _text(r.get("gbnVal")))}
            for r in _pages("ncsKsaInfo", params)]


def criteria(duty: str, unit_no: str) -> dict[int, list[str]]:
    """능력단위 하나의 수행준거 — {요소 번호: ['1.1 …', '1.2 …']} (계획서 표기대로 '요소번호.연번 ' 머리를 붙인다)."""
    out: dict[int, list[str]] = {}
    for row in ksa(duty, unit_no):
        if row["kind"] == "수행준거" and row["text"]:
            out.setdefault(row["no"], []).append(row["text"])
    return {no: [f"{no}.{i} {text}" for i, text in enumerate(texts, 1)] for no, texts in out.items()}
