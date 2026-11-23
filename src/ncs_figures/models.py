"""그림 기능 패키지의 데이터 타입. 결과 행(dict)은 rows.to_row에서 마지막에만 만든다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from ncs_core.figure_context import FigureContext
from ncs_core.source_line import AiMarker, SourceInfo

FigureKind = Literal["양식", "양식 후보", "본문 그림", "캡션 없는 그림"]
Transfer = Literal["허용", "금지", "확인 전"]
RiskLevel = Literal["문제없음", "확인 필요", "고위험", "판정 안 함"]


@dataclass(frozen=True)
class FigureItem:
    """prepare_figures의 결과 — 점검의 입력."""

    ctx: FigureContext
    image_id: str | None                # 그림을 못 읽으면 None
    file_sha256: str
    phash: str | None
    kind: FigureKind
    source: SourceInfo | None           # 출처 줄이 없으면 None
    ai: AiMarker | None
    transfer: Transfer = "금지"
    transfer_reason: str = ""


@dataclass(frozen=True)
class CheckOutcome:
    name: str                           # 행의 체크 이름(예: "①출처 있음")
    value: str | None                   # O·X·△·-, None = 미실행
    note: str = ""
    suggestion: str | None = None
    skipped: str | None = None          # 미실행 이유
    model: str | None = None


@dataclass(frozen=True)
class Match:
    image_id: str
    match_type: Literal["exact", "near", "similar"]
    score: float
    source_ref: str
    license_type: str | None = None
    reuse_scope: str | None = None
    rights_status: str | None = None
    # 화면·메모에 보일 DB 쪽 정보(어느 모듈의 어떤 그림, 그 그림의 출처)
    module: str | None = None
    figure_label: str | None = None
    figure_title: str | None = None
    source_text: str | None = None
    source_kind: str | None = None
    rights_basis: str | None = None


@dataclass(frozen=True)
class Resources:
    """주입 자원 — 없으면 해당 점검은 미실행(오류가 아님)."""

    lookup: object | None = None        # ImageRightsLookup (R3)
    scorer: object | None = None        # 그림-캡션 점수 (R2)
    sscd: object | None = None          # 복제 탐지 벡터 (R3)
    semantic: object | None = None      # 의미 벡터 (R4)
    asker: Callable[..., dict] | None = None   # VLM 호출 (R2)
    marks: object | None = None         # ② 그림 속 마크·저작권 문구(marks.MarkReader — 로컬 OCR)
    submissions: object | None = None   # ⑥⑦ 집필자 제출 서류(submissions.Submissions)
    link: object | None = None          # 03-003 RightsGuideLink
    sink: object | None = None          # 011 RecommendationSink (R7)


@dataclass(frozen=True)
class FigureReview:
    item: FigureItem
    checks: tuple[CheckOutcome, ...]
    matches: tuple[Match, ...] = ()
    risk: RiskLevel | None = None       # 양식·양식 후보는 None. 필수 점검(③)이 미실행이면 '판정 안 함'
    risk_reasons: tuple[str, ...] = ()
    reading: dict | None = None         # 그림 판독(reading.read_figure) — 판독을 켰을 때만
    model_calls: tuple[dict, ...] = ()  # 이 그림에서 부른 모델 결과(캡션 판정 등) — 사용량 합계용
    replacements: tuple[dict, ...] = () # 그림 DB의 같은 주제 그림(바꿔 쓸 후보) — DB가 있을 때만


@dataclass(frozen=True)
class FigureReviewResult:
    module_code: str
    reviews: tuple[FigureReview, ...]
    rows: list[dict]
    summary: dict
    diagnostics: dict = field(default_factory=dict)
