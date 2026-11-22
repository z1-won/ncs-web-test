"""그림 검수(REQ-02-005)·그림 태깅(REQ-02-009) — 규칙만 쓰는 부분은 형식 검수 뒤 화면이 바로 부르고(API 비용 없음),
그림 판독(Claude)은 사용자가 '그림 판독'을 눌렀을 때만 실행한다(LLM 검토와 같은 원칙).

결과는 업로드 폴더 아래 _figures/에 남고 토큰과 함께 지워진다.
  _figures/result.json      005 행·요약 + 009 레코드·요약(규칙)
  _figures/images/<id>.png  그림(썸네일·원본)
  _figures/검수표.html       005 이미지별 검수표(인쇄하면 PDF)
  _figures/read.json        그림 판독 결과(누를 때만)
app.state.figure_vision: 테스트용 그림 모델 대역(ncs_figures.vision.FakeVision). 있으면 외부로 보내지 않고 그것을 쓴다.
"""

import json
import os
import time
import traceback
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..common import Services, error_response, logger

KIND_ORDER = {"고위험": 0, "확인 필요": 1, "문제없음": 2, "판정 안 함": 3}


def _preload() -> None:
    """서버를 띄울 때(주 스레드) 그림 모듈을 한 번 읽어 둔다.

    화면은 형식 검수 뒤 그림 결과와 그림 모델 상태를 동시에 부르고, FastAPI는 요청마다 다른 스레드에서 돈다.
    두 스레드가 ncs_figures를 처음으로 동시에 읽으면(패키지 __init__ → pipeline → vision 과 vision 직접 읽기가 엇갈려)
    _DeadlockError가 난다. 미리 읽어 두면 요청 스레드는 이미 읽힌 모듈만 쓴다.
    """
    try:
        import ncs_figures.db  # noqa: F401
        import ncs_figures.export  # noqa: F401
        import ncs_figures.marks  # noqa: F401
        import ncs_figures.pipeline  # noqa: F401
        import ncs_figures.reading  # noqa: F401
        import ncs_figures.report  # noqa: F401
        import ncs_figures.tagging  # noqa: F401
        import ncs_figures.vision  # noqa: F401
    except ImportError:
        pass   # 패키지가 없으면 요청 때 _call이 설치 안내를 돌려준다


