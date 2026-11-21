"""개발계획서 작성(REQ-02-001) — 세분류 목록, 세분류의 능력단위(없으면 NCS에서 받아 오기), 초안 hwpx."""

import base64
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from ..common import Services, error_response, logger
from ..schemas import ErrorResponse, PlanDraftRequest


def _units(units: list[dict]) -> list[dict]:
    return [{"code": u["code"], "name": u["name"], "level": u["level"], "elements": len(u["elements"]),
             "criteria": sum(len(e["criteria"]) for e in u["elements"])} for u in sorted(units, key=lambda u: u["code"])]


def _detail(cat, duty: str) -> dict | None:
    """세분류 한 건: 분류 이름, 요소·수행준거를 받아 둔 능력단위(ready), 받아 온 날. NCS 목록에도 받아 둔 표에도 없으면 None."""
    sub = cat.subclass(duty)
    units = cat.units_with_detail(duty)
    if sub is None and not units:
        return None
    dates = sorted({u["fetched"] for u in units if u.get("fetched")})
    return {
        "duty": duty, "name": sub.name if sub else duty, "classes": dict(sub.names) if sub else {},
        "ready": bool(units), "units": _units(units),
        # 받아 두지 않은 세분류는 NCS 목록의 능력단위 이름만 안다(요소·수행준거는 받아 와야 한다)
        "listed": [{"code": u.code, "name": u.name} for u in sub.units] if sub else [],
        "fetched": dates[-1] if dates else None,
    }


def register(app: FastAPI, services: Services) -> None:
    @app.get("/api/plan/subclasses")
    def plan_subclasses() -> dict[str, Any]:
        """세분류 목록(NCS 목록 전부) — 초안을 바로 만들 수 있는지(ready: 요소·수행준거를 받아 둠)와 능력단위 수.
        can_fetch가 참이면 ready가 아닌 세분류도 /fetch로 NCS에서 받아 와 쓸 수 있다. 능력단위 상세는 /api/plan/subclasses/{duty}."""
        from ncs_core.ncs_catalog import catalog
        from ncs_core.ncs_fetch import can_fetch

        cat = catalog()
        if cat is None:
            return {"subclasses": [], "can_fetch": False, "warning": "NCS 목록(ncs_units.tsv)이 없습니다"}
        ready: dict[str, int] = {}
        for unit in cat.element_units.values():
            ready[unit["duty"]] = ready.get(unit["duty"], 0) + 1
        out = []
        for duty in sorted(set(cat.subclasses) | set(ready)):
            sub = cat.subclass(duty)
            out.append({"duty": duty, "name": sub.name if sub else duty, "classes": dict(sub.names) if sub else {},
                        "ready": duty in ready, "units": ready.get(duty) or (len(sub.units) if sub else 0)})
        return {"subclasses": out, "can_fetch": can_fetch()}

    @app.get("/api/plan/subclasses/{duty}", responses={404: {"model": ErrorResponse}})
    def plan_subclass(duty: str) -> Any:
        from ncs_core.ncs_catalog import catalog

        cat = catalog()
        found = _detail(cat, duty[:8]) if cat is not None else None
        if found is None:
            return error_response(404, f"세분류 {duty}를 NCS 목록에서 찾지 못했습니다")
        return found

    @app.post("/api/plan/subclasses/{duty}/fetch", responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}})
    def plan_subclass_fetch(duty: str, refresh: bool = False) -> Any:
        """세분류의 요소·수행준거를 NCS(공공데이터포털)에서 받아 기준정보 폴더에 둔다. 이미 받아 둔 세분류는 refresh=true일 때만 다시 받는다.
        응답은 세분류 상세 + 변화({추가, 삭제, 변경}: 다시 받았을 때 전과 달라진 능력단위) + 처음(처음 받았는가)."""
        from ncs_core.ncs_api import NcsApiError
        from ncs_core.ncs_catalog import catalog
        from ncs_core.ncs_fetch import can_fetch, refresh_duty

        duty = duty[:8]
        if not re.fullmatch(r"\d{8}", duty):
            return error_response(400, "세분류 코드는 숫자 8자리입니다")
        cat = catalog()
        current = _detail(cat, duty) if cat is not None else None
        if current and current["ready"] and not refresh:
            return {**current, "변화": None, "처음": False}
        if not can_fetch():
            return error_response(400, "이 서버는 NCS에서 기준정보를 받아 오도록 설정되어 있지 않습니다. 관리자에게 문의해 주세요.")
        try:
            done = refresh_duty(duty)
        except NcsApiError as error:
            logger.warning("NCS 기준정보 받기 실패(%s): %s", duty, error)
            return error_response(502, "NCS에서 기준정보를 받아 오지 못했습니다. 잠시 후 다시 시도해 주세요. 계속되면 관리자에게 문의해 주세요.")
        return {**_detail(catalog(), duty), "변화": done["변화"], "처음": done["처음"]}

    @app.post("/api/plan/draft", responses={400: {"model": ErrorResponse}})
    def plan_draft(body: PlanDraftRequest) -> Any:
        """개발계획서 초안 hwpx와 그 초안의 ①~⑩ 점검 요약을 함께 준다: {filename, content(base64 hwpx), check}.
        요약은 능력단위가 많으면 10KB를 넘어 응답 헤더에 실을 수 없다(프록시의 헤더 한도) — 본문으로 보낸다."""
        from ncs_plan import CheckConfig as PlanConfig
        from ncs_plan import run_review
        from ncs_plan.fill import build_plan, spec_from_catalog

        try:
            units = [u[8:10] for u in body.units] or None
            spec = spec_from_catalog(body.duty, units=units, agency=body.agency)
            spec["기본"]["영문 세분류명"] = body.english
            spec["총괄표"] = [{"코드": m["코드"], "명칭": m["명칭"], "LM 코드": f"LM{m['코드']}", "LM 명칭": m["명칭"],
                            "집필진": body.writers.get(m["코드"], ""), "검토진": body.reviewers.get(m["코드"], "")} for m in spec["모듈"]]
            content = build_plan(spec)
        except ValueError as error:
            return error_response(400, str(error))
        summary: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="ncs_plan_draft_") as folder:
            path = Path(folder) / f"개발계획서_초안_{body.duty}.hwpx"
            path.write_bytes(content)
            try:
                result = run_review([path], config=PlanConfig(stage="draft"))   # 초안은 1차 문서 — 기관 기재 칸은 해당 없음
                summary = [{k: r.get(k, "") for k in ("구성요소", "번호", "체크 항목", "검수결과", "비고")} for r in result.sheet]
            except ValueError as error:   # 점검이 실패해도 초안은 준다
                summary = [{"구성요소": "개발계획서", "번호": "", "체크 항목": "점검 실행", "검수결과": "오류", "비고": str(error)}]
        return {"filename": f"개발계획서_초안_{body.duty}.hwpx", "content": base64.b64encode(content).decode("ascii"), "check": summary}
