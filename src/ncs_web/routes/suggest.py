"""원고 문장 추천(REQ-02-004) — 원고를 받아 구성별·문장별 정정 후보를, 또는 문장 하나를 받아 후보를 돌려준다. 계산은 ncs_suggest가 맡는다.

검수 결과처럼 저장하지 않는다: 올린 파일은 임시 폴더에서 읽고 바로 지운다. 채택/기각 기록은 화면이 갖고 내려받게 한다.
"""

import re
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, UploadFile

from ..common import Services, error_response
from ..schemas import ErrorResponse


def register(app: FastAPI, services: Services) -> None:
    @app.get("/api/suggest/kinds")
    def suggest_kinds() -> Any:
        """문장 종류와 규정 꼴(화면의 문장 직접 입력 선택지)."""
        from ncs_suggest import KINDS

        return {"종류": [{"이름": name, "규정 꼴": form} for name, form in KINDS.items()]}

    @app.post("/api/suggest", responses={400: {"model": ErrorResponse}})
    def suggest(manuscript: Annotated[UploadFile, File()], use_llm: Annotated[bool, Form()] = False) -> Any:
        """원고(hwp/hwpx) → 추천 카드(ncs_suggest.suggest_manuscript). use_llm: AI 후보도 묻기(설정·승인·허용 목록이 있을 때만 실제 호출)."""
        from ncs_suggest import suggest_manuscript

        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", Path(manuscript.filename or "원고.hwp").name).strip(" .") or "원고.hwp"
        with tempfile.TemporaryDirectory(prefix="ncs_suggest_") as folder:
            path = Path(folder) / name
            path.write_bytes(manuscript.file.read())
            try:
                return suggest_manuscript(path, use_llm=use_llm)
            except ValueError as error:
                return error_response(400, str(error))

    @app.post("/api/suggest/sentence", responses={400: {"model": ErrorResponse}})
    def suggest_one(
        text: Annotated[str, Form()],
        kind: Annotated[str, Form()],
        before: Annotated[str, Form()] = "",
        after: Annotated[str, Form()] = "",
        use_llm: Annotated[bool, Form()] = False,
    ) -> Any:
        """문장 하나 + 종류 → 추천 카드(ncs_suggest.suggest_sentence). before/after: AI 후보에 함께 보낼 앞뒤 문단(선택)."""
        from ncs_suggest import suggest_sentence

        try:
            return suggest_sentence(text, kind, before=before, after=after, use_llm=use_llm)
        except ValueError as error:
            return error_response(400, str(error))
