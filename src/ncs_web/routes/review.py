"""검수 실행 — 상태(/api/health), 업로드 토큰(/api/uploads), 검수 1건(/api/review). 실행·저장은 ncs_service에 맡긴다."""

import os
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Response, UploadFile
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from ..common import Services, error_response, logger, parse_roles
from ..schemas import CheckName, ErrorResponse, ReviewResponse, SavedPaths, UploadResponse


def register(app: FastAPI, services: Services) -> None:
    from ncs_core import select_documents
    from ncs_core.pictures import DEFAULT_TARGET_DPI, DPI_CHOICES
    from ncs_service import ReviewRequest, execute_review
    from ncs_service.registry import ENGINES, describe_engines

    store, uploads_store = services.store, services.uploads

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        # history: 이력 API(/api/reviews)가 등록되어 있는가. 화면이 이력 영역을 켤지 결정하는 데 쓴다.
        # engines: 검수 항목마다 구성요소 이름과 구현된 확인서 항목 번호 — 화면의 선택 목록 글이 여기서 나온다
        # image_dpi: 이미지 해상도 기준의 선택지와 기본값 — 화면의 선택 칸(원고 검수·업스케일링)이 같은 값을 쓴다
        return {"ok": True, "checks": list(ENGINES), "engines": describe_engines(), "history": store.supports_history,
                "image_db": store.supports_history,   # 이미지 저작권 DB API(/api/images)가 등록되어 있는가 — 이력과 같이 PostgreSQL일 때만
                "image_dpi": {"choices": list(DPI_CHOICES), "default": DEFAULT_TARGET_DPI}}

    @app.post(
        "/api/uploads", response_model=UploadResponse,
        responses={400: {"model": ErrorResponse}},
    )
    def create_upload(
        files: Annotated[list[UploadFile], File()],
        roles: Annotated[str, Form()] = "",   # 업로드 칸이 정한 역할: files와 같은 순서의 JSON 배열. 없으면 넣은 순서(원고 → 개발계획서)
    ) -> UploadResponse | JSONResponse:
        """전체 실행 1단계: 파일을 한 번만 올려 두고 토큰을 받는다. 역할(원고/개발계획서/출력본)은 roles로 지정한 대로,
        지정하지 않으면 넣은 순서(원고 → 개발계획서)로 정해 함께 알려 준다. 지정한 역할은 이 토큰으로 돌리는 검수에도 그대로 쓴다."""
        try:
            named = [item for item in files if item.filename]   # 파일을 고르지 않은 빈 입력 칸은 역할 개수에 세지 않는다
            given = parse_roles(roles, len(named))
            upload = uploads_store.put([(item.filename or "", item.file.read()) for item in named])
            try:
                if given is not None:
                    if len(upload.files) != len(given):
                        raise ValueError("빈 파일이 있어 역할을 맞출 수 없습니다. 파일을 확인하세요")
                    upload.assigned = {str(path): role for (_, path), role in zip(upload.files, given)}
                # 역할을 미리 확인해 두면 화면이 '개발계획서 없음 → 위치 건너뜀'을 실행 전에 알 수 있다
                documents = select_documents([path for _, path in upload.files], upload.assigned or None, required=())
            except ValueError:
                uploads_store.release(upload.token)
                raise
            names = dict(upload.files)
            by_path = {str(path): name for name, path in upload.files}
            upload.roles = {role: by_path.get(str(document.path)) for role, document in documents.items()}
            upload.roles.setdefault("manuscript", None)
            upload.roles.setdefault("plan", None)
            upload.roles.setdefault("print", None)
            return UploadResponse(upload=upload.token, group=upload.group_id, files=list(names),
                                  roles=upload.roles, expires_in=int(uploads_store.ttl))
        except ValueError as error:
            return error_response(400, str(error))

    @app.delete("/api/uploads/{token}", status_code=204)
    def delete_upload(token: str) -> Response:
        """전체 실행이 끝나면 화면이 바로 지운다. 지우지 않아도 만료 시간이 지나면 정리된다."""
        if not uploads_store.release(token):
            raise HTTPException(404, "업로드 토큰이 없거나 만료되었습니다")
        return Response(status_code=204)

    @app.post(
        "/api/review", response_model=ReviewResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    def review(
        files: Annotated[list[UploadFile] | None, File()] = None,
        check: Annotated[CheckName, Form()] = "position",
        module_code: Annotated[str, Form()] = "",
        upload: Annotated[str, Form()] = "",
        group: Annotated[str, Form()] = "",
        stage: Annotated[str, Form()] = "",     # 개발계획서 점검(plan) 단계: final / draft. 다른 검수는 무시
        roles: Annotated[str, Form()] = "",     # files로 직접 올릴 때만: files와 같은 순서의 역할 JSON 배열. 없으면 넣은 순서(검수 종류의 필수 역할 먼저)
        work_stage: Annotated[str, Form()] = "",  # 원고 진행 현황의 단계(2 초고본·3 수정본·6 최종본). 비우면 단계 없이 남긴다. 개발계획서 점검은 무시
        image_dpi: Annotated[str, Form()] = "",  # 이미지 해상도 기준(150/300). 기타(misc) 검수의 ⑤·⑧에만 쓰이고 다른 검수는 무시. 비우면 기본값
    ) -> ReviewResponse | JSONResponse:
        """files로 직접 올리거나, /api/uploads 토큰(upload)으로 올려 둔 파일을 쓴다. group은 이력 묶음 id(토큰 응답의 group).
        토큰으로 실행하면 업로드 때 정한 역할을 그대로 쓴다."""
        # 동기 엔진은 일반 def 경로 함수의 스레드풀에서 실행한다.
        try:
            marked = _work_stage(work_stage) if check != "plan" else None
            if upload:
                kept = uploads_store.get(upload)
                if kept is None:
                    raise ValueError("업로드 토큰이 없거나 만료되었습니다. 파일을 다시 올려 주세요")
                if group and group != kept.group_id:
                    raise ValueError("group이 업로드 토큰의 묶음 id와 다릅니다")
                # group을 보내지 않으면 단독 실행(묶음 없음) — 화면이 파일을 미리 올려 두고 토큰만으로 1건 돌리는 경우
                if roles:
                    raise ValueError("roles는 업로드할 때 지정합니다. upload 토큰과 함께 보낼 수 없습니다")
                payload = _run(kept.files, check, module_code, group or None, stage=stage, roles=kept.assigned or None, image_dpi=image_dpi,
                               work_stage=marked, version_id=kept.version_id)
            else:
                if group:
                    raise ValueError("group은 upload 토큰과 함께만 쓸 수 있습니다")
                with tempfile.TemporaryDirectory(prefix="ncs_upload_") as folder:
                    saved = []
                    named = [item for item in files or [] if item.filename]
                    given = parse_roles(roles, len(named))
                    assigned: dict[str, str] = {}
                    for index, item in enumerate(named):
                        name = Path(item.filename).name
                        if name in ("", ".", ".."):
                            raise ValueError("유효하지 않은 업로드 파일명입니다")
                        # 동일 파일명도 서로 덮어쓰지 않으며 모듈 코드 추출용 원래 이름은 보존한다.
                        directory = Path(folder) / str(index)
                        directory.mkdir()
                        path = directory / name
                        with path.open("wb") as target:
                            shutil.copyfileobj(item.file, target)
                        if path.stat().st_size:
                            saved.append((name, path))
                            if given is not None:
                                assigned[str(path)] = given[index]
                    if not saved:
                        raise ValueError("업로드된 파일이 없습니다")
                    payload = _run(saved, check, module_code, None, stage=stage, roles=assigned or None, image_dpi=image_dpi, work_stage=marked)
        except ValueError as error:
            return error_response(400, str(error))
        except Exception as error:
            # 전체 traceback(서버 경로·내부 구조)은 서버 로그에만 남긴다. 응답에 실어 보내는 것은 NCS_WEB_DEBUG=1일 때뿐.
            logger.exception("검수 실행 실패: %s", error)
            debug = {"traceback": traceback.format_exc()} if os.getenv("NCS_WEB_DEBUG") == "1" else {}
            return error_response(500, f"{type(error).__name__}: {error}", **debug)
        return payload

    def _work_stage(value: str) -> int | None:
        from ncs_service.progress import REVIEW_STAGES

        if not value.strip():
            return None
        if value.strip() not in {str(no) for no in REVIEW_STAGES}:
            raise ValueError("work_stage는 " + " / ".join(f"{no}({name})" for no, name in REVIEW_STAGES.items()) + " 중 하나여야 합니다")
        return int(value)

    def _run(saved: list[tuple[str, Path]], check: str, module_code: str, group_id: str | None, *, stage: str = "",
             roles: dict[str, str] | None = None, image_dpi: str = "", work_stage: int | None = None, version_id: str = "") -> ReviewResponse:
        paths = tuple(path for _, path in saved)
        config = None
        if check == "plan" and stage:
            from ncs_plan import CheckConfig as PlanConfig

            config = PlanConfig(stage=stage)
        if check == "misc" and image_dpi:
            from ncs_misc import CheckConfig as MiscConfig

            if image_dpi not in {str(choice) for choice in DPI_CHOICES}:
                raise ValueError("image_dpi는 " + " / ".join(str(choice) for choice in DPI_CHOICES) + " 중 하나여야 합니다")
            config = MiscConfig(target_dpi=int(image_dpi))
        execution = execute_review(ReviewRequest(paths, check, module_code.strip(), roles=roles, config=config))
        result = execution.result
        stored = store.save(execution, saved, group_id=group_id)
        if work_stage is not None and stored.run_id is not None:
            try:
                store.tag_review_stage(stored.run_id, work_stage)
            except Exception as error:      # 단계 표시는 부가 정보라 검수 결과를 막지 않는다
                logger.exception("검수 단계 표시 실패: %s", error)
        if version_id and stored.run_id is not None:     # 세분류 건의 판본으로 돌린 검수 — 그 판본에 붙인다. 붙이지 못하면 근거가 끊기므로 실패로 알린다
            from ncs_service import cases

            cases.tag_review_version(store.dsn, stored.run_id, version_id)
        saved_paths = (
            SavedPaths(folder=str(stored.directory), zip=str(stored.zip_path))
            if stored.directory is not None else None
        )
        return ReviewResponse(
            id=stored.run_id, group=group_id, check=execution.check, module_code=result.module_code, 요약=stored.summary,
            검수확인서=result.sheet, 진단=result.diagnostics, 지적사항=result.findings,
            전체=result.checklist, 저장=saved_paths,
        )
