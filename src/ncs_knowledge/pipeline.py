"""입력 선택 → 추출 → 규칙 실행. 저장과 화면 출력은 호출자가 결정한다. (ncs_toc.pipeline과 같은 구조)

추출은 공통 파서를 쓴다:
  차례·본문·참고 자료 위치: ncs_core.manuscript (parse_toc / parse_body / section_presence)
  내용체계 표:             ncs_core.manuscript.parse_overview
  계획서 학습 목표:        ncs_knowledge.plan
  그림·표 캡션:            ncs_knowledge.figtab.collect_labels
"""

import re
from collections.abc import Sequence
from typing import Any

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.manuscript import parse_body, parse_overview, parse_toc, section_presence
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .figtab import _flatten, collect_labels
from .models import ReviewContext
from .plan import parse_plan_goals
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .structure import unit_regions
from .sheet import sheet


def prepare_review(
    manuscript: Document,
    plan: Document | None = None,
    *,
    module_code: str = "",
    config: CheckConfig = DEFAULT_CONFIG,
) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if max(config.front_section, config.body_section) >= len(manuscript.sections):
        raise ValueError("지정한 차례/본문 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    parse_config = config.parse_config()
    sections = [manuscript.sections[config.front_section], manuscript.sections[config.body_section]]
    toc = parse_toc(sections)
    if not toc or not toc["학습"]:
        raise ValueError("차례 또는 차례 학습명을 읽지 못했습니다. 양식과 섹션 설정을 확인하세요")
    overview = parse_overview(manuscript, config.front_section).get("내용체계")
    images = [(p, name) for s, p, name in manuscript.images if s == config.body_section]
    presence = section_presence(sections, images, parse_config, figures=manuscript.section_figures(config.body_section))
    body = parse_body(
        sections, len(toc["학습"]), cutoff=presence["참고 자료"]["k"], config=parse_config,
        table_paragraphs=manuscript.section_table_paragraphs(config.body_section),
    )
    units = unit_regions(body, config)
    plan_goals = parse_plan_goals(plan, code) if plan else None
    table_paragraphs = manuscript.section_table_paragraphs(config.body_section)
    aside = manuscript.section_aside_paragraphs(config.body_section) or frozenset()
    flat = _flatten(sections, exclude={(1, i) for i in aside})  # 메모·머리말 안 캡션은 세지 않음
    caps, refs, bare = collect_labels(flat)
    position = {(s, i): k for k, (s, i, _) in enumerate(flat)}
    lesson_spans = [
        (no, position[(1, body["lines"][a][0])], position[(1, body["lines"][b][0])] if b < len(body["lines"]) else len(flat))
        for no, a, b in body["spans"]
    ]
    labels = {"flat": flat, "caps": caps, "refs": refs, "bare": bare, "lesson_spans": lesson_spans}
    return ReviewContext(manuscript, plan, code, config, toc, overview, body, units, plan_goals, table_paragraphs, labels)


def _actual_sections(value: Any, config: CheckConfig) -> Any:
    if isinstance(value, str):
        return re.sub(r"section([01])\b", lambda m: "section" + str(config.front_section if m[1] == "0" else config.body_section), value)
    if isinstance(value, dict):
        return {k: _actual_sections(v, config) for k, v in value.items()}
    if isinstance(value, list):
        return [_actual_sections(v, config) for v in value]
    return value


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    manuscript, plan, config = context.manuscript, context.plan, context.config
    warnings = []
    for skipped in context.toc.get("건너뜀", []):
        warnings.append(
            f"차례에서 '학습 {skipped['no']}. {skipped['text']}' 줄을 학습으로 받지 않았습니다"
            f"(학습 {skipped['기대']}을 기대). 번호가 건너뛰었거나 중복됐습니다. 이후 학습이 누락될 수 있습니다"
        )
    if not plan:
        warnings.append("개발계획서가 없어 ⑤ 학습 목표 대조는 생략(-)입니다")
    elif not context.plan_goals:
        warnings.append("개발계획서에서 이 모듈 코드의 블록을 찾지 못했습니다. ⑤는 생략(-)입니다")
    elif not context.plan_goals["내용"]:
        warnings.append("개발계획서 학습 내용·학습 목표를 읽지 못했습니다")
    if not context.body["nav_runs"]:
        warnings.append("내비게이터 묶음을 찾지 못했습니다. ①②③은 판단불가, 학습 구간이 필요한 ④⑤⑥⑦도 영향을 받습니다")
    if context.overview is None:
        warnings.append("'학습모듈의 내용체계' 표를 읽지 못했습니다. ③④의 내용체계 대조는 판단불가입니다")
    if context.table_paragraphs is None:
        warnings.append("hwp 원고는 표 안 문단을 구분하지 않아 ⑥⑧에서 표 안 번호·출처도 함께 셉니다")
    if len(manuscript.sections) > 2:
        warnings.append("선택한 차례/개요 및 본문 섹션만 검사합니다")
    implemented = {rule.item_prefix for rule in rules}
    implemented_items = [item for item in ALL_ITEM_IDS if any(item.startswith(p) for p in implemented)]
    labels = context.labels
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(manuscript.path), "plan": str(plan.path) if plan else None},
        "format": manuscript.format,
        "sections": {"front": config.front_section, "body": config.body_section},
        "counts": {
            "lessons": len(context.toc["학습"]),
            "contents": len(context.toc["내용"]),
            "navigator_runs": len(context.body["nav_runs"]),
            "units": len(context.units),
            "plan_goal_sentences": sum(len(v["goals"]) for v in context.plan_goals["내용"].values()) if context.plan_goals else 0,
            "captions": len(labels["caps"]),
            "references": len(labels["refs"]),
            "bare_labels": len(labels["bare"]),
            "table_paragraphs": len(context.table_paragraphs) if context.table_paragraphs is not None else None,
        },
        "implemented": implemented_items,
        "not_implemented": [item for item in ALL_ITEM_IDS if item not in implemented_items],
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
