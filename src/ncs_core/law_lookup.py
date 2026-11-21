"""법령명의 현행 여부를 법제처에서 조회해 판정하고(judge), 점검 중에 표에 없는 법령명을 그 자리에서 조회해 기준정보 폴더에 쌓는다(ensure).

판정: 현행 목록에 같은 이름 → 현행 / 연혁에만 있고 제개정구분이 폐지 → 폐지 / 연혁의 법령ID로 현행 이름이 다르면 → 명칭변경 /
아무 데도 없음 → 미검색 / 연혁 서비스를 못 쓰면 → 현행목록없음(폐지·명칭 변경·오기 중 하나).
scripts/data/build_law_names.py(패키지 표를 미리 채우는 길)도 같은 judge를 쓴다.

법제처로 나가는 것은 법령 이름뿐이다(문서 본문은 보내지 않는다). 인증(LAW_API_OC)과 쓸 곳(기준정보 폴더)이 둘 다 있을 때만 조회한다.
"""

from __future__ import annotations

import os
import threading
from datetime import date, timedelta

from . import law_catalog
from .law_api import LawApiError, history, search
from .law_catalog import LAW_FILE, LawEntry, normalize
from .refdata import overlay_path

HEADER = ("# 법령명 표 — 점검 중에 법제처 Open API(open.law.go.kr)로 조회한 결과. ncs_core.law_lookup이 덧붙인다.\n"
          "# 표기\t정식명칭\t법령ID\t시행일자\t제개정구분\t상태\t현행명칭\t조회일\n")
MAX_AGE_DAYS = 30        # 이보다 오래된 조회 결과는 다시 조회한다(그사이 폐지·명칭 변경이 있었을 수 있다)
MAX_LOOKUPS = 30         # 문서 하나에서 새로 조회하는 법령명 수의 상한(점검이 한없이 길어지지 않게)
MAX_FAILURES = 2         # 연달아 이만큼 실패하면 그만둔다(연결이 안 되는 곳에서 이름마다 시간 초과를 기다리지 않게)
_lock = threading.Lock()


def judge(name: str) -> tuple[str, str, str, str, str, str]:
    """→ (정식명칭, 법령ID, 시행일자, 제개정구분, 상태, 현행명칭)"""
    key = normalize(name)
    current = [r for r in search(name) if normalize(r.name) == key or normalize(r.abbreviation) == key]
    if current:
        r = sorted(current, key=lambda x: x.effective)[-1]
        return r.name, r.law_id, r.effective, r.revision, "현행", r.name
    try:
        past = [r for r in history(name) if normalize(r.name) == key]
    except LawApiError:
        # 연혁 서비스를 못 쓰면 '현행 목록에 없음'까지만 안다(폐지·명칭 변경·오기 중 무엇인지는 사람이 확인)
        return "", "", "", "", "현행목록없음", ""
    if not past:
        return "", "", "", "", "미검색", ""
    last = sorted(past, key=lambda x: (x.promulgated, x.serial))[-1]
    if last.repealed:
        return last.name, last.law_id, last.effective, last.revision, "폐지", ""
    # 같은 법령ID의 현행 이름을 찾는다(명칭 변경)
    renamed = [r for r in search(last.name[:6]) if r.law_id == last.law_id and normalize(r.name) != key]
    if renamed:
        return last.name, last.law_id, last.effective, last.revision, "명칭변경", renamed[0].name
    return last.name, last.law_id, last.effective, last.revision, "연혁만", ""


def can_lookup() -> bool:
    return bool(os.getenv("LAW_API_OC")) and overlay_path(LAW_FILE) is not None


def is_stale(entry: LawEntry, today: date | None = None) -> bool:
    """조회일이 MAX_AGE_DAYS보다 오래됐는가. 조회일을 읽지 못하면 오래된 것으로 본다."""
    try:
        checked = date.fromisoformat(entry.checked.strip())
    except ValueError:
        return True
    return (today or date.today()) - checked > timedelta(days=MAX_AGE_DAYS)


def ensure(names: list[str]) -> dict | None:
    """names 가운데 표에 없거나 조회한 지 오래된 법령명을 법제처에서 조회해 기준정보 폴더의 표에 덧붙인다.
    조회할 수 없는 환경이면 None. 아니면 {'조회': [이름…], '실패': [이름…], '남김': 상한 때문에 조회하지 않은 수, '오류': 첫 오류 글 또는 None}."""
    if not can_lookup():
        return None
    catalog = law_catalog.law_catalog()
    wanted = []
    for name in dict.fromkeys(n.strip() for n in names if n and n.strip()):
        entry = catalog.lookup(name) if catalog else None
        if entry is None or is_stale(entry):
            wanted.append(name)
    report = {"조회": [], "실패": [], "남김": max(0, len(wanted) - MAX_LOOKUPS), "오류": None}
    rows, failures, today = [], 0, date.today().isoformat()
    for name in wanted[:MAX_LOOKUPS]:
        if failures >= MAX_FAILURES:
            report["실패"].append(name)
            continue
        try:
            rows.append("\t".join([name, *judge(name), today]))
            report["조회"].append(name)
            failures = 0
        except LawApiError as error:
            failures += 1
            report["실패"].append(name)
            report["오류"] = report["오류"] or str(error).splitlines()[0][:200]
    if rows:
        path = overlay_path(LAW_FILE)
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file():
                path.write_text(HEADER, encoding="utf-8")
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(rows) + "\n")
            law_catalog.reload()
    return report
