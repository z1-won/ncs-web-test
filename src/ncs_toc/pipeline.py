"""입력 선택 → 추출 → 규칙 실행. 저장과 화면 출력은 호출자가 결정한다.

prepare_review: 문서를 읽고 ReviewContext를 만든다.
evaluate_review: 규칙을 실행해 ReviewResult를 만든다.
run_review: 둘을 이어 붙인 편의 함수.
"""

import re
from collections.abc import Sequence
from typing import Any

from ncs_core import Document, ReviewResult, Rule, resolve_module_code, run_rules, select_documents
from ncs_core.manuscript import parse_body, parse_overview, parse_plan_toc, parse_toc, section_presence
from ncs_core.manuscript.pages import locate_headings
from ncs_core.pdf import PdfDocument
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .evaluation import evaluation_tables
from .models import ReviewContext
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .rules.action_nouns import unknown_words
from .sheet import sheet


def prepare_review(
    manuscript: Document,
    plan: Document | None = None,
    *,
    module_code: str = "",
    config: CheckConfig = DEFAULT_CONFIG,
    print_copy: PdfDocument | None = None,
) -> ReviewContext:
    code = resolve_module_code(manuscript.path, module_code)
    if max(config.front_section, config.body_section) >= len(manuscript.sections):
        raise ValueError("지정한 차례/본문 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    # 파서의 논리적 section0(차례·개요)/section1(본문)에 양식의 실제 섹션을 연결한다.
    sections = [manuscript.sections[config.front_section], manuscript.sections[config.body_section]]
    toc = parse_toc(sections)
    if not toc or not toc["학습"]:
        raise ValueError("차례 또는 차례 학습명을 읽지 못했습니다. 양식과 섹션 설정을 확인하세요")
    # 내용체계는 표 우선으로 읽는다(개요·필요지식 엔진과 같은 파서). 셀 안에서 '1-1.'과 명칭이 두 문단으로 갈려도 읽힌다.
    overview = parse_overview(manuscript, config.front_section).get("내용체계")
    plan_toc = parse_plan_toc(plan, code) if plan else None
    images = [(p, name) for s, p, name in manuscript.images if s == config.body_section]
    parse_config = config.parse_config()
    presence = section_presence(sections, images, parse_config, figures=manuscript.section_figures(config.body_section),
                                tables=manuscript.section_tables(config.body_section),
                                media_complete=manuscript.format == "hwpx")
    body = parse_body(
        sections, len(toc["학습"]), cutoff=presence["참고 자료"]["k"], config=parse_config,
        table_paragraphs=manuscript.section_table_paragraphs(config.body_section),
        aside_paragraphs=manuscript.section_aside_paragraphs(config.body_section),
        styles=manuscript.section_styles(config.body_section),
    )
    eval_tables = evaluation_tables(manuscript.section_tables(config.body_section))
    headings = print_error = None
    if print_copy is not None:
        try:
            headings = locate_headings(print_copy)
        except ValueError as error:  # 출력본은 선택 입력이라 검수를 멈추지 않고 ⑦만 판단불가로 둔다
            print_error = f"출력본을 읽지 못함 ({error})"
    return ReviewContext(manuscript, plan, code, config, toc, overview, plan_toc, body, presence, eval_tables,
                         print_copy, headings, print_error)


def _actual_sections(value: Any, config: CheckConfig) -> Any:
    """결과의 'section0/section1' 표기를 실제 입력 섹션 번호로 바꾼다."""
    if isinstance(value, str):
        return re.sub(
            r"section([01])\b",
            lambda m: "section" + str(config.front_section if m[1] == "0" else config.body_section),
            value,
        )
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
    if broken := context.toc.get("쪽 깨짐"):
        warnings.append(
            f"차례 쪽 번호가 '?'(상호 참조 미갱신)인 줄 {len(broken)}개({', '.join(broken)}) — "
            "한글에서 필드 갱신(F9 등) 후 다시 검수하세요"
        )
    if not context.plan_toc:
        warnings.append("개발계획서가 없거나 해당 모듈 블록을 읽지 못했습니다")
    elif not context.plan_toc["학습명"] or not context.plan_toc["내용명"]:
        warnings.append("개발계획서 명칭을 일부만 읽었습니다. 항목별 비교 기준을 확인하세요")
    if not context.body["lessons"]:
        warnings.append("본문 학습 구간을 읽지 못했습니다. 평가 대조와 ④ 교수·학습 방법/평가 위치는 판단불가입니다")
    if not context.eval_tables:
        warnings.append("평가 표 셀 정보가 없어 문단 휴리스틱으로 비교합니다")
    if context.print_copy is None:
        warnings.append("출력본 PDF가 없어 ⑦ 차례 쪽수는 판단불가입니다. 원고를 한글에서 PDF로 저장해 함께 올리면 확정합니다")
    elif context.print_error:
        warnings.append(context.print_error)
    elif context.print_copy.module_code and context.print_copy.module_code != context.module_code:
        warnings.append(f"출력본의 모듈 코드({context.print_copy.module_code})가 원고와 다릅니다")
    if len(manuscript.sections) > 2:
        warnings.append("선택한 차례/개요 및 본문 섹션만 검사합니다. 다른 섹션에 이어진 본문은 검사하지 않습니다")
    implemented = {rule.item_prefix for rule in rules}
    return {
        "module_code": context.module_code,
        "inputs": {"manuscript": str(manuscript.path), "plan": str(plan.path) if plan else None,
                   "print": str(context.print_copy.path) if context.print_copy else None},
        "format": manuscript.format,
        "sections": {"front": config.front_section, "body": config.body_section},
        "counts": {
            "lessons": len(context.toc["학습"]),
            "contents": len(context.toc["내용"]),
            "navigator_runs": len(context.body["nav_runs"]),
            "evaluation_tables": len(context.eval_tables),
            "print_pages": len(context.print_copy.pages) if context.print_copy else None,
        },
        "implemented": sorted(implemented),
        "not_implemented": [item for item in ALL_ITEM_IDS if item not in implemented],
        "warnings": warnings,
    }


def evaluate_review(context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    """한 실행의 결과만 돌려준다. 같은 context를 다시 실행해도 이전 결과를 누적하지 않는다."""
    config = context.config
    checklist = run_rules(context, rules)
    for row in checklist:
        row["region_path"] = _actual_sections(row["region_path"], config)
        row["비고"] = _actual_sections(row["비고"], config)
        if row["item_id"] == "F02-차례-⑤":
            row["원고"] = _actual_sections(row["원고"], config)
    diagnostics = _diagnostics(context, rules)
    # ②에서 목록에 없어 △로 남은 머리어. scripts/data/build_action_nouns.py --from-results 가 이 키를 읽는다.
    diagnostics["행동명사 미확인"] = unknown_words(checklist)
    return ReviewResult(context.module_code, checklist, flatten(checklist), diagnostics, context, sheet(checklist))


def run_review(
    paths,
    *,
    roles: dict | None = None,
    module_code: str = "",
    config: CheckConfig = DEFAULT_CONFIG,
    rules: Sequence[Rule] = DEFAULT_RULES,
) -> ReviewResult:
    """paths: 원고 1개 + 선택적 개발계획서 1개 + 선택적 출력본 PDF 1개. roles={경로: 'manuscript'|'plan'}로 역할을 지정할 수 있다."""
    documents = select_documents(paths, roles, required=("manuscript",))
    manuscript, plan = documents["manuscript"], documents.get("plan")
    context = prepare_review(manuscript, plan, module_code=module_code, config=config, print_copy=documents.get("print"))
    return evaluate_review(context, rules=rules)
