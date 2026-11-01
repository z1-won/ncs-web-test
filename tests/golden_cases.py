"""골든 테스트의 공통 정의: 어떤 입력 조합을 돌리고, 결과에서 무엇을 저장·비교하는가.

사례 = 네 엔진 × 합성 원고 6종 × 개발계획서 유/무 (위치는 계획서 필수이므로 유만) = 42건.
저장하는 것: 체크리스트·지적사항·검수확인서·진단(입력 경로 제외). 입력 경로는 실행 환경마다 다르므로 뺀다.
"""

import json
import os
from pathlib import Path

# 합성 원고·계획서는 실제 NCS와 다른 값을 쓰므로 NCS 목록을 끄고(개발계획서 기준) 돌린다. 목록 자체는 test_ncs_catalog가 검사한다.
os.environ.setdefault("NCS_CATALOG_FILE", str(Path(__file__).with_name("no_catalog.tsv")))

from ncs_service import ReviewRequest, execute_review
from ncs_service.registry import ENGINES

ROOT = Path(__file__).resolve().parents[1]

FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = ROOT / "tests" / "golden"


def cases():
    """(사례 이름, ReviewRequest) 목록. 이름이 골든 파일 이름이 된다."""
    plan = next(FIXTURES.glob("개발계획서_*.hwpx"))
    for manuscript in sorted(FIXTURES.glob("원고_*.hwpx")):
        for check, engine in ENGINES.items():
            for with_plan in (True, False):
                if "plan" in engine.required and not with_plan:
                    continue
                paths = (manuscript, plan) if with_plan else (manuscript,)
                yield f"{check}_{manuscript.stem}_{'plan' if with_plan else 'noplan'}", ReviewRequest(paths, check)


def observe(request: ReviewRequest) -> dict:
    """비교 대상이 되는 결과. 입력 오류도 결과의 일부로 기록한다."""
    try:
        result = execute_review(request).result
    except ValueError as error:
        return {"error": str(error)}
    diagnostics = {key: value for key, value in result.diagnostics.items() if key != "inputs"}
    return {
        "checklist": result.checklist,
        "findings": result.findings,
        "sheet": result.sheet,
        "diagnostics": diagnostics,
    }


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
