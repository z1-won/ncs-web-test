"""입력 선택 → 수행 내용 블록 분할 → 규칙 실행. 저장과 화면 출력은 호출자가 결정한다.

개발계획서에는 수행 내용이 없으므로 ①④에 개발계획서는 쓰지 않는다(받아도 무시).
"""

from collections.abc import Sequence

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.text import flatten

from .blocks import split_perform_blocks
from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
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
    if config.body_section >= len(manuscript.sections):
        raise ValueError("지정한 본문 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    body = config.body_section
    styles = manuscript.section_styles(body)
    blocks = split_perform_blocks(
        manuscript.sections[body],
        styles=styles,
        table_paragraphs=manuscript.section_table_paragraphs(body),
        aside_paragraphs=manuscript.section_aside_paragraphs(body),
    )
    return ReviewContext(manuscript, plan, code, config, blocks, styles is not None)


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    manuscript, config = context.manuscript, context.config
    warnings = []
    if not context.blocks:
        warnings.append("본문에서 '수행 내용' 머리를 찾지 못했습니다. ①④는 판단불가입니다. 양식·섹션 설정을 확인하세요")
    if not context.has_styles:
        warnings.append("hwp 원고는 문단 스타일이 없어 네모 번호([1])를 첫 글자로 추정합니다. hwpx를 권장합니다")
    missing = [(b["block_id"], b["소제목 누락"]) for b in context.blocks if b["소제목 누락"]]
    if missing:
        warnings.append("소제목(재료·기기·안전·수행 순서)을 찾지 못한 블록: " + "; ".join(f"{bid}: {', '.join(m)}" for bid, m in missing[:5]))
    unknown_unit = [b["block_id"] for b in context.blocks if b["unit"] is None]
    if unknown_unit:
        warnings.append("소속 학습 내용(N-M.)을 찾지 못한 수행 내용: " + ", ".join(unknown_unit[:5]))
    if len(manuscript.sections) > 2:
        warnings.append("선택한 본문 섹션만 검사합니다. 다른 섹션에 이어진 본문은 검사하지 않습니다")
    implemented = {rule.item_prefix for rule in rules}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(manuscript.path), "plan": str(context.plan.path) if context.plan else None},
        "format": manuscript.format,
        "sections": {"front": config.front_section, "body": config.body_section},
        "counts": {
            "blocks": len(context.blocks),
            "units": len({b["unit"] for b in context.blocks if b["unit"]}),
            "level1_lines": sum(1 for b in context.blocks for s in b["수행순서"] if s.get("level1")),
        },
        "implemented": sorted(implemented),
        "not_implemented": [item for item in ALL_ITEM_IDS if item not in implemented],
        "warnings": warnings,
    }


def evaluate_review(context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    checklist = run_rules(context, rules)
    return ReviewResult(context.module_code, checklist, flatten(checklist), _diagnostics(context, rules), context, sheet(checklist))


def run_review(
    paths,
    *,
    roles: dict | None = None,
    module_code: str = "",
    config: CheckConfig = DEFAULT_CONFIG,
    rules: Sequence[Rule] = DEFAULT_RULES,
) -> ReviewResult:
    documents = select_documents(paths, roles, required=("manuscript",))
    context = prepare_review(documents["manuscript"], documents.get("plan"), module_code=module_code, config=config)
    return evaluate_review(context, rules=rules)
