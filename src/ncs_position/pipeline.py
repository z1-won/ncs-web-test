"""입력 선택 → 추출 → 규칙 실행. 저장과 화면 출력은 호출자가 결정한다.

prepare_review: 문서를 읽고 ReviewContext를 만든다.
evaluate_review: 규칙을 실행해 ReviewResult를 만든다.
run_review: 둘을 이어 붙인 편의 함수.
"""

from collections.abc import Sequence

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.ncs_catalog import catalog
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .parsers import find_styled_position_table, parse_classification, parse_plan_module_name, parse_position
from .patterns import MODULE_CODE_PARTS
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
    plan_classification, plan_position = parse_classification(plan_lines), parse_position(plan.tables)
    reference_classification, reference_position, source = catalog_reference(code)
    if reference_position is None:
        reference_classification, reference_position, source = plan_classification, plan_position, "개발계획서"
    elif plan_position["세분류"]:
        # ② 소분류의 세분류 목록: '학습모듈 분류보기'에는 학습모듈이 개발된 세분류만 있어 전체 목록이 아니다(온디바이스AIoT처럼
        # 신설 세분류가 빠짐). 개발계획서가 세분류 목록을 적었으면 그것을 쓴다.
        reference_position = {**reference_position, "세분류": plan_position["세분류"]}
    module_name, module_name_source = resolve_module_name(code, plan.sections, reference_position, source)
    return ReviewContext(
        manuscript,
        plan,
        code,
        config,
        reference_classification,
        parse_classification(front_lines),
        reference_position,
        parse_position(manuscript.tables),
        find_styled_position_table(manuscript.tables) if manuscript.has_styles else None,
        module_name,
        source,
        plan_classification if source != "개발계획서" else None,
        plan_position if source != "개발계획서" else None,
        module_name_source,
    )


def reference_module_name(position: dict | None, module_code: str) -> str | None:
    """기준 위치 표(NCS 목록 또는 개발계획서)에서 이 모듈의 학습모듈명 — 모듈 코드의 능력단위 번호(LM……EE)째 행.

    위치 표의 능력단위·학습모듈명 열은 세분류의 능력단위를 NCS 순서로 나열하므로 EE번째가 이 모듈이다(학습모듈명 열이 비면 능력단위명).
    """
    parts = MODULE_CODE_PARTS.match(module_code or "")
    if not parts or not position:
        return None
    names = position.get("학습모듈명") or position.get("능력단위") or []
    index = int(parts.group(5)) - 1
    return names[index] if 0 <= index < len(names) else None


def resolve_module_name(module_code: str, plan_sections, reference_position: dict, source: str) -> tuple[str | None, str]:
    """⑤의 '해당 행'을 고를 학습모듈명과 그 출처.

    1) 개발계획서 모듈 블록의 '학습 모듈명' 칸 → 2) NCS 목록의 능력단위 코드(10자리) → 3) 기준 위치 표의 EE번째 행.
    셋 다 없으면 (None, '없음')이고 규칙은 코드 번호 순번으로 돌아간다(기존 동작).
    """
    name = parse_plan_module_name(plan_sections, module_code)
    if name:
        return name, "개발계획서"
    cat = catalog()
    unit = cat.unit(module_code) if cat and source == "NCS 목록" else None
    if unit:
        return unit.name, "NCS 목록"
    name = reference_module_name(reference_position, module_code)
    if name:
        return name, f"{source} 위치 표"
    return None, "없음"


def catalog_reference(module_code: str) -> tuple[dict | None, dict | None, str]:
    """NCS 목록에서 이 모듈의 세분류를 찾아 위치 표의 기준값을 만든다. 없으면 (None, None, '').

    세분류 목록 = 같은 소분류의 세분류(코드 순), 능력단위·학습모듈명 = 세분류의 능력단위명(NCS 학습모듈명은 능력단위명을 쓴다).
    """
    cat = catalog()
    sub = cat.subclass(module_code) if cat else None
    if sub is None:
        return None, None, ""
    names = [u.name for u in sub.units]
    position = {
        "세분류": [s.name for s in cat.subclasses_of_small(sub.code)],
        "능력단위": names,
        "학습모듈명": names,
        "행쌍": [(n, n) for n in names],
    }
    return dict(sub.names), position, "NCS 목록"


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    warnings = []
    basis = context.reference_source
    if len(context.plan_classification) < 3:
        warnings.append(f"{basis}에서 대·중·소분류를 모두 읽지 못했습니다")
    if not context.plan_position["세분류"] and not context.plan_position["능력단위"]:
        warnings.append(f"{basis}에서 세분류·능력단위·학습모듈명 표를 찾지 못했습니다")
    if basis == "개발계획서":
        warnings.append("NCS 목록에 이 세분류가 없어 개발계획서를 기준으로 비교했습니다 (scripts/build_ncs_catalog.py로 목록 갱신)")
    if context.plan_module_name is None:
        warnings.append("개발계획서 학습모듈명을 읽지 못해 ⑤의 해당 행은 모듈 코드 번호로 정합니다")
    elif context.module_name_source != "개발계획서":
        warnings.append(f"개발계획서 학습모듈명을 읽지 못해 ⑤의 해당 행은 {context.module_name_source}의 「{context.plan_module_name}」로 정합니다")
    if not context.manuscript.has_styles:
        warnings.append("hwp(바이너리)는 글꼴·음영을 읽지 않아 ⑤는 판단불가입니다")
    implemented = {rule.item_prefix for rule in rules}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(context.manuscript.path), "plan": str(context.plan.path)},
        "format": context.manuscript.format,
        "reference": context.reference_source,
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
