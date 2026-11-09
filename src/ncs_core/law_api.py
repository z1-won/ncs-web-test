"""법제처 국가법령정보 공동활용(open.law.go.kr) Open API 호출 — 법령명의 현행 여부·연혁.

인증키(OC)는 환경 변수 LAW_API_OC(회원 ID). 신청 시 등록한 IP에서만 호출된다. 검수 서버는 호출하지 않고, 운용 전에
scripts/data/build_law_names.py로 법령명 표(data/law_names.tsv)를 만들어 두면 law_catalog가 그것을 읽는다.

  https://www.law.go.kr/DRF/lawSearch.do?OC=…&target=law&type=XML&query=법령명        현행 법령 목록
  https://www.law.go.kr/DRF/lawSearch.do?OC=…&target=lsHistory&type=XML&query=법령명  법령 연혁 목록(폐지·개정 이력 포함)
응답은 <LawSearch><law>…</law></LawSearch> 꼴이고 항목 필드는 법령명한글·법령ID·공포일자·시행일자·제개정구분명·현행연혁코드 등.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from xml.etree import ElementTree as ET

BASE_URL = "https://www.law.go.kr/DRF/lawSearch.do"
FIELDS = ("법령명한글", "법령약칭명", "법령ID", "법령일련번호", "공포일자", "공포번호", "시행일자", "제개정구분명", "현행연혁코드", "법령구분명", "소관부처명")


class LawApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class LawRecord:
    name: str            # 법령명한글
    law_id: str          # 법령ID(법령이 바뀌어도 유지되는 식별자)
    serial: str          # 법령일련번호(개정본마다 다름)
    promulgated: str     # 공포일자 YYYYMMDD
    effective: str       # 시행일자
    revision: str        # 제개정구분명(제정/일부개정/전부개정/폐지/타법폐지/타법개정 …)
    current: str         # 현행연혁코드(현행/연혁)
    kind: str            # 법령구분명(법률/대통령령/총리령/부령 …)
    abbreviation: str    # 법령약칭명

    @property
    def repealed(self) -> bool:
        return "폐지" in (self.revision or "")


def _oc() -> str:
    oc = os.getenv("LAW_API_OC")
    if not oc:
        raise LawApiError("LAW_API_OC 환경 변수가 없습니다 (.env에 넣고 set -a; source .env; set +a)")
    return oc


def _get(params: dict, timeout: float = 20.0) -> str:
    query = {"OC": _oc(), "type": "XML", **params}
    url = f"{BASE_URL}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "ncs-f02-review/0.1", "Accept": "application/xml"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        raise LawApiError(f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:200]}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise LawApiError(f"연결 실패: {error}") from None
    if "사용자 정보 검증" in body or "<html" in body[:200].lower():
        raise LawApiError("인증 실패 — OC(회원 ID) 또는 등록 IP를 확인하세요: " + re.sub(r"\s+", " ", body)[:200])
    return body


def _parse(xml: str) -> list[LawRecord]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise LawApiError(f"응답을 XML로 읽지 못함: {error}; 머리: {xml[:200]!r}") from None
    out = []
    for item in root.iter("law"):
        get = lambda tag: (item.findtext(tag) or "").strip()  # noqa: E731
        out.append(LawRecord(get("법령명한글"), get("법령ID"), get("법령일련번호"), get("공포일자"), get("시행일자"),
                             get("제개정구분명"), get("현행연혁코드"), get("법령구분명"), get("법령약칭명")))
    return out


def search(name: str, *, display: int = 20) -> list[LawRecord]:
    """현행 법령 목록에서 이름으로 찾는다(부분 일치)."""
    return _parse(_get({"target": "law", "query": name, "display": display}))


def history(name: str, *, display: int = 50) -> list[LawRecord]:
    """법령 연혁 목록(폐지·개정 이력)에서 이름으로 찾는다."""
    return _parse(_get({"target": "lsHistory", "query": name, "display": display}))


def raw(params: dict) -> str:
    """탐색용 — 응답 원문."""
    return _get(params)