def register(app: FastAPI, services: Services) -> None:
    uploads_store = services.uploads
    app.state.figure_vision = None
    app.state.figure_lookup = None       # 테스트용 DB 대조기(StubLookup). 없으면 FIG_DB·결과/figure_db.sqlite
    _preload()

    def _upload(token: str) -> tuple[Path, Path]:
        kept = uploads_store.touch(token)
        if kept is None:
            raise ValueError("업로드 토큰이 없거나 만료되었습니다. 파일을 다시 올려 주세요")
        name = (kept.roles or {}).get("manuscript")
        path = next((p for n, p in kept.files if n == name), None)
        if path is None:
            raise ValueError("업로드에서 원고를 찾지 못했습니다")
        if path.suffix.lower() not in (".hwpx", ".hwp"):
            raise ValueError("그림 검수는 hwpx·hwp 원고만 됩니다")
        return path, kept.directory / "_figures"

    def _call(action):
        try:
            return action()
        except ImportError as error:
            return error_response(500, f"그림 검수에 필요한 패키지가 없습니다(pip install -r requirements/web.txt): {error}")
        except ValueError as error:
            return error_response(400, str(error))
        except Exception as error:
            logger.exception("그림 검수 실패: %s", error)
            debug = {"traceback": traceback.format_exc()} if os.getenv("NCS_WEB_DEBUG") == "1" else {}
            return error_response(500, f"{type(error).__name__}: {error}", **debug)

    db_cache: dict = {}

    def _lookup():
        """④ DB 대조용 이미지 DB(FIG_DB 또는 결과/figure_db.sqlite). 없으면 None(④ 미실행). 파일이 바뀌면 다시 읽는다."""
        if app.state.figure_lookup is not None:
            return app.state.figure_lookup
        from ncs_figures.db import StubLookup, default_db_path
        path = default_db_path()
        if not path.is_file():
            return None
        stamp = path.stat().st_mtime
        if db_cache.get("key") != (str(path), stamp):
            db_cache.update(key=(str(path), stamp), lookup=StubLookup(path))
        return db_cache["lookup"]

    def _submissions(work: Path, token: str):
        """(검수용, 태깅용). 검수용 = 올린 제출 서류 + 출력본 PDF, 서류가 없으면 None(⑥⑦ 미실행).
        태깅용 = 서류가 없어도 출력본 PDF만 있으면 그것(쪽 번호)."""
        folder = work / "submissions"
        files = sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
        kept = uploads_store.get(token) if token else None
        prints = []
        if kept is not None:
            name = (kept.roles or {}).get("print")
            prints = [p for n, p in kept.files if n == name]
        if not files and not prints:
            return None, None
        from ncs_figures.submissions import read_documents
        read = read_documents([*files, *prints])
        return (read if files else None), read

    def _captions(work: Path):
        from ncs_figures.reading import RecordedCaptions
        path = work / "read.json"
        if not path.is_file():
            return RecordedCaptions({}, missing="그림 판독을 아직 하지 않음 — '그림 판독' 버튼을 전부로 실행")
        read = json.loads(path.read_text(encoding="utf-8"))
        judged = {f["image_id"]: f["캡션 판정"] for f in read.get("figures", []) if f.get("image_id") and f.get("캡션 판정")}
        return RecordedCaptions(judged, read.get("model", ""),
                                missing="이 그림은 아직 판독하지 않음 — '그림 판독' 버튼을 전부로 실행")

    def _rules(manuscript: Path, work: Path, module_code: str = "", token: str = "") -> dict:
        """규칙만(모델 없음): 005 검수 + 009 태깅. 한 번 만들면 다시 쓴다."""
        target = work / "result.json"
        if target.is_file():
            return json.loads(target.read_text(encoding="utf-8"))
        from ncs_figures.export import write_csv
        from ncs_figures.models import Resources
        from ncs_figures.pipeline import run_review
        from ncs_figures.report import write_html
        from ncs_figures.tagging import tag_manuscript
        started = time.perf_counter()
        work.mkdir(parents=True, exist_ok=True)
        from ncs_figures.marks import open_marks
        lookup = _lookup()
        marks = open_marks()                     # ② 그림 속 마크·저작권 문구 — 로컬 OCR(처음엔 그림당 1초쯤, 다음엔 캐시)
        submissions, for_tags = _submissions(work, token)  # ⑥⑦ 제출 서류(올렸을 때만) + 출력본 PDF(쪽수)
        captions = _captions(work)               # ③ 그림 판독 버튼으로 받은 캡션 판정 — 없으면 위험도 '판정 안 함'
        review = run_review(manuscript, module_code=module_code,
                            resources=Resources(lookup=lookup, marks=marks, submissions=submissions, asker=captions))
        write_html(review, work / "검수표.html", title=manuscript.stem)
        records, tag_summary = tag_manuscript(manuscript, images_dir=work / "images", submissions=for_tags)
        for record in records:
            module = record.pop("module", None)
            record["modules"] = [module["code"] or module["file"]] if module else []
            for use in record["uses"]:
                use["module_info"] = module
        write_csv(records, work / "figures.csv")
        # 행마다 '대체 후보'(그림 DB의 같은 주제 그림)는 파이프라인이 채운다 — CLI·검수표와 같은 값
        rows = sorted(review.rows, key=lambda r: (KIND_ORDER.get(r["위험도"], 3), r["item_id"]))
        result = {
            "manuscript": manuscript.name, "module_code": review.module_code,
            "review": {"summary": review.summary, "rows": rows},
            "tags": {"summary": tag_summary, "records": records},
            "db": lookup.size() if lookup is not None else None,
            "submissions": None if submissions is None else {
                "파일": submissions.files, "수록 현황 목록": len(submissions.status), "제작 목록": len(submissions.production),
                "이용허락 동의서": len(submissions.permissions), "초상권 동의서": submissions.portrait_consents,
                "AI 결과물 현황": len(submissions.ai), "출력본 PDF": submissions.print_pdf is not None,
                "목록에만 있음": review.summary.get("목록에만 있음", {})},
            "seconds": round(time.perf_counter() - started, 1),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        target.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return result

    @app.get("/api/uploads/{token}/figures")
    def figures_rules(token: str, module_code: str = "") -> Response:
        """형식 검수 뒤 화면이 바로 부른다 — 모델·외부 전송 없음. 원고 하나에 수 초~십수 초."""
        def action():
            manuscript, work = _upload(token)
            result = _rules(manuscript, work, module_code, token)
            uploads_store.touch(token)
            return JSONResponse(result)
        return _call(action)

    @app.post("/api/uploads/{token}/figures/submissions")
    def figures_submissions(token: str, files: Annotated[list[UploadFile], File()]) -> Response:
        """⑥⑦ 집필자 제출 서류(수록 현황 목록·제작 목록·이용허락 동의서·초상권 동의서·서약서, hwp·hwpx)를 올린다.
        올리면 규칙 결과를 지운다(다음에 부를 때 서류를 넣어 다시 만듦). 같은 이름은 덮어쓴다."""
        def action():
            manuscript, work = _upload(token)
            folder = work / "submissions"
            folder.mkdir(parents=True, exist_ok=True)
            for item in files:
                name = Path(item.filename or "").name
                if not name:
                    continue
                if Path(name).suffix.lower() not in (".hwp", ".hwpx"):
                    raise ValueError(f"제출 서류는 hwp·hwpx만 됩니다: {name}")
                (folder / name).write_bytes(item.file.read())
            (work / "result.json").unlink(missing_ok=True)       # 그림 검수는 화면이 다시 부를 때 서류를 넣어 만든다
            uploads_store.touch(token)
            return JSONResponse({"파일": sorted(p.name for p in folder.iterdir() if p.is_file())})
        return _call(action)

    @app.delete("/api/uploads/{token}/figures/submissions", status_code=204)
    def figures_submissions_clear(token: str) -> Response:
        def action():
            import shutil
            _, work = _upload(token)
            shutil.rmtree(work / "submissions", ignore_errors=True)
            (work / "result.json").unlink(missing_ok=True)
            return Response(status_code=204)
        return _call(action)

    @app.get("/api/uploads/{token}/figures/image/{image_id}.png")
    def figures_image(token: str, image_id: str) -> Response:
        def action():
            _, work = _upload(token)
            if not image_id.isalnum():
                raise ValueError("그림 id가 잘못됨")
            path = work / "images" / f"{image_id}.png"
            if not path.is_file():
                return error_response(404, "그림이 없습니다(양식 그림이거나 아직 그림 검수를 하지 않음)")
            return FileResponse(path, media_type="image/png")
        return _call(action)

    @app.get("/api/figures/db-image/{image_id}.png")
    def figures_db_image(image_id: str) -> Response:
        """DB에 있는 기존 그림(④에서 같다고 찾은 그림) — 원고 그림과 나란히 보이기 위함."""
        def action():
            lookup = _lookup()
            row = lookup.row(image_id) if lookup is not None and image_id.isalnum() else None
            path = Path(row["image_file"]) if row and row.get("image_file") else None
            if path is None or not path.is_file():
                return error_response(404, "DB에 그림 파일이 없습니다")
            return FileResponse(path, media_type="image/png")
        return _call(action)

    def _attachment(content: bytes, media: str, ascii_name: str, name: str) -> Response:
        return Response(content, media_type=media, headers={
            "Content-Disposition": f"attachment; filename={ascii_name}; filename*=UTF-8''{quote(name)}"})

    @app.get("/api/uploads/{token}/figures/report.html")
    def figures_report(token: str) -> Response:
        """005 이미지별 검수표 — 새 탭에서 열고 인쇄하면 PDF."""
        def action():
            manuscript, work = _upload(token)
            _rules(manuscript, work, token=token)
            return Response((work / "검수표.html").read_bytes(), media_type="text/html; charset=utf-8")
        return _call(action)

    @app.get("/api/uploads/{token}/figures/figures.csv")
    def figures_csv(token: str) -> Response:
        def action():
            manuscript, work = _upload(token)
            _rules(manuscript, work, token=token)
            return _attachment((work / "figures.csv").read_bytes(), "text/csv; charset=utf-8", "figures.csv", f"{manuscript.stem}_그림태깅.csv")
        return _call(action)

    @app.get("/api/uploads/{token}/figures/result.json")
    def figures_json(token: str) -> Response:
        def action():
            manuscript, work = _upload(token)
            _rules(manuscript, work, token=token)
            return _attachment((work / "result.json").read_bytes(), "application/json", "figures.json", f"{manuscript.stem}_그림검수.json")
        return _call(action)

    @app.get("/api/uploads/{token}/figures/memo")
    def figures_memo(token: str) -> Response:
        """005 확인 필요 이상 그림에 메모를 단 원고 사본. 원고 본문은 바꾸지 않는다."""
        def action():
            from ncs_service.annotate import annotate_hwpx
            manuscript, work = _upload(token)
            rows = _rules(manuscript, work, token=token)["review"]["rows"]
            content, summary = annotate_hwpx(manuscript.read_bytes(), rows, author="이미지 검수")
            response = _attachment(content, "application/hwp+zip", "figures_memo.hwpx", f"{manuscript.stem}_이미지검수메모.hwpx")
            response.headers["X-Memo-Summary"] = json.dumps(summary)
            return response
        return _call(action)

    # ---------------------------------------------------------------- 그림 판독(API)

    @app.get("/api/figures/vision-status")
    def figures_vision_status() -> Response:
        def action():
            from ncs_figures.vision import vision_status
            body = vision_status()
            if app.state.figure_vision is not None:
                body.update(available=True, problem=None, model=app.state.figure_vision.name)
            return JSONResponse(body)
        return _call(action)

    @app.get("/api/uploads/{token}/figures/read")
    def figures_read_previous(token: str) -> Response:
        def action():
            _, work = _upload(token)
            path = work / "read.json"
            if not path.is_file():
                return error_response(404, "아직 그림 판독을 하지 않았습니다")
            return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
        return _call(action)

    @app.post("/api/uploads/{token}/figures/read")
    def figures_read(token: str, limit: Annotated[int, Form()] = 5) -> Response:
        """본문 그림을 앞에서부터 limit장(0 = 전부) 판독 + 캡션 판정. 외부 전송이 허용된 그림만 보낸다(나머지는 '보내지 않음').
        끝나면 005 검수표를 다시 만든다 — ③ 판정이 들어가야 위험도가 정해진다."""
        def action():
            from ncs_core.documents import load_document
            from ncs_figures.config import FigureConfig
            from ncs_figures.pipeline import prepare_figures
            from ncs_figures.reading import read_and_judge
            from ncs_figures.vision import cost, load_dotenv, load_model, vision_status
            manuscript, work = _upload(token)
            model = app.state.figure_vision
            if model is None:
                status = vision_status()
                if not status["available"]:
                    raise ValueError(status["problem"])
                model = load_model()
            load_dotenv()
            cfg = FigureConfig()                      # 요청마다 새로 — FIG_TRANSFER_OTHERS를 그때 읽는다
            items = [i for i in prepare_figures(load_document(manuscript), cfg=cfg) if i.kind in ("본문 그림", "캡션 없는 그림")]
            chosen = items if int(limit) <= 0 else items[:min(int(limit), 200)]     # 0 = 전부(위험도를 정하려면 전부 필요)
            figures, totals = [], {"보냄": 0, "보내지 않음": 0, "새 호출": 0, "입력": 0, "출력": 0, "비용": 0.0, "실패": 0}
            started = time.perf_counter()
            for item in chosen:
                reading, caption = read_and_judge(item, model, module_name=manuscript.stem)
                sent = reading.get("status") != "미실행"
                totals["보냄" if sent else "보내지 않음"] += 1
                for call in (reading, caption):
                    if call.get("status") == "완료" and not call.get("cached"):
                        totals["새 호출"] += 1
                        totals["입력"] += call["usage"].get("input", 0)
                        totals["출력"] += call["usage"].get("output", 0)
                        totals["비용"] += cost(call["model"], call["usage"]) or 0.0
                    elif call.get("status") == "실패":
                        totals["실패"] += 1
                clean = lambda d: {k: v for k, v in d.items() if k != "usage"}  # noqa: E731
                figures.append({"image_id": item.image_id, "그림": item.ctx.figure_label, "캡션": item.ctx.caption,
                                "위치": item.ctx.region_path, "전송": {"값": item.transfer, "이유": item.transfer_reason},
                                "판독": clean(reading), "캡션 판정": clean(caption)})
            totals["비용"] = round(totals["비용"], 4)
            result = {"model": model.name, "본문 그림": len(items), "판독한 그림": len(chosen), "합계": totals, "figures": figures,
                      "seconds": round(time.perf_counter() - started, 1), "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "transfer_others": cfg.transfer_others}
            work.mkdir(parents=True, exist_ok=True)
            previous = json.loads((work / "read.json").read_text(encoding="utf-8")) if (work / "read.json").is_file() else {}
            key = lambda f: f.get("image_id") or f"{f.get('위치')}|{f.get('캡션')}"  # noqa: E731 — 그림을 못 읽은 자리도 남긴다
            kept = {key(f): f for f in previous.get("figures", [])}                  # 앞서 판독한 그림은 남긴다
            kept.update({key(f): f for f in figures})
            saved = {**result, "figures": list(kept.values())}
            (work / "read.json").write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
            (work / "result.json").unlink(missing_ok=True)       # 005 검수표를 ③ 판정을 넣어 다시 만든다
            uploads_store.touch(token)
            return JSONResponse(result)
        return _call(action)
