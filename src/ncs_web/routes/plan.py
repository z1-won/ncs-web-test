"""개발계획서 작성(REQ-02-001) — 초안을 만들 수 있는 세분류 목록과 초안 hwpx."""

import base64
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from ..common import Services, error_response
from ..schemas import ErrorResponse, PlanDraftRequest


def register(app: FastAPI, services: Services) -> None:
    @app.get("/api/plan/subclasses")
    def plan_subclasses() -> dict[str, Any]:
        """초안을 만들 수 있는 세분류 — 요소·수행준거 표(ncs_elements.tsv)에 받아 둔 것만. 능력단위마다 요소 수를 함께."""
        from ncs_core.ncs_catalog import catalog

        cat = catalog()
        if cat is None:
            return {"subclasses": [], "warning": "NCS 목록(ncs_units.tsv)이 없습니다"}
        by_duty: dict[str, list[dict]] = {}
        for unit in cat.element_units.values():
            by_duty.setdefault(unit["duty"], []).append(unit)
        out = []
        for duty, units in sorted(by_duty.items()):
            sub = cat.subclass(duty)
            out.append({
                "duty": duty,
                "name": sub.name if sub else duty,
                "classes": dict(sub.names) if sub else {},
                "units": [{"code": u["code"], "name": u["name"], "level": u["level"], "elements": len(u["elements"]),
                           "criteria": sum(len(e["criteria"]) for e in u["elements"])} for u in sorted(units, key=lambda u: u["code"])],
            })
        return {"subclasses": out, "build": "scripts/data/build_ncs_elements.py --duty <세분류코드>"}

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
