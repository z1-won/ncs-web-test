"""공통 파서로 문맥을 준비하고 평가 ①②③ 규칙을 실행한다."""
from collections.abc import Sequence
from dataclasses import replace
from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.documents import toc_title_index
from ncs_core.manuscript import parse_body, parse_overview, parse_plan_goals, parse_plan_toc, parse_toc, section_presence
from ncs_core.text import flatten
from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .region import eval_regions
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .sheet import sheet


def _after_toc(manuscript: Document, section: int) -> Document:
    """진짜 차례 제목 앞 문단을 비운 사본(문단 번호는 그대로). 개요 내용 체계를 읽을 때 쓴다.

    원고 앞부분의 'NCS학습모듈의 이해'(iii~vi쪽)에는 '2. NCS학습모듈의 개요' 제목과 예시 내용 체계 표
    ('촬영 구성안 검토와 수정' 등 — 모든 원고에 같은 예시)가 있어, 코어 parse_overview가 처음 나온 개요 제목을 따라
    예시 표를 읽는다(SW제품기획 최종본 10종 모두 평가 ① X, 한글 PDF로 확인). 실제 개요는 차례 뒤에 오므로
    차례 앞을 비워 같은 코어 함수가 실제 개요를 읽게 한다. 차례를 못 찾으면 원본 그대로.
    """
    paragraphs = manuscript.sections[section]
    toc = toc_title_index(paragraphs)
    if not toc:
        return manuscript
    sections = list(manuscript.sections)
    sections[section] = [""] * toc + list(paragraphs[toc:])
    tables = [t for t in manuscript.tables if not (t["section"] == section and t["paragraph"] < toc)]
    return replace(manuscript, sections=sections, tables=tables)


def prepare_review(manuscript: Document, plan: Document | None = None, *, module_code: str = "",
                   config: CheckConfig = DEFAULT_CONFIG) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if max(config.front_section, config.body_section) >= len(manuscript.sections):
        raise ValueError("지정한 차례/본문 섹션이 없습니다")
    sections = [manuscript.sections[config.front_section], manuscript.sections[config.body_section]]
    toc = parse_toc(sections)
    plan_toc = parse_plan_toc(plan, code) if plan else None
    overview = parse_overview(_after_toc(manuscript, config.front_section), config.front_section).get("내용체계")
    presence = section_presence(sections, [])
    body = parse_body(sections, len((toc or {}).get("학습", [])),
                      cutoff=presence["참고 자료"]["k"],
                      table_paragraphs=manuscript.section_table_paragraphs(config.body_section),
                      aside_paragraphs=manuscript.section_aside_paragraphs(config.body_section),
                      styles=manuscript.section_styles(config.body_section))
    regions = eval_regions(manuscript, body, config.body_section)
    plan_goals = parse_plan_goals(plan, code) if plan else None
    return ReviewContext(manuscript, plan, code, config, toc, overview, plan_toc, body, regions, plan_goals)


def _warnings(context: ReviewContext) -> list[str]:
    warnings = ["평가 ①②③⑤를 검사합니다(④ 미구현). 표 구조·학습 연결이 불명확하면 판단불가입니다."]
    if context.plan is None:
        warnings.append("개발계획서가 없어 ② 학습 목표 대조는 생략(-)입니다")
    elif context.plan_goals is None:
        warnings.append("개발계획서에서 이 모듈 코드의 블록을 찾지 못했습니다. ②는 생략(-)입니다")
    missing = [str(r["lesson"]) for r in context.regions if not r["found"]]
    if missing:
        warnings.append("평가 구역을 찾지 못한 학습: " + ", ".join(missing))
    return warnings


def evaluate_review(context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    checklist = run_rules(context, rules)
    implemented = [rule.item_prefix for rule in rules]
    diagnostics = {
        "module_code": context.module_code,
        "implemented": implemented,
        "not_implemented": [i for i in ALL_ITEM_IDS if i not in implemented],
        "warnings": _warnings(context),
        "counts": {"lessons": len(context.regions), "criteria_tables": sum(r["criteria_tables"] for r in context.regions),
                   "methods": sum(len(r["methods"]) for r in context.regions)},
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
