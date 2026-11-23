"""원고 문장 추천(REQ-02-004) — 원고를 받아 구성별·문장별 정정 후보를, 또는 문장 하나를 받아 후보를 돌려준다. 계산은 ncs_suggest가 맡는다.

검수 결과처럼 저장하지 않는다: 올린 파일은 임시 폴더에서 읽고 바로 지운다. 채택/기각 기록은 화면이 갖고 내려받게 한다.
채택한 문장은 /api/suggest/memo가 원고 hwpx의 그 문장 자리에 한글 메모로 달아 돌려준다(본문은 고치지 않는다, 파일은 저장하지 않는다).
"""

import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Response, UploadFile

from ..common import Services, error_response
from ..schemas import ErrorResponse


def register(app: FastAPI, services: Services) -> None:
    @app.get("/api/suggest/kinds")
    def suggest_kinds() -> Any:
        """문장 종류와 규정 꼴(화면의 문장 직접 입력 선택지)."""
        from ncs_suggest import KINDS

        return {"종류": [{"이름": name, "규정 꼴": form} for name, form in KINDS.items()]}

    @app.post("/api/suggest", responses={400: {"model": ErrorResponse}})
    def suggest(manuscript: Annotated[UploadFile, File()]) -> Any:
        """원고(hwp/hwpx) → 추천 카드(ncs_suggest.suggest_manuscript). 고칠 문장과 후보는 AI(Claude)가 낸다 — 서버에
        ANTHROPIC_API_KEY·반출 승인(LLM_ALLOW_UPLOAD=1)이 있으면 자동으로 부르고, 없으면 카드 없이 'AI 미설정 — 이유'(결과의 AI.상태)만
        낸다. 사용량은 AI.usage."""
        from ncs_suggest import suggest_manuscript

        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", Path(manuscript.filename or "원고.hwp").name).strip(" .") or "원고.hwp"
        with tempfile.TemporaryDirectory(prefix="ncs_suggest_") as folder:
            path = Path(folder) / name
            path.write_bytes(manuscript.file.read())
            try:
                return suggest_manuscript(path)
            except ValueError as error:
                return error_response(400, str(error))

    @app.post("/api/suggest/sentence", responses={400: {"model": ErrorResponse}})
    def suggest_one(
        text: Annotated[str, Form()],
        kind: Annotated[str, Form()],
        before: Annotated[str, Form()] = "",
        after: Annotated[str, Form()] = "",
    ) -> Any:
        """문장 하나 + 종류(+ 앞 문장·뒤 문장, 선택) → 추천 카드(ncs_suggest.suggest_sentence). AI를 부르지 못하면 '판단불가'와 이유.
        앞뒤 문장은 AI에 문맥으로만 보낸다(각 400자까지)."""
        from ncs_suggest import suggest_sentence

        try:
            return suggest_sentence(text, kind, before=before, after=after)
        except ValueError as error:
            return error_response(400, str(error))

    @app.post("/api/suggest/memo", responses={400: {"model": ErrorResponse}})
    def suggest_memo(
        manuscript: Annotated[UploadFile, File()],
        records: Annotated[str, Form()],
    ) -> Any:
        """원고 hwpx + 채택 기록(JSON 배열 — 화면의 채택 기록 행 가운데 채택한 것) → 채택 문장을 그 문장 자리에 한글 메모로 단 hwpx.
        본문은 고치지 않는다. 메모 요약(단 문장 수, 메모 수, 자리를 찾지 못한 문장)은 X-Memo-Summary 머리글."""
        from ncs_service.annotate import annotate_notes
        from ncs_suggest import MEMO_AUTHOR, memo_notes

        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", Path(manuscript.filename or "원고.hwpx").name).strip(" .") or "원고.hwpx"
        if not name.lower().endswith(".hwpx"):
            return error_response(400, "메모는 hwpx 원고에만 달 수 있습니다(hwp는 한글에서 hwpx로 저장 후 다시 올리세요)")
        try:
            notes, summary = memo_notes(json.loads(records))
        except ValueError as error:      # json.JSONDecodeError도 ValueError
            message = "채택 기록(records)은 JSON 배열이어야 합니다" if isinstance(error, json.JSONDecodeError) else str(error)
            return error_response(400, message)
        try:
            content, made = annotate_notes(manuscript.file.read(), notes, author=MEMO_AUTHOR, summary=summary)
        except (zipfile.BadZipFile, KeyError, SyntaxError):      # hwpx가 아니거나 섹션·머리 XML을 읽지 못함
            return error_response(400, "원고 hwpx를 읽지 못했습니다. 한글에서 hwpx로 다시 저장해 올리세요")
        filename = f"{Path(name).stem}_문장추천메모.hwpx"
        return Response(content, media_type="application/hwp+zip", headers={
            "Content-Disposition": f"attachment; filename=suggest_memo.hwpx; filename*=UTF-8''{quote(filename)}",
            "X-Memo-Summary": json.dumps(made),
        })
