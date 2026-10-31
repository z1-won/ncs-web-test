"""입력 검증 → 추출 → 규칙 실행. 저장과 사용자 입력은 수행하지 않는다."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .common import flatten
from .content_rules import check_class3, check_position
from .emphasis_rules import check_emphasis, plan_module_name
from .inputs import validate_document_paths
from .loader import load_sections
from .models import Document, ReviewContext, ReviewResult
from .module_code import resolve_module_code
from .styles import load_table_formats
from .tables import load_tables


@dataclass(frozen=True)
class Rule:
    key: str
    evaluate: Callable[[ReviewContext], list[dict]]


def classification_rule(context: ReviewContext) -> list[dict]:
    return check_class3(context.plan.sections, context.manuscript.sections)


def position_rule(context: ReviewContext) -> list[dict]:
    return check_position(context.plan.tables, context.manuscript.tables)


def emphasis_rule(context: ReviewContext) -> list[dict]:
    return check_emphasis(
        context.manuscript.formatted_tables, context.module_code, context.module_name
    )


DEFAULT_RULES = (
    Rule("classification", classification_rule),
    Rule("position", position_rule),
    Rule("emphasis", emphasis_rule),
)


def load_document(path: str | Path, *, include_styles: bool = False) -> Document:
    path = Path(path)
    fmt, sections = load_sections(path)
    if not sections or not any(line for section in sections for line in section):
        raise ValueError(f"문단 텍스트를 추출하지 못했습니다: {path}")
    _, tables = load_tables(path)
    styles = load_table_formats(path) if include_styles else None
    return Document(path, fmt, sections, tables, styles)


def prepare_review(
    plan_path: str | Path, manuscript_path: str | Path, *, module_code: str = ""
) -> ReviewContext:
    validate_document_paths({"plan": plan_path, "manuscript": manuscript_path})
    code = resolve_module_code(manuscript_path, module_code)
    plan = load_document(plan_path)
    manuscript = load_document(manuscript_path, include_styles=True)
    return ReviewContext(plan, manuscript, code, plan_module_name(plan.sections, code))


def evaluate_review(
    context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES
) -> ReviewResult:
    """한 실행의 결과만 반환한다. 동일 context 재실행 시 이전 결과를 누적하지 않는다."""
    keys = [rule.key for rule in rules]
    if len(keys) != len(set(keys)):
        raise ValueError("중복된 검사 key가 있습니다.")
    checklist = []
    for rule in rules:
        checklist.extend(rule.evaluate(context))
    return ReviewResult(context.module_code, checklist, flatten(checklist))


def run_review(
    plan_path: str | Path,
    manuscript_path: str | Path,
    *,
    module_code: str = "",
    rules: Sequence[Rule] = DEFAULT_RULES,
) -> ReviewResult:
    context = prepare_review(plan_path, manuscript_path, module_code=module_code)
    return evaluate_review(context, rules=rules)
