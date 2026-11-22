"""그림 검수·태깅 설정 — 양식 가정, 임계값, 외부 전송 기본값, 위험도 필수 점검. 값을 바꿀 때는 근거를 설계서에 적는다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class FigureConfig:
    lookback: int = 3                                  # 캡션 위 출처 줄을 찾는 문단 수(필요 지식 ⑧과 같은 값)
    page_size_mm: tuple[int, int] = (200, 280)         # 이보다 크면 쪽 전체 그림(표지·간지) — 양식 후보
    banner_max_height_mm: int = 15                     # 이보다 낮으면 띠(배너) — 양식 후보
    templates_path: Path = DATA / "template_images.tsv"
    # 외부 전송(설계 5.7): 2026-11-21 결정으로 모든 그림을 보낸다. 다시 막으려면 FIG_TRANSFER_OTHERS=확인 전(또는 금지).
    # (2026-11-20에는 공공누리 제0·1·AI유형만 보냈음 — 이 값은 기록용으로만 남김)
    transfer_allowed_kogl: frozenset[str] = frozenset({"0", "1", "AI"})
    transfer_others: str = field(default_factory=lambda: os.environ.get("FIG_TRANSFER_OTHERS", "").strip() or "허용")
    # 위험도를 정하려면 꼭 실행해야 하는 점검 — 하나라도 미실행이면 위험도는 '판정 안 함'(2026-11-21: ③ 캡션 일치)
    required_checks: frozenset[str] = frozenset({"③캡션 일치"})
    # 출처 종류별 제4조 3항 요소 — 빠지면 ①출처 요건 X
    required_elements: tuple[tuple[str, tuple[str, ...]], ...] = field(default_factory=lambda: (
        ("웹·검색", ("url", "checked_date")),
        ("스크린숏", ("checked_date",)),
        ("기존 학습모듈", ("cited_page",)),
        ("문헌", ("author",)),
        ("공공누리", ("kogl_type",)),
    ))


DEFAULT_CONFIG = FigureConfig()
