"""원고 진행 현황(REQ-02-007 '원고별 편집·내용·저작권 검수 진행도 확인') — 원고(모듈 코드)마다 남아 있는 기록을 단계와 진행도로 보여 준다.

읽기 전용이다: 새로 받는 입력이 없고, 이미 남은 기록(원고 검수·개발계획서 점검 이력, 분량 산정 이력, 의견 반영 검토와 권리 증빙 점검의
개수 기록, 이미지 저작권 DB)만 모은다. 단계와 진행도를 만드는 일은 ncs_service.progress가 한다. 저장소가 이력을 지원할 때(PostgreSQL)만 붙는다.
"""

from fastapi import FastAPI, Query
from starlette.exceptions import HTTPException

from ..common import Services


def module_name(module_code: str) -> str:
    """NCS 목록에서 학습모듈(능력단위) 이름. 목록에 없으면 빈 값."""
    from ncs_core.ncs_catalog import catalog

    listing = catalog()
    unit = listing.unit(module_code.removeprefix("LM")) if listing else None
    return unit.name if unit else ""


def register(app: FastAPI, services: Services) -> None:
    store = services.store
    if not store.supports_history:
        return

    @app.get("/api/manuscripts")
    def manuscripts(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> list[dict]:
        """기록이 있는 원고 목록(최근 기록순): 모듈 코드, 학습모듈명, 처음·최근 기록 시각, 기록 수, 기록이 있는 단계 수(7단계 중)."""
        return [{**row, "name": module_name(row["module_code"])} for row in store.list_manuscripts(limit=limit, offset=offset)]

    @app.get("/api/manuscripts/{module_code}")
    def manuscript_progress(module_code: str) -> dict:
        """한 원고의 진행 현황: 단계 7개(기록으로 미룬 상태)와 편집·내용·저작권 검수 진행도, 분량."""
        from ncs_core import validate_module_code

        try:
            code = validate_module_code(module_code)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        found = store.get_progress(code, name=module_name(code))
        if found is None:
            raise HTTPException(404, "이 모듈 코드로 남은 기록이 없습니다")
        return found
