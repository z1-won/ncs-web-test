"""분야(NCS 분류)별 공용 명칭 — 생성형 AI 프롬프트에 원고 분야와 '상표로 보지 않을 것' 예시를 넣는 데 쓴다.

모듈 코드(LM1203020401_23v3)의 앞 8자리가 세분류다. `data/field_terms.tsv`에서 코드 앞자리가 맞는 줄을
모두 모은다(* → 대분류 2 → 중분류 4 → 소분류 6 → 세분류 8자리 순). 분야 이름은 NCS 목록(`ncs_catalog`)에서 읽고,
목록이 없거나 세분류가 없으면 이름 없이 용어만 쓴다. 판정 정책은 두지 않는다(엔진 rules/가 쓴다).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .ncs_catalog import catalog

FIELD_TERMS_FILE = "field_terms.tsv"


@dataclass(frozen=True)
class Field:
    code: str                  # 세분류 8자리(모르면 "")
    path: tuple[str, ...]      # ('이용·숙박·여행·오락·스포츠', '관광·레저', '숙박서비스', '연회관리'). 목록에 없으면 ()
    terms: tuple[str, ...]     # 공용 명칭(넓은 분류 → 좁은 분류 순, 중복 제거)

    @property
    def label(self) -> str:
        return " > ".join(self.path)


def _terms_path() -> Path:
    override = os.getenv("NCS_FIELD_TERMS_FILE")
    return Path(override) if override else Path(__file__).with_name("data") / FIELD_TERMS_FILE


@lru_cache(maxsize=4)
def _read(path: str) -> tuple[tuple[str, str], ...]:
    file = Path(path)
    if not file.is_file():
        return ()
    rows = []
    for line in file.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        prefix, _, term = line.partition("\t")
        prefix, term = prefix.strip(), term.strip()
        if term and (prefix == "*" or (prefix.isdigit() and len(prefix) in (2, 4, 6, 8))):
            rows.append((prefix, term))
    return tuple(rows)


def field_of(module_code: str) -> Field:
    """모듈 코드·세분류 코드 → 분야 이름과 공용 명칭. 코드를 모르면 '*' 용어만."""
    digits = (module_code or "").replace("LM", "")[:8]
    code = digits if len(digits) == 8 and digits.isdigit() else ""
    names: tuple[str, ...] = ()
    found = catalog()
    if code and found:
        sub = found.subclass(code)
        if sub:
            names = tuple(sub.names[k] for k in ("대분류", "중분류", "소분류", "세분류"))
    order = {"*": 0, 2: 1, 4: 2, 6: 3, 8: 4}
    matched = [(order["*" if p == "*" else len(p)], term) for p, term in _read(str(_terms_path()))
               if p == "*" or (code and code.startswith(p))]
    terms: list[str] = []
    for _, term in sorted(matched, key=lambda pair: pair[0]):
        if term not in terms:
            terms.append(term)
    return Field(code, names, tuple(terms))
