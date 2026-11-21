"""운영 중에 NCS 요소·수행준거를 받아 와 기준정보 폴더에 둔다 — 개발계획서 작성에서 아직 없는 세분류를 고르거나 다시 받을 때.

scripts/data/build_ncs_elements.py(개발자가 터미널에서 패키지 표를 채우는 길)와 같은 API(ncs_api)를 쓰되, 쓰는 곳이 다르다:
여기는 패키지 표를 고치지 않고 기준정보 폴더(ncs_core.refdata)의 ncs_elements.tsv에 세분류 단위로 바꿔 쓴다.
세분류 하나를 받는 데 호출 1 + 능력단위 수 × 2번(요소 이름, 수행준거). 능력단위 하나라도 못 받으면 아무것도 쓰지 않는다
(반만 받은 세분류가 '받아 둔 것'으로 보이지 않게).
"""

from __future__ import annotations

import os
import threading
from datetime import date
from pathlib import Path

from . import ncs_api, ncs_catalog
from .ncs_api import NcsApiError
from .ncs_catalog import CRITERIA_SEP, ELEMENTS_FILE
from .refdata import overlay_path, replace_file

HEADER = ("# NCS 능력단위요소·수행준거 — 운영 중에 NCS(공공데이터포털 B490007/ncsInfo)에서 받아 온 세분류. ncs_core.ncs_fetch가 쓴다.\n"
          "# 세분류코드\t능력단위코드\t능력단위명\t수준\t정의\t요소코드\t요소명\t수행준거(‖ 구분)\t받아 온 날\n")
_lock = threading.Lock()


def can_fetch() -> bool:
    """받아 올 수 있는가 — NCS 인증키가 있고 쓸 곳(기준정보 폴더)이 정해져 있을 때만."""
    return bool(os.getenv("NCS_API_KEY")) and overlay_path(ELEMENTS_FILE) is not None


def _clean(value) -> str:
    """표 한 칸에 들어갈 글 — 문장 안의 줄바꿈·탭을 공백으로(줄바꿈이 섞이면 다음 줄이 다른 행으로 읽힌다)."""
    return " ".join(str(value if value is not None else "").split())


def fetch_duty(duty: str) -> list[dict]:
    """세분류(8자리)의 능력단위 전부 — ncs_catalog.read_elements의 값과 같은 모양. 못 받으면 NcsApiError."""
    duty = duty[:8]
    units = ncs_api.units(duty)
    if not units:
        raise NcsApiError(f"NCS에 세분류 {duty}의 능력단위가 없습니다")
    out = []
    for unit in units:
        number = unit.code[8:10]
        names = {e["no"]: e["name"] for e in ncs_api.elements(duty, number) if e["code"] == unit.code}
        sentences = ncs_api.criteria(duty, number)
        numbers = sorted(set(names) | set(sentences))
        if not numbers:
            raise NcsApiError(f"NCS에 능력단위 {unit.code}의 요소·수행준거가 없습니다")
        out.append({"duty": duty, "code": unit.code, "name": unit.name, "level": unit.level, "definition": unit.definition,
                    "elements": [{"code": f"{unit.code}.{no}", "no": no, "name": names.get(no, ""), "criteria": sentences.get(no, [])}
                                 for no in numbers]})
    return out


def _rows(units: list[dict], fetched: str) -> list[str]:
    return ["\t".join(_clean(v) for v in [unit["duty"], unit["code"], unit["name"], unit["level"] or "", unit["definition"],
                                           element["code"], element["name"], CRITERIA_SEP.join(element["criteria"]), fetched])
            for unit in units for element in unit["elements"]]


def save_duty(duty: str, units: list[dict], *, fetched: str | None = None) -> Path:
    """기준정보 폴더의 표에서 이 세분류의 행을 모두 빼고 새로 받은 행을 넣는다. 다른 세분류의 행은 그대로 둔다."""
    path = overlay_path(ELEMENTS_FILE)
    if path is None:
        raise ValueError("기준정보 폴더가 정해지지 않았습니다(ncs-web --data 또는 NCS_DATA_DIR)")
    duty = duty[:8]
    with _lock:
        kept = [line for line in (path.read_text(encoding="utf-8").splitlines() if path.is_file() else [])
                if line.strip() and not line.startswith("#") and not line.startswith(duty + "\t")]
        replace_file(path, HEADER + "\n".join(kept + _rows(units, fetched or date.today().isoformat())) + "\n")
        ncs_catalog.reload()
    return path


def _signature(unit: dict) -> tuple:
    return (unit["code"], unit["name"], unit["level"], unit["definition"],
            tuple((e["no"], e["name"], tuple(e["criteria"])) for e in unit["elements"]))


def compare(before: list[dict], after: list[dict]) -> dict:
    """다시 받은 것이 전과 무엇이 다른가 — {'추가': [...], '삭제': [...], '변경': [...]} (능력단위 '코드 이름')."""
    old = {unit["code"][:10]: unit for unit in before}
    new = {unit["code"][:10]: unit for unit in after}
    label = lambda unit: f"{unit['code']} {unit['name']}"   # noqa: E731
    return {
        "추가": [label(new[key]) for key in sorted(new.keys() - old.keys())],
        "삭제": [label(old[key]) for key in sorted(old.keys() - new.keys())],
        "변경": [label(new[key]) for key in sorted(new.keys() & old.keys()) if _signature(old[key]) != _signature(new[key])],
    }


def refresh_duty(duty: str) -> dict:
    """세분류를 NCS에서 (다시) 받아 기준정보 폴더에 두고, 전과 달라진 것을 돌려준다: {'units': [...], '변화': compare(), '처음': bool}."""
    cat = ncs_catalog.catalog()
    before = cat.units_with_detail(duty) if cat else []
    units = fetch_duty(duty)
    save_duty(duty, units)
    return {"units": units, "변화": compare(before, units), "처음": not before}
