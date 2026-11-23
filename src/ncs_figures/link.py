"""다른 담당 기능과의 연결 자리 — 03-003 저작권 안내(RightsGuideLink), 011 대체 그림 추천(RecommendationSink).

지금은 스텁: 호출을 JSONL 파일에 한 줄씩 기록만 한다. 실제 기능이 준비되면 같은 메서드를 가진 구현으로 바꾼다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class RightsGuideLink(Protocol):
    def notify(self, row: dict) -> None: ...


class RecommendationSink(Protocol):
    def request(self, brief: dict) -> None: ...


class _JsonlRecorder:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.count = 0

    def _write(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.count += 1


class RecordingLink(_JsonlRecorder):
    """03-003 스텁 — '확인 필요' 이상 행을 받으면 위치·위험도·근거만 기록."""

    def notify(self, row: dict) -> None:
        self._write({"item_id": row["item_id"], "region_path": row["region_path"], "원고": row["원고"],
                     "위험도": row["위험도"], "위험 근거": row["위험 근거"], "image_id": row.get("image_id")})


class BriefFileSink(_JsonlRecorder):
    """011 스텁 — 그림 브리프를 한 줄씩 기록."""

    def request(self, brief: dict) -> None:
        self._write(brief)
