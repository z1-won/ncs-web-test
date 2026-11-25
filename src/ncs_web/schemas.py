"""API 요청·응답 모델. 경로 모듈(routes/)이 함께 쓴다."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

CheckName = Literal["position", "toc", "overview", "knowledge", "perform", "teaching", "evaluation", "references", "colophon", "misc", "plan"]


class SavedPaths(BaseModel):
    folder: str
    zip: str


class ReviewResponse(BaseModel):
    id: str | None = None
    group: str | None = None   # 전체 실행 묶음 id(업로드 토큰으로 실행했을 때)
    check: CheckName
    module_code: str
    요약: dict[str, Any]
    검수확인서: list[dict[str, Any]]
    진단: dict[str, Any]
    지적사항: list[dict[str, Any]]
    전체: list[dict[str, Any]]
    저장: SavedPaths | None = None


class ErrorResponse(BaseModel):
    error: str
    traceback: str | None = None


class SheetExportRequest(BaseModel):
    """확인서 내보내기 입력 — 화면이 가진 확인서 행을 그대로 보낸다(DB 모드든 파일 모드든, 저장 전 결과든 같은 길)."""

    module_code: str
    rows: list[dict[str, Any]]          # 여러 구성요소의 검수확인서 행을 이어 붙인 것
    created_at: str | None = None


class PlanDraftRequest(BaseModel):
    """개발계획서 초안 만들기 입력(REQ-02-001 '작성'). units를 비우면 세분류의 능력단위 전부."""

    duty: str                                   # 세분류 코드 8자리
    units: list[str] = []                       # 능력단위 코드(1203020201_24v3) 목록
    agency: str = ""                            # 개발기관명
    english: str = ""                           # 영문 세분류명
    writers: dict[str, str] = {}                # 능력단위 코드 → 담당 집필진
    reviewers: dict[str, str] = {}              # 능력단위 코드 → 담당 검토진
    kind: str = "신규"                          # "신규" | "개선" — 개선이면 개선 양식(NCS 변경 전·후 대조표 + 총괄표의 개선 유형 열)에 채운다
    types: dict[str, str] = {}                  # 개선일 때: 능력단위 코드 → 개선 유형(신규 개발/기존 개선/양식 편집/최소개선). 없으면 기존 개선
    previous: dict[str, str] = {}               # 개선일 때: 능력단위 코드 → 개선 전 능력단위번호('없음'이면 신설). 없으면 대조표의 개선 전 칸을 비워 둔다


class UploadResponse(BaseModel):
    """전체 실행용 업로드 토큰. upload를 /api/review에 files 대신 넘기면 같은 파일로 검수를 여러 번 돌릴 수 있다."""

    upload: str
    group: str                    # 이 토큰으로 실행한 검수들의 이력 묶음 id
    files: list[str]
    roles: dict[str, str | None]  # 역할 → 파일 이름(요청의 roles로 지정했으면 그대로, 아니면 넣은 순서). plan이 None이면 개발계획서 없음
    expires_in: int               # 초


class ImageActionRequest(BaseModel):
    """이미지 저작권 DB의 확정·확정 취소(REQ-02-010). 변경 이력의 이름은 로그인한 계정에서 읽는다. by는 로그인을 끈 서버(테스트)에서만 쓴다."""
    by: str = Field(default="", max_length=50)
    version: int | None = Field(None, ge=1)   # 화면이 열어 본 버전. 주면 그 버전일 때만 바꾼다


class ImageEvidenceRequest(BaseModel):
    """이미지 저작권 DB에 증빙 1건을 직접 등록(REQ-02-010). 서류 파일은 받지 않는다 — 종류와 파일 이름(또는 보관 위치)만 남긴다."""
    by: str = Field(default="", max_length=50)
    kind: str = Field(min_length=1, max_length=30)          # transfer_consent / license_consent / portrait_consent / ai_pledge
    file_ref: str | None = Field(None, max_length=200)      # 서류 파일 이름 또는 보관 위치
    submitted_on: date | None = None
    note: str | None = Field(None, max_length=500)


class RecommendRequest(BaseModel):
    """이미지 추천(REQ-02-011). 문단과 능력단위 코드 중 하나는 있어야 한다."""
    text: str = Field("", max_length=4000)
    unit_code: str = Field("", max_length=30)        # '1203020201', 'LM1203020201_24v3' 모두 받는다
    criterion_no: str = Field("", max_length=10, pattern=r"^(\d+\.\d+)?$")   # 수행준거 번호 '1.1'
    limit: int = Field(10, ge=1, le=30)
    use_llm: bool = True


class DiagramSpecRequest(BaseModel):
    """도표·표 명세 후보(REQ-02-006 ①). 집필자가 쓴 문단이 있어야 한다. kind를 주면 그 종류만 받는다."""
    text: str = Field(max_length=4000)
    criterion: str = Field("", max_length=4000)      # 수행준거 글(선택) — 근거 검사의 글에 함께 넣는다
    kind: Literal["", "diagram", "graph", "sequence", "cycle", "structure", "compare", "table", "bar", "line", "pie"] = ""
    focus: str = Field("", max_length=200)           # 문단 가운데 그림으로 나타낼 부분(선택)


class DiagramCheckRequest(BaseModel):
    """명세의 모양과 근거 검사. text가 없으면 모양만 본다."""
    spec: dict[str, Any]
    text: str = Field("", max_length=4000)
    criterion: str = Field("", max_length=4000)


class DiagramRenderRequest(BaseModel):
    """명세를 그린다. format: png 그림 / html·tsv 표를 한글 프로그램에 붙여 넣을 글(표 명세만)."""
    spec: dict[str, Any]
    width_mm: float = Field(150.0, ge=40.0, le=170.0)
    dpi: int = Field(300, ge=72, le=600)
    format: Literal["png", "html", "tsv"] = "png"


class DiagramMarkingRequest(BaseModel):
    """만든 도표·표 하나에 붙일 표기 줄(출처 줄, AI 활용 줄, 번호와 제목). date는 활용 일자."""
    title: str = Field("", max_length=40)
    tool: str = Field(max_length=40)
    date: date
    kind: Literal["sequence", "cycle", "structure", "compare", "table", "bar", "line", "pie", "photo", "illustration"]
    number: str = Field("", max_length=10, pattern=r"^(\d+-\d*)?$")     # '1-2', 번호를 아직 모르면 '1-' 또는 빈 글
    usage: Literal[1, 4] = 1                                             # 표기 예 번호. 4(AI 창작)는 사진·삽화를 문단 없이 만들었을 때


class ImagePromptRequest(BaseModel):
    """사진·삽화의 장면 후보(REQ-02-006 ①). 문단 없이 focus(주제)만 줄 수도 있다. scene: 집필자가 고친 한국어 장면 — 그 하나만 영어로 옮긴다."""
    text: str = Field("", max_length=4000)
    criterion: str = Field("", max_length=4000)
    kind: Literal["photo", "illustration"]
    focus: str = Field("", max_length=400)
    scene: str = Field("", max_length=400)


class ImageGenerateRequest(BaseModel):
    """장면 글(영어)로 사진·삽화를 만든다. scene_ko는 검사에만 쓴다. seed를 주면 같은 그림이 다시 나온다."""
    scene: str = Field(min_length=1, max_length=800)
    scene_ko: str = Field("", max_length=400)
    kind: Literal["photo", "illustration"]
    shape: Literal["landscape", "portrait", "square"] = "landscape"
    count: int = Field(2, ge=1, le=4)
    seed: int | None = Field(None, ge=0, le=2**31 - 1)


class ImageInspectRequest(BaseModel):
    """만든 그림 한 장(PNG, base64)을 받기 전에 본다 — 놓을 폭에서의 해상도, 이미지 저작권 DB의 닮은 그림(DB가 있는 서버)."""
    png: str = Field(min_length=1, max_length=28_000_000)
    width_mm: float = Field(150.0, ge=40.0, le=170.0)
    limit: int = Field(5, ge=1, le=20)


class ImageRegisterRequest(BaseModel):
    """만든 사진·삽화를 이미지 저작권 DB에 올린다(에디터와 직능연)."""
    png: str = Field(min_length=1, max_length=28_000_000)
    kind: Literal["photo", "illustration"]
    usage: Literal[1, 4] = 1
    title: str = Field("", max_length=40)
    tool: str = Field(max_length=40)
    date: date
    module_code: str = Field("", max_length=30)
    number: str = Field("", max_length=10, pattern=r"^(\d+-\d+)?$")
    by: str = Field("", max_length=80)


class DiagramSimilarRequest(BaseModel):
    """만든 그림과 닮은 그림을 이미지 저작권 DB에서 찾는다. 그림은 서버가 명세에서 다시 그린다."""
    spec: dict[str, Any]
    width_mm: float = Field(150.0, ge=40.0, le=170.0)
    limit: int = Field(5, ge=1, le=20)


class DiagramRegisterRequest(DiagramSimilarRequest):
    """만든 그림을 이미지 저작권 DB에 올린다(에디터와 직능연). ai=false는 생성형 AI 없이 직접 적어 그린 그림."""
    ai: bool = True
    tool: str = Field("", max_length=40)
    date: date
    module_code: str = Field("", max_length=30)
    number: str = Field("", max_length=10, pattern=r"^(\d+-\d+)?$")      # 그림 번호 '1-2'. 모듈 코드와 함께 적으면 수록 위치로 남는다
    by: str = Field("", max_length=80)


class RecommendChoiceRequest(BaseModel):
    """추천 선택 기록(REQ-02-011). 추천을 돌린 문단·수행준거와 그림, 선택(used 쓸 그림 / rejected 맞지 않음 / none 지움)."""
    text: str = Field("", max_length=4000)
    unit_code: str = Field("", max_length=30)
    criterion_no: str = Field("", max_length=10, pattern=r"^(\d+\.\d+)?$")
    image_id: str = Field(max_length=40)
    choice: Literal["used", "rejected", "none"]
    rank: int | None = Field(None, ge=1, le=100)
    score: float | None = None
    by: str = Field("", max_length=80)               # 로그인을 쓰지 않는 서버에서만 쓴다. 로그인했으면 계정 이름이 남는다
    detail: dict[str, Any] = Field(default_factory=dict)   # 그때의 근거(맞은 핵심어, 유사도 등) — 화면이 보낸 그대로 남긴다


class ImageRightsRequest(ImageActionRequest):
    """권리 정보 수정. rights의 모양은 이미지 레코드의 rights와 같다(docs/IMAGE_RECORD.md). null은 그 칸을 비운다."""
    rights: dict[str, Any]


class OpinionDecisionRequest(BaseModel):
    """의견 반영 검토의 담당자 확정(REQ-02-003 사람 작업 4) — 결과표 내려받기와 확정 저장이 함께 쓴다."""

    manuscript: str = ""
    rows: list[dict[str, Any]]                  # /api/opinion 응답의 '의견' 행
    decisions: dict[str, str] = {}              # 의견 번호 → "반영" | "미반영"
    record_id: str = ""                         # /api/opinion 응답의 '진행 현황 기록'.id — 있으면 그 기록에 확정을 적는다(DB 모드)
    llm: str = ""

