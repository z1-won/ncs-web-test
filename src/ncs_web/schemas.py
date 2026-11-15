"""API 요청·응답 모델. 경로 모듈(routes/)이 함께 쓴다."""

from typing import Any, Literal

from pydantic import BaseModel

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


class UploadResponse(BaseModel):
    """전체 실행용 업로드 토큰. upload를 /api/review에 files 대신 넘기면 같은 파일로 검수를 여러 번 돌릴 수 있다."""

    upload: str
    group: str                    # 이 토큰으로 실행한 검수들의 이력 묶음 id
    files: list[str]
    roles: dict[str, str | None]  # 역할 → 파일 이름(요청의 roles로 지정했으면 그대로, 아니면 넣은 순서). plan이 None이면 개발계획서 없음
    expires_in: int               # 초
