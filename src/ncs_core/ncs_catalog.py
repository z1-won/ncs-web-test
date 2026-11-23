"""NCS 분류·능력단위 목록(data/ncs_units.tsv) 조회.

출처: NCS 포털 '학습모듈 분류보기' 내려받기(scripts/data/build_ncs_catalog.py로 변환). 학습모듈이 개발된 능력단위가 세분류별로
들어 있다. 위치 ①~④(대·중·소분류 명칭, 소분류의 세분류 목록, 세분류의 능력단위·학습모듈 목록·순서)의 기준과
개요 ③(선수학습의 NCS 코드·명칭 유효성)에 쓴다. 개발계획서는 이 목록을 옮겨 적은 것이라 목록이 있으면 목록을 기준으로 삼고,
없는 세분류(목록 갱신 전 신규 등)는 개발계획서로 돌아간다.

파일 위치는 NCS_CATALOG_FILE 환경 변수로 바꿀 수 있다(기본: 패키지 data/ncs_units.tsv).
요소·수행준거 표(ncs_elements.tsv)는 기준정보 폴더(ncs_core.refdata)에 같은 이름 파일이 있으면 그 위에 덧씌운다 — 운영 중에
NCS에서 받아 온 세분류(ncs_core.ncs_fetch)가 거기에 있다. 덧쓰는 파일에 든 세분류는 통째로 그 파일의 것을 쓴다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .refdata import overlay_path

CATALOG_FILE = "ncs_units.tsv"
LEVELS_FILE = "ncs_levels.tsv"   # 세분류코드  능력단위코드  능력단위명  수준  훈련시간 (scripts/data/build_ncs_levels.py)
ELEMENTS_FILE = "ncs_elements.tsv"   # 세분류코드 능력단위코드 능력단위명 수준 정의 요소코드 요소명 수행준거(‖ 구분) (scripts/data/build_ncs_elements.py)
CRITERIA_SEP = " ‖ "
CLASS_LABELS = ("대분류", "중분류", "소분류")


@dataclass(frozen=True)
class Unit:
    code: str        # 1203020401_23v3
    name: str        # 연회 판촉
    subclass: str    # 12030204

    @property
    def base(self) -> str:
        """버전을 뺀 10자리."""
        return self.code[:10]

    @property
    def number(self) -> int:
        return int(self.code[8:10])


@dataclass(frozen=True)
class Subclass:
    code: str                      # 12030204
    names: dict[str, str]          # {'대분류': …, '중분류': …, '소분류': …, '세분류': …}
    units: tuple[Unit, ...]        # 코드 순

    @property
    def name(self) -> str:
        return self.names["세분류"]

    @property
    def small(self) -> str:
        """소분류 코드 6자리."""
        return self.code[:6]


# NCS 원자료의 수행준거 글이 제 번호로 시작하는 것이 있다('4.7 4.7 충성고객들을 …'). 계획서에는 번호가 한 번만 적히므로 하나로 줄인다
DOUBLED_NUMBER = re.compile(r"^(\d+\.\d+)\s+\1\s+")


def read_elements(path: Path) -> dict[str, dict]:
    """ncs_elements.tsv → {능력단위 10자리: {'duty','code','name','level','definition','fetched','elements':[{'code','no','name','criteria':[…]}]}}.
    fetched는 받아 온 날(YYYY-MM-DD, 아홉째 열) — 패키지 표에는 없어 None."""
    out: dict[str, dict] = {}
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if re.match(r"^\d{8}\t", line) or not rows:
            rows.append(line)
        else:   # 문장 안 줄바꿈으로 쪼개진 조각 — 앞 행에 붙인다
            rows[-1] += " " + line.strip()
    for line in rows:
        duty, code, name, level, definition, element_code, element_name, criteria, fetched = (line.split("\t") + [""] * 9)[:9]
        unit = out.setdefault(code[:10], {"duty": duty, "code": code, "name": name, "level": int(level) if level.strip() else None,
                                          "definition": definition, "fetched": fetched.strip() or None, "elements": []})
        unit["elements"].append({"code": element_code, "no": int(element_code.rsplit(".", 1)[-1] or 0), "name": element_name,
                                 "criteria": [DOUBLED_NUMBER.sub(r"\1 ", c) for c in criteria.split(CRITERIA_SEP) if c]})
    return out


def read_levels(path: Path) -> dict[str, dict]:
    """ncs_levels.tsv → {능력단위 10자리: {'duty','code','name','level','hours'}}."""
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        duty, code, name, level = parts[:4]
        hours = parts[4] if len(parts) > 4 else ""
        out[code[:10]] = {"duty": duty, "code": code, "name": name, "level": int(level) if level.strip() else None, "hours": hours}
    return out


class Catalog:
    def __init__(self, path: Path, levels_path: Path | None = None, elements_overlay: Path | None = None):
        self.path = path
        self.subclasses: dict[str, Subclass] = {}
        self._units: dict[str, Unit] = {}        # 10자리 → Unit
        levels_path = levels_path if levels_path is not None else path.with_name(LEVELS_FILE)
        self.levels: dict[str, dict] = read_levels(levels_path) if levels_path.is_file() else {}
        elements_path = path.with_name(ELEMENTS_FILE)
        self.element_units: dict[str, dict] = read_elements(elements_path) if elements_path.is_file() else {}
        if elements_overlay is not None and elements_overlay.is_file():
            extra = read_elements(elements_overlay)
            fetched_duties = {unit["duty"] for unit in extra.values()}   # 받아 온 세분류는 통째로 바꾼다(없어진 능력단위가 남지 않게)
            self.element_units = {key: unit for key, unit in self.element_units.items() if unit["duty"] not in fetched_duties}
            self.element_units.update(extra)
        rows: dict[str, list] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            sub, big, mid, small, name, _ncs_year, _module_year, code, unit_name = line.split("\t")
            rows.setdefault(sub, [{"대분류": big, "중분류": mid, "소분류": small, "세분류": name}, []])
            rows[sub][1].append(Unit(code, unit_name, sub))
        for sub, (names, units) in rows.items():
            units.sort(key=lambda u: u.code)
            self.subclasses[sub] = Subclass(sub, names, tuple(units))
            for unit in units:
                self._units[unit.base] = unit

    def subclass(self, code: str) -> Subclass | None:
        """모듈 코드(LM1203020401_23v3)·능력단위 코드·세분류 8자리 어느 것이든 받는다."""
        digits = code.replace("LM", "")[:8]
        return self.subclasses.get(digits)

    def subclasses_of_small(self, code: str) -> list[Subclass]:
        """소분류(앞 6자리)에 속한 세분류를 코드 순으로."""
        small = code.replace("LM", "")[:6]
        return sorted((s for s in self.subclasses.values() if s.small == small), key=lambda s: s.code)

    def unit(self, code: str) -> Unit | None:
        """능력단위 코드(버전 있든 없든, LM 접두 있든 없든) → Unit."""
        return self._units.get(code.replace("LM", "")[:10])

    def level(self, code: str) -> int | None:
        """능력단위 수준(1~8). 수준 표가 없거나 코드가 없으면 None."""
        row = self.levels.get(code.replace("LM", "")[:10])
        return row["level"] if row else None

    def unit_detail(self, code: str) -> dict | None:
        """요소·수행준거 표의 능력단위(정의·요소·수행준거). 표에 없으면 None — scripts/data/build_ncs_elements.py로 받아 둔다."""
        return self.element_units.get(code.replace("LM", "")[:10])

    def units_with_detail(self, duty: str) -> list[dict]:
        return sorted((u for u in self.element_units.values() if u["duty"] == duty[:8]), key=lambda u: u["code"])

    def level_row(self, code: str) -> dict | None:
        """수준 표의 행(능력단위 목록에 없는 능력단위도 수준 표에는 있을 수 있다)."""
        return self.levels.get(code.replace("LM", "")[:10])


def _default_path() -> Path:
    override = os.getenv("NCS_CATALOG_FILE")
    return Path(override) if override else Path(__file__).with_name("data") / CATALOG_FILE


@lru_cache(maxsize=4)
def _load(path: str, overlay: str = "") -> Catalog | None:
    return Catalog(Path(path), elements_overlay=Path(overlay) if overlay else None) if Path(path).is_file() else None


def catalog() -> Catalog | None:
    """경로당 한 번 읽는다. 파일이 없으면 None(기준은 개발계획서로). NCS_CATALOG_FILE을 없는 경로로 두면 목록을 끈다(합성 원고 테스트)."""
    overlay = overlay_path(ELEMENTS_FILE)
    return _load(str(_default_path()), str(overlay) if overlay is not None else "")


def reload() -> None:
    """읽어 둔 목록을 버린다 — 기준정보 폴더의 표를 새로 썼을 때 부른다(다음 catalog()가 다시 읽는다)."""
    _load.cache_clear()


def criteria_of(module_code: str) -> list[str] | None:
    """학습모듈(능력단위) 코드 → 받아 둔 NCS 기준정보의 수행준거 문장 전부. 목록이 꺼져 있거나, 그 능력단위를 받아 두지 않았거나,
    버전이 다른 기준정보뿐이면 None — 개발계획서가 없을 때 학습 목표를 대조하는 데 쓴다(필요 지식 ⑤, 평가 ②)."""
    cat = catalog()
    code = (module_code or "").replace("LM", "")
    detail = cat.unit_detail(code) if cat is not None and code else None
    if detail is None or detail.get("code") != code:
        return None
    return [criterion for element in detail.get("elements") or [] for criterion in element.get("criteria") or []] or None

