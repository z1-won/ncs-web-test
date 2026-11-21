"""기준정보를 덧쓰는 폴더 — 운영 중에 받아 온 기준정보(NCS 요소·수행준거, 법령명 조회 결과)를 두는 곳.

패키지에 든 표(data/ncs_elements.tsv, data/law_names.tsv)는 배포할 때의 판이고 운영 중에는 고치지 않는다. 운영 중에 새로 받은 것은
이 폴더의 같은 이름 파일에 쓰고, 읽을 때는 패키지 표 위에 덧씌운다(같은 세분류·같은 법령명은 이 폴더의 것이 이긴다).
폴더가 정해지지 않으면 덧쓰기도, 운영 중 외부 조회도 하지 않는다(검수 CLI·테스트는 패키지 표만 본다).

정하는 길: 웹 서버가 set_data_dir()로(ncs-web --data, 기본 '기준정보'), 그 밖에는 환경 변수 NCS_DATA_DIR.
"""

from __future__ import annotations

import os
from pathlib import Path

_dir: Path | None = None


def set_data_dir(path: str | Path | None) -> None:
    """None이면 환경 변수 NCS_DATA_DIR로 돌아간다."""
    global _dir
    _dir = Path(path).expanduser().resolve() if path else None


def data_dir() -> Path | None:
    if _dir is not None:
        return _dir
    env = os.getenv("NCS_DATA_DIR")
    return Path(env).expanduser().resolve() if env else None


def overlay_path(name: str) -> Path | None:
    """덧쓰는 파일의 경로(없는 파일일 수 있다). 폴더가 정해지지 않았으면 None."""
    folder = data_dir()
    return folder / name if folder is not None else None


def replace_file(path: Path, text: str) -> None:
    """임시 파일에 쓰고 바꿔치기 — 쓰는 도중에 읽는 쪽이 반쯤 쓴 표를 보지 않게."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
