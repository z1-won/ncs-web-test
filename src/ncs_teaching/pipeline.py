"""입력 선택 → 교수·학습 방법 블록 분할 → 규칙 실행. 개발계획서는 쓰지 않는다(받아도 무시)."""

from collections.abc import Sequence

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.text import flatten

from .blocks import split_teaching_blocks
from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .sheet import sheet


def prepare_review(manuscript: Document, plan: Document | None = None, *, module_code: str = "",
                   config: CheckConfig = DEFAULT_CONFIG) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if config.body_section >= len(manuscript.sections):
        raise ValueError("지정한 본문 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    body = config.body_section
    styles = manuscript.section_styles(body)
    blocks = split_teaching_blocks(
        manuscript.sections[body], styles=styles, numbers=manuscript.section_numbers(body),
        table_paragraphs=manuscript.section_table_paragraphs(body), aside_paragraphs=manuscript.section_aside_paragraphs(body),
    )
    return ReviewContext(manuscript, plan, code, config, blocks, styles is not None)


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    manuscript, config = context.manuscript, context.config
    warnings = []
    if not context.blocks:
        warnings.append("본문에서 '교수·학습 방법' 머리를 찾지 못했습니다. ①~④는 판단불가입니다")
    if not context.has_styles:
        warnings.append("hwp 원고는 문단 스타일·자동 글머리가 없어 텍스트의 글머리표(•)로만 항목을 셉니다. hwpx를 권장합니다")
    missing = [(b["block_id"], b["소제목 누락"]) for b in context.blocks if b["소제목 누락"]]
    if missing:
        warnings.append("소제목(교수 방법·학습 방법) 아래 항목이 없는 블록: " + "; ".join(f"{bid}: {', '.join(m)}" for bid, m in missing[:5]))
    odd = [b["block_id"] for b in context.blocks if b["lesson_line"] is not None and b["lesson_line"] != b["lesson"]]
    if odd:
        warnings.append("블록 순번과 본문의 '학습 N' 줄이 다른 교수·학습 방법 블록(순번을 학습 번호로 썼음): " + ", ".join(odd[:5]))
    implemented = {rule.item_prefix for rule in rules}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(manuscript.path), "plan": str(context.plan.path) if context.plan else None},
        "format": manuscript.format,
        "sections": {"front": config.front_section, "body": config.body_section},
        "counts": {"blocks": len(context.blocks),
                   "teach_items": sum(len(b["교수"]) for b in context.blocks),
                   "learn_items": sum(len(b["학습"]) for b in context.blocks)},
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
