"""입력 선택 → 추출 → 규칙 실행. 저장과 화면 출력은 호출자가 결정한다. (ncs_toc.pipeline과 같은 구조)"""

import re
from collections.abc import Sequence
from typing import Any

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .parsers import parse_overview, parse_plan
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .sheet import sheet


def prepare_review(
    manuscript: Document,
    plan: Document | None = None,
    *,
    module_code: str = "",
    config: CheckConfig = DEFAULT_CONFIG,
) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if config.front_section >= len(manuscript.sections):
        raise ValueError("지정한 개요 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    overview = parse_overview(manuscript, config.front_section)
    if overview["개요 제목 p"] is None and not any(overview.get(k) for k in ("목표", "선수학습", "내용체계", "핵심 용어")):
        raise ValueError("학습모듈의 개요를 읽지 못했습니다. 양식과 섹션 설정을 확인하세요")
    plan_info = parse_plan(plan, code) if plan else None
    return ReviewContext(manuscript, plan, code, config, overview, plan_info)


def _actual_sections(value: Any, config: CheckConfig) -> Any:
    if isinstance(value, str):
        return re.sub(r"section0\b", f"section{config.front_section}", value)
    if isinstance(value, dict):
        return {k: _actual_sections(v, config) for k, v in value.items()}
    if isinstance(value, list):
        return [_actual_sections(v, config) for v in value]
    return value


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    manuscript, plan, overview = context.manuscript, context.plan, context.overview
    warnings = []
    if plan and not context.plan_info:
        warnings.append("개발계획서에서 이 모듈 코드의 블록을 찾지 못했습니다. ①⑤⑥ 대조는 생략·판단불가입니다")
    elif not plan:
        warnings.append("개발계획서가 없어 ①⑤⑥의 개발계획서 대조는 생략·판단불가입니다")
    elif not context.plan_info["요소"] or not context.plan_info["학습명"]:
        warnings.append("개발계획서 요소 코드 또는 학습명을 읽지 못했습니다")
    for key in ("목표", "선수학습", "내용체계", "핵심 용어"):
        if not overview.get(key):
            warnings.append(f"개요의 '{key}' 블록을 읽지 못했습니다")
    implemented = {rule.item_prefix for rule in rules}
    structure = overview.get("내용체계") or {}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(manuscript.path), "plan": str(plan.path) if plan else None},
        "format": manuscript.format,
        "sections": {"front": context.config.front_section},
        "counts": {
            "prerequisites": len(overview["선수학습"]["items"]) if overview.get("선수학습") else 0,
            "lessons": len(structure.get("학습", [])),
            "contents": len(structure.get("내용", [])),
            "elements": len(structure.get("요소", [])),
            "terms": len(overview["핵심 용어"]["items"]) if overview.get("핵심 용어") else 0,
        },
        "implemented": sorted(implemented),
        "not_implemented": [item for item in ALL_ITEM_IDS if item not in implemented],
        "warnings": warnings,
    }


def evaluate_review(context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    config = context.config
    checklist = run_rules(context, rules)
    for row in checklist:
        row["region_path"] = _actual_sections(row["region_path"], config)
        row["비고"] = _actual_sections(row["비고"], config)
    diagnostics = _diagnostics(context, rules)
    return ReviewResult(context.module_code, checklist, flatten(checklist), diagnostics, context, sheet(checklist))


def run_review(
    paths,
    *,
    roles: dict | None = None,
    module_code: str = "",
    config: CheckConfig = DEFAULT_CONFIG,
    rules: Sequence[Rule] = DEFAULT_RULES,
) -> ReviewResult:
    documents = select_documents(paths, roles, required=("manuscript",))
    manuscript, plan = documents["manuscript"], documents.get("plan")
    context = prepare_review(manuscript, plan, module_code=module_code, config=config)
    return evaluate_review(context, rules=rules)
