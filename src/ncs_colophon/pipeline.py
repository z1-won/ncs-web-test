"""본문 섹션의 표에서 개발 이력·판권 표를 읽고 ① 규칙을 실행한다. 개발계획서는 쓰지 않는다."""

from collections.abc import Sequence

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .sheet import sheet
from .tables import read_colophons, read_histories


def prepare_review(manuscript: Document, plan: Document | None = None, *, module_code: str = "",
                   config: CheckConfig = DEFAULT_CONFIG) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if max(config.front_section, config.body_section) >= len(manuscript.sections):
        raise ValueError("지정한 차례/본문 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    tables = manuscript.section_tables(config.body_section)
    return ReviewContext(manuscript, plan, code, config, read_histories(tables), read_colophons(tables))


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    warnings = []
    if not context.histories:
        warnings.append("'NCS학습모듈 개발이력' 표를 찾지 못했습니다")
    if not context.colophons:
        warnings.append("판권 표를 찾지 못했습니다")
    if context.manuscript.format != "hwpx":
        warnings.append("hwp는 표 셀 구조를 읽지 못할 수 있습니다. hwpx를 권장합니다")
    implemented = {rule.item_prefix for rule in rules}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(context.manuscript.path), "plan": str(context.plan.path) if context.plan else None},
        "format": context.manuscript.format,
        "sections": {"front": context.config.front_section, "body": context.config.body_section},
        "counts": {"history_tables": len(context.histories), "colophon_tables": len(context.colophons),
                   "history_blocks": sum(len(h["blocks"]) for h in context.histories)},
        "implemented": sorted(implemented),
        "not_implemented": [item for item in ALL_ITEM_IDS if item not in implemented],
        "warnings": warnings,
    }


def evaluate_review(context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    checklist = run_rules(context, rules)
    return ReviewResult(context.module_code, checklist, flatten(checklist), _diagnostics(context, rules), context, sheet(checklist))


def run_review(paths, *, roles: dict | None = None, module_code: str = "", config: CheckConfig = DEFAULT_CONFIG,
               rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    documents = select_documents(paths, roles, required=("manuscript",))
    context = prepare_review(documents["manuscript"], documents.get("plan"), module_code=module_code, config=config)
    return evaluate_review(context, rules=rules)
