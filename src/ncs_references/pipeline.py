"""참고 자료 구역(section_presence)을 찾아 항목과 본문 출처 줄을 읽고 ①②③ 규칙을 실행한다. 개발계획서는 쓰지 않는다."""

from collections.abc import Sequence

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.manuscript import section_presence
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .entries import collect_citations, collect_entries, find_short_reference_run
from .models import ReviewContext
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .sheet import sheet


def prepare_review(manuscript: Document, plan: Document | None = None, *, module_code: str = "",
                   config: CheckConfig = DEFAULT_CONFIG) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if max(config.front_section, config.body_section) >= len(manuscript.sections):
        raise ValueError("지정한 차례/본문 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    sections = [manuscript.sections[config.front_section], manuscript.sections[config.body_section]]
    body = config.body_section
    images = [(p, name) for s, p, name in manuscript.images if s == body]
    presence = section_presence(sections, images, figures=manuscript.section_figures(body), tables=manuscript.section_tables(body),
                                media_complete=manuscript.format == "hwpx")
    aside = manuscript.section_aside_paragraphs(body) or frozenset()
    if not (presence.get("참고 자료") or {}).get("있음"):
        guessed = find_short_reference_run(manuscript.sections[body], aside, manuscript.section_table_paragraphs(body) or frozenset())
        if guessed:
            presence = {**presence, "참고 자료": guessed}
    entries = collect_entries(manuscript.sections[body], presence, aside)
    start = (presence.get("참고 자료") or {}).get("k")
    citations = collect_citations(manuscript.sections[body], start, aside)
    return ReviewContext(manuscript, plan, code, config, presence, entries, citations)


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    found = context.presence.get("참고 자료") or {}
    warnings = []
    if not context.entries:
        warnings.append("참고 자료 항목을 찾지 못했습니다(구역 없음 또는 글머리 항목 없음). ①②③은 판단불가입니다")
    unreadable = [e["n"] for e in context.entries if e["key"] is None]
    if unreadable:
        warnings.append("저자(연도) 꼴을 읽지 못한 참고 자료 항목: " + ", ".join(f"{n}번" for n in unreadable[:8]))
    implemented = {rule.item_prefix for rule in rules}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(context.manuscript.path), "plan": str(context.plan.path) if context.plan else None},
        "format": context.manuscript.format,
        "sections": {"front": context.config.front_section, "body": context.config.body_section},
        "counts": {"entries": len(context.entries), "citations": len(context.citations),
                   "literature_citations": sum(1 for c in context.citations if c["literature"])},
        "reference_section": {"있음": found.get("있음"), "근거": found.get("근거"), "k": found.get("k"), "end": found.get("end")},
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
