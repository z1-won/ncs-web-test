"""법령명 표(data/law_names.tsv) 조회 — 원고·계획서에 적힌 법령 이름이 현행인지.

출처: scripts/data/build_law_names.py(법제처 Open API). 검수 중에는 이 표만 읽는다.
열: 표기 \\t 정식명칭 \\t 법령ID \\t 시행일자 \\t 제개정구분 \\t 상태 \\t 현행명칭 \\t 조회일
상태: 현행 / 폐지 / 명칭변경 / 미검색 / 현행목록없음(연혁 조회 불가). 명칭변경이면 현행명칭에 지금 이름.
파일 위치는 LAW_NAMES_FILE 환경 변수로 바꿀 수 있다(기본: 패키지 data/law_names.tsv).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LAW_FILE = "law_names.tsv"
QUOTED = re.compile(r"[「『]([^」』]{2,80})[」』]")
# 따옴표 없이 적힌 법령명: '…법', '…법 시행령', '…법 시행규칙', '…에 관한 법률'. 일반 명사 '방법·기법·문법·화법…'은 제외한다.
# 띄어 쓴 이름('개인정보 보호법', '고객정보 보호법')은 앞 어절 하나까지 붙여 잡는다. 맨 '법'으로 끝나면 뒤에 조사 하나까지만 허용(법인·법적·법규 제외).
PARTICLE = r"(?=(?:[에을를은는이가과와의도만](?:서|는|게|로|도)?)?(?![가-힣]))"
BARE = re.compile(r"(?<![가-힣])([가-힣A-Za-z0-9·]{2,20}(?:\s[가-힣A-Za-z0-9·]{1,12}){0,2}(?:에\s*관한\s*법률|법\s*시행령|법\s*시행규칙|법률|법" + PARTICLE + "))")
LAW_END = re.compile(r"(법률|법)[에을를은는이가과와의도만]?$")
# 앞 어절이 문장의 다른 말이면 떼어 낸다: 조사·어미로 끝나는 어절('규정에', '따라', '관련된')
NOT_NAME_WORD = re.compile(r"(에|을|를|은|는|이|가|과|와|의|로|도|라|여|서|고|며|면|해|된|한|하여|따라|관련|및)$")
NOT_LAW_TAIL = re.compile(r"(방법|기법|문법|어법|화법|용법|수법|편법|비법|작법|표기법|계산법|분석법|처리법|측정법|교수법|학습법|접근법|사용법|조작법|활용법|해법|요법|기술법|필법|서법|도법|산법|상법적|기법적)$")


def normalize(name: str) -> str:
    return re.sub(r"[\s「」『』··]", "", name or "")


def extract_law_names(text: str) -> list[tuple[str, bool]]:
    """글에서 법령명 후보 → [(표기, 따옴표 여부)]. 따옴표로 묶인 이름은 무엇이든 후보, 맨 이름은 '법'류로 끝나는 것만."""
    out, seen = [], set()
    for m in QUOTED.finditer(text or ""):
        name = m.group(1).strip()
        if re.search(r"(법|령|규칙|고시|훈령|예규|지침|조례|법률)$", name) and normalize(name) not in seen:
            seen.add(normalize(name))
            out.append((name, True))
    stripped = QUOTED.sub(" ", text or "")
    for m in BARE.finditer(stripped):
        words = m.group(1).strip().split()
        candidates = []
        while len(words) > 1:
            front, rest = words[0], " ".join(words[1:])
            if LAW_END.search(front) and not re.search(r"^시행\s*(령|규칙)", rest):   # '근로기준법과 최저임금법' → 두 법령
                candidates.append(re.sub(r"[에을를은는이가과와의도만]$", "", front))
                words = words[1:]
            elif NOT_NAME_WORD.search(front):                                        # '따라 산업안전보건법' → 앞 어절은 문장
                words = words[1:]
            else:
                break
        candidates.append(" ".join(words))
        for candidate in candidates:
            tail_word = candidate.split()[-1]
            if NOT_LAW_TAIL.search(tail_word) or len(normalize(candidate)) < 4 or normalize(candidate) in seen:
                continue
            seen.add(normalize(candidate))
            out.append((candidate, False))
    return out


@dataclass(frozen=True)
class LawEntry:
    written: str
    name: str
    law_id: str
    effective: str
    revision: str
    status: str       # 현행 / 폐지 / 명칭변경 / 미검색 / 현행목록없음
    current_name: str
    checked: str


class LawCatalog:
    def __init__(self, path: Path):
        self.path = path
        self.entries: dict[str, LawEntry] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            parts = (line.split("\t") + [""] * 8)[:8]
            entry = LawEntry(*parts)
            self.entries[normalize(entry.written)] = entry
            if entry.name:
                self.entries.setdefault(normalize(entry.name), entry)

    def lookup(self, name: str) -> LawEntry | None:
        return self.entries.get(normalize(name))


def _default_path() -> Path:
    override = os.getenv("LAW_NAMES_FILE")
    return Path(override) if override else Path(__file__).with_name("data") / LAW_FILE


@lru_cache(maxsize=4)
def _load(path: str) -> LawCatalog | None:
    return LawCatalog(Path(path)) if Path(path).is_file() else None


def law_catalog() -> LawCatalog | None:
    """표가 없으면 None(⑩은 판단불가)."""
    return _load(str(_default_path()))
