"""공통 파서(차례·본문·학습 내용 구간·꼬리 영역)로 문맥을 만들고 기타 ①②⑥⑦ 규칙을 실행한다. 개발계획서는 쓰지 않는다."""

from collections.abc import Sequence

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.manuscript import parse_body, parse_toc, section_presence, unit_regions
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .sheet import sheet


def prepare_review(manuscript: Document, plan: Document | None = None, *, module_code: str = "",
                   config: CheckConfig = DEFAULT_CONFIG) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if max(config.front_section, config.body_section) >= len(manuscript.sections):
        raise ValueError("지정한 차례/본문 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    sections = [manuscript.sections[config.front_section], manuscript.sections[config.body_section]]
    toc = parse_toc(sections)
    if not toc or not toc["학습"]:
        raise ValueError("차례 또는 차례 학습명을 읽지 못했습니다. 양식과 섹션 설정을 확인하세요")
    images = [(p, name) for s, p, name in manuscript.images if s == config.body_section]
    presence = section_presence(sections, images, figures=manuscript.section_figures(config.body_section),
                                tables=manuscript.section_tables(config.body_section), media_complete=manuscript.format == "hwpx")
    body = parse_body(sections, len(toc["학습"]), cutoff=presence["참고 자료"]["k"],
                      table_paragraphs=manuscript.section_table_paragraphs(config.body_section),
                      aside_paragraphs=manuscript.section_aside_paragraphs(config.body_section))
    units = unit_regions(body)
    return ReviewContext(manuscript, plan, code, config, toc, body, units, presence)


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    manuscript = context.manuscript
    warnings = []
    if manuscript.format != "hwpx":
        warnings.append("hwp 원고는 쪽 나누기·그림 개체를 읽을 수 없어 ①②가 판단불가입니다. hwpx를 권장합니다")
    if not context.units:
        warnings.append("학습 내용(N-M) 구간을 찾지 못해 ⑥은 판단불가입니다")
    implemented = {rule.item_prefix for rule in rules}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(manuscript.path), "plan": str(context.plan.path) if context.plan else None},
        "format": manuscript.format,
        "sections": {"front": context.config.front_section, "body": context.config.body_section},
        "counts": {"lessons": len(context.body["lessons"]), "units": len(context.units),
                   "pictures": len(manuscript.section_pictures(context.config.body_section)),
                   "page_breaks": len(manuscript.section_page_breaks(context.config.body_section) or ())},
        "presence": {name: bool((context.presence.get(name) or {}).get("있음")) for name in ("참고 자료", "활용 서식", "부록")},
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
