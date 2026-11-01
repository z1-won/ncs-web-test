"""패키지에 실린 단어 목록(data/*.txt)을 읽는다. 검수 실행은 네트워크를 쓰지 않고 이 파일만 본다."""

from functools import lru_cache
from importlib import resources

ACTION_NOUNS_FILE = "action_nouns.txt"


def _read_words(name: str) -> frozenset[str]:
    text = resources.files("ncs_core.data").joinpath(name).read_text(encoding="utf-8")
    words = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words.add(line.split("\t")[0].strip())
    return frozenset(words)


@lru_cache(maxsize=None)
def action_nouns() -> frozenset[str]:
    """행동명사 목록. ‘~하다’를 붙이면 뜻이 통하는 명사."""
    return _read_words(ACTION_NOUNS_FILE)

