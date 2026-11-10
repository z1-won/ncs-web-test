"""행동명사 판정 어휘. 검수 중 처음 보는 단어는 국립국어원 표준국어대사전 API로 ‘W하다’ 동사 표제어를 확인한다.

흐름 (F02 차례 ②):
  (1) 학습 내용명에서 머리어 W를 뽑는다 (ncs_toc.rules.action_nouns.head_word)
  (2) W가 저장된 목록(action_nouns.txt)에 있으면 O
  (3) 없으면 ‘W하다’를 사전 API로 조회한다
  (4) 동사 표제어가 있으면 목록에 추가하고 O
  (5) 없으면 X. 조회 결과는 action_nouns_rejected.txt에 남겨 다시 묻지 않는다(외래어 예외 처리는 추후)
  API를 부를 수 없을 때(인증키 없음·네트워크 오류)는 △ — "사전에 없음"과 "사전을 못 봄"은 다르다.

API 인증키는 환경 변수 STDICT_API_KEY. 목록 파일 위치는 NCS_LEXICON_DIR로 바꿀 수 있다(기본: 패키지 data/).
"""

from __future__ import annotations

import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date
from importlib import resources
from pathlib import Path
from xml.etree import ElementTree as ET

ACTION_NOUNS_FILE = "action_nouns.txt"
REJECTED_FILE = "action_nouns_rejected.txt"
STDICT_SEARCH_URL = "https://stdict.korean.go.kr/api/search.do"

# resolver(word) → (True 행동명사 / False 아님 / None 조회 불가, 근거)
Resolver = Callable[[str], tuple[bool | None, str]]


def _data_dir() -> Path:
    custom = os.getenv("NCS_LEXICON_DIR")
    if custom:
        return Path(custom)
    return Path(str(resources.files("ncs_core.data")))


def _read(path: Path) -> dict[str, str]:
    """단어 → 그 줄(출처·날짜·근거). 주석·빈 줄 무시."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            out[line.split("\t")[0].strip()] = line
    return out


def _plain(word: str) -> str:
    return word.replace("-", "").replace("^", "").replace(" ", "")


def stdict_resolver(key: str, timeout: float = 10.0) -> Resolver:
    """표준국어대사전 search.do로 ‘W하다’ 동사 표제어를 정확 검색하는 resolver."""

    def resolve(word: str) -> tuple[bool | None, str]:
        target = word + "하다"
        params = {"key": key, "q": target, "advanced": "y", "method": "exact", "type_search": "search", "num": 50}
        request = urllib.request.Request(
            f"{STDICT_SEARCH_URL}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "ncs-f02-review/0.1"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            return None, f"사전 조회 실패: {error}"
        if not raw.strip():
            return None, "사전 조회 실패: 빈 응답(인증키·일일 한도 확인)"
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return None, "사전 조회 실패: 응답을 읽을 수 없음"
        error = root.find(".//error_code")
        if error is not None:
            return None, f"사전 API 오류 {error.text}: {root.findtext('.//message') or ''}"
        for item in root.iter("item"):
            if _plain(item.findtext("word", "")) == target and "동사" in (item.findtext("pos", "") or ""):
                return True, f"'{item.findtext('word')}' 동사 표제어(target_code {item.findtext('target_code')})"
        return False, f"표준국어대사전에 '{target}' 동사 표제어 없음"

    return resolve


class ActionNounLexicon:
    """저장된 목록 + 사전 조회. 조회 결과는 목록 파일에 바로 기록한다."""

    def __init__(self, directory: Path | None = None, resolver: Resolver | None = None):
        self.directory = Path(directory) if directory else _data_dir()
        self.resolver = resolver
        self._lock = threading.Lock()
        self.accepted = _read(self.directory / ACTION_NOUNS_FILE)
        self.rejected = _read(self.directory / REJECTED_FILE)

    @property
    def words(self) -> frozenset[str]:
        return frozenset(self.accepted)

    def _append(self, filename: str, word: str, source: str, why: str) -> str:
        line = f"{word}\t{source}\t{date.today().isoformat()}\t{why}"
        path = self.directory / filename
        with path.open("a", encoding="utf-8") as handle:
            if path.stat().st_size and not path.read_text(encoding="utf-8").endswith("\n"):
                handle.write("\n")
            handle.write(line + "\n")
        return line

    def add(self, word: str, source: str, why: str) -> None:
        """사람이 승인한 단어를 목록에 넣는다(source='manual')."""
        with self._lock:
            if word not in self.accepted:
                self.accepted[word] = self._append(ACTION_NOUNS_FILE, word, source, why)
                self.rejected.pop(word, None)

    def judge(self, word: str) -> tuple[str, str | None]:
        """→ ('O'|'X'|'△', 비고). (2)~(5)."""
        if not word:
            return "△", "학습 내용명이 비어 있음"
        if not any(ch.isalpha() for ch in word):
            # '?'·'…'·'-'처럼 글자가 없는 조각은 단어가 아니다. 사전에 묻거나 X로 기록하지 않는다(읽기 결함일 수 있음).
            return "△", f"학습 내용명 끝 단어를 읽지 못함: '{word}'"
        if word in self.accepted:
            return "O", None
        if word in self.rejected:
            return "X", f"'{word}' — 행동명사가 아님(‘{word}하다’ 사전 표제어 없음)"
        if self.resolver is None:
            return "△", f"행동명사 여부 확인 필요: '{word}' (사전 조회 불가 — 인증키 미설정)"
        verdict, why = self.resolver(word)
        with self._lock:
            if verdict is True:
                self.accepted.setdefault(word, self._append(ACTION_NOUNS_FILE, word, "stdict", why))
                return "O", None
            if verdict is False:
                self.rejected.setdefault(word, self._append(REJECTED_FILE, word, "stdict", why))
                return "X", f"'{word}' — 행동명사가 아님({why})"
        return "△", f"행동명사 여부 확인 필요: '{word}' ({why})"


_default: ActionNounLexicon | None = None
_default_lock = threading.Lock()


def default_lexicon() -> ActionNounLexicon:
    """프로세스당 하나. 인증키(STDICT_API_KEY)가 있으면 사전 조회를 켠다."""
    global _default
    with _default_lock:
        if _default is None:
            key = os.getenv("STDICT_API_KEY")
            _default = ActionNounLexicon(resolver=stdict_resolver(key) if key else None)
        return _default


def action_nouns() -> frozenset[str]:
    """저장된 행동명사 목록(조회 없음)."""
    return default_lexicon().words
