"""공통 파서로 문맥을 준비하고 평가 ① 규칙을 실행한다."""
from collections.abc import Sequence
from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.manuscript import parse_body, parse_overview, parse_plan_toc, parse_toc, section_presence
from ncs_core.text import flatten
from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .sheet import sheet


def prepare_review(manuscript: Document, plan: Document | None = None, *, module_code: str = "",
                   config: CheckConfig = DEFAULT_CONFIG) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if max(config.front_section, config.body_section) >= len(manuscript.sections):
        raise ValueError("지정한 차례/본문 섹션이 없습니다")
    sections = [manuscript.sections[config.front_section], manuscript.sections[config.body_section]]
    toc = parse_toc(sections)
    plan_toc = parse_plan_toc(plan.sections, code) if plan else None
    overview = parse_overview(manuscript, config.front_section).get("내용체계")
    presence = section_presence(sections, [])
    body = parse_body(sections, len((toc or {}).get("학습", [])),
                      cutoff=presence["참고 자료"]["k"],
                      table_paragraphs=manuscript.section_table_paragraphs(config.body_section))
    return ReviewContext(manuscript, plan, code, config, toc, overview, plan_toc, body)


def evaluate_review(context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    checklist = run_rules(context, rules)
    implemented = [rule.item_prefix for rule in rules]
    diagnostics = {
        "module_code": context.module_code,
        "implemented": implemented,
        "not_implemented": [i for i in ALL_ITEM_IDS if i not in implemented],
        "warnings": ["평가 ①만 검사합니다. 표 구조·학습 연결이 불명확하면 판단불가입니다."],
        "inputs": {"manuscript": str(context.manuscript.path),
                   "plan": str(context.plan.path) if context.plan else None},
        "sections": {"front": context.config.front_section, "body": context.config.body_section},
    }
    return ReviewResult(context.module_code, checklist, flatten(checklist), diagnostics, context, sheet(checklist))


def run_review(paths, *, roles: dict | None = None, module_code: str = "",
               config: CheckConfig = DEFAULT_CONFIG, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    docs = select_documents(paths, roles, required=("manuscript",))
    context = prepare_review(docs["manuscript"], docs.get("plan"), module_code=module_code, config=config)
    return evaluate_review(context, rules=rules)
