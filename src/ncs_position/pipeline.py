"""입력 선택 → 추출 → 규칙 실행. 저장과 화면 출력은 호출자가 결정한다.

prepare_review: 문서를 읽고 ReviewContext를 만든다.
evaluate_review: 규칙을 실행해 ReviewResult를 만든다.
run_review: 둘을 이어 붙인 편의 함수.
"""

from collections.abc import Sequence

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .parsers import find_styled_position_table, parse_classification, parse_plan_module_name, parse_position
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .sheet import sheet


def prepare_review(
    manuscript: Document,
    plan: Document,
    *,
    module_code: str = "",
    config: CheckConfig = DEFAULT_CONFIG,
) -> ReviewContext:
    if plan is None:
        raise ValueError("위치 검수에는 개발계획서가 필요합니다")
    code = resolve_module_code(manuscript.path, module_code)
    if config.front_section >= len(manuscript.sections):
        raise ValueError("지정한 위치 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    plan_lines = [l for section in plan.sections for l in section]
    front_lines = [l for l in manuscript.sections[config.front_section] if l]
    return ReviewContext(
        manuscript,
        plan,
        code,
        config,
        parse_classification(plan_lines),
        parse_classification(front_lines),
        parse_position(plan.tables),
        parse_position(manuscript.tables),
        find_styled_position_table(manuscript.tables) if manuscript.has_styles else None,
        parse_plan_module_name(plan.sections, code),
    )


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    warnings = []
    if len(context.plan_classification) < 3:
        warnings.append("개발계획서에서 대·중·소분류를 모두 읽지 못했습니다")
    if not context.plan_position["세분류"] and not context.plan_position["능력단위"]:
        warnings.append("개발계획서에서 세분류·능력단위·학습모듈명 표를 찾지 못했습니다")
    if context.plan_module_name is None:
        warnings.append("개발계획서 학습모듈명을 읽지 못해 ⑤의 해당 행은 모듈 코드 번호로 정합니다")
    if not context.manuscript.has_styles:
        warnings.append("hwp(바이너리)는 글꼴·음영을 읽지 않아 ⑤는 판단불가입니다")
    implemented = {rule.item_prefix for rule in rules}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(context.manuscript.path), "plan": str(context.plan.path)},
        "format": context.manuscript.format,
        "sections": {"front": context.config.front_section},
        "counts": {
            "classification": len(context.manuscript_classification),
            "subclasses": len(context.manuscript_position["세분류"]),
            "units": len(context.manuscript_position["능력단위"]),
            "modules": len(context.manuscript_position["학습모듈명"]),
        },
        "implemented": sorted(implemented),
        "not_implemented": [item for item in ALL_ITEM_IDS if not any(item[-1] in p for p in implemented)],
        "warnings": warnings,
    }


def evaluate_review(context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    """한 실행의 결과만 돌려준다. 같은 context를 다시 실행해도 이전 결과를 누적하지 않는다."""
    checklist = run_rules(context, rules)
    return ReviewResult(
        context.module_code, checklist, flatten(checklist), _diagnostics(context, rules), context, sheet(checklist)
    )


def run_review(
    paths,
    *,
    roles: dict | None = None,
    module_code: str = "",
    config: CheckConfig = DEFAULT_CONFIG,
    rules: Sequence[Rule] = DEFAULT_RULES,
) -> ReviewResult:
    """paths: 원고 1개 + 개발계획서 1개. roles={경로: 'manuscript'|'plan'}로 역할을 지정할 수 있다."""
    documents = select_documents(paths, roles, required=("manuscript", "plan"))
    context = prepare_review(documents["manuscript"], documents["plan"], module_code=module_code, config=config)
    return evaluate_review(context, rules=rules)
