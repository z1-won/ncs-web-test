"""개발계획서의 표를 읽고 ①~⑩ 규칙을 실행한다. 원고는 필요 없다(함께 있으면 모듈 코드 추출에만 쓴다)."""

from collections.abc import Sequence

from ncs_core.rules import coverage
from ncs_core import Document, ReviewResult, Rule, law_lookup, run_rules, select_documents, validate_module_code
from ncs_core.law_catalog import extract_law_names, law_catalog
from ncs_core.lexicon import default_lexicon
from ncs_core.module_code import CODE_IN_NAME
from ncs_core.ncs_catalog import catalog
from ncs_core.text import flatten

from .config import DEFAULT_CONFIG, CheckConfig
from .models import ReviewContext
from .parsers import is_module_table, read_plan
from .registry import ALL_ITEM_IDS, DEFAULT_RULES
from .rules.laws import law_texts
from .sheet import sheet


def _module_code(manuscript: Document | None, plan: Document, data: dict, override: str) -> str:
    """원고가 있으면 원고 파일명, 아니면 계획서 파일명, 아니면 총괄표(또는 모듈 표)의 첫 능력단위로 LM 코드를 만든다."""
    if override and override.strip():
        return validate_module_code(override)
    for path in (manuscript.path if manuscript else None, plan.path):
        if path is None:
            continue
        found = list(dict.fromkeys(CODE_IN_NAME.findall(str(path).rsplit("/", 1)[-1])))
        if len(found) == 1:
            return validate_module_code(found[0])
    for entry in data.get("총괄표") or []:
        if entry.get("LM 코드", "").startswith("LM"):
            try:
                return validate_module_code(entry["LM 코드"])
            except ValueError:
                continue
    for module in data.get("모듈") or []:
        try:
            return validate_module_code("LM" + module["코드"])
        except ValueError:
            continue
    raise ValueError("개발계획서에서 학습모듈 코드를 찾지 못했습니다. module_code를 지정하세요")


def prepare_review(manuscript: Document | None, plan: Document | None, *, module_code: str = "",
                   config: CheckConfig = DEFAULT_CONFIG) -> ReviewContext:
    if plan is None:
        raise ValueError("개발계획서 파일이 필요합니다")
    data = read_plan(plan.tables)
    cells = [text for table in plan.tables if is_module_table(table) for text in table["cells"].values() if text]
    code = _module_code(manuscript, plan, data, module_code)
    # ⑩의 기준(법령명 표)에 없는 법령명은 여기서 법제처에 조회해 표에 더한다. 조회할 수 있는 환경(인증 + 기준정보 폴더)에서만 —
    # 아니면 None이고 ⑩은 지금처럼 표에 있는 것만 판정한다. 나가는 것은 법령 이름뿐이다.
    names = [name for module in data["모듈"] for _where, text, _ncs in law_texts(module) for name, _quoted in extract_law_names(text)]
    lookup = law_lookup.ensure(names)
    return ReviewContext(manuscript, plan, code, config, data, catalog() if config.use_catalog else None, default_lexicon(), cells,
                         law_catalog(), lookup)


def _diagnostics(context: ReviewContext, rules: Sequence[Rule]) -> dict:
    data, warnings = context.data, []
    if not data["모듈"]:
        warnings.append("모듈 표(NCS 수정 금지 ⇰ NCS학습모듈)를 찾지 못했습니다")
    if data["총괄표"] is None:
        warnings.append("개발계획 총괄표를 찾지 못했습니다")
    if data["대조표"] is None:
        warnings.append("NCS 변경 전·후 대조표를 찾지 못했습니다")
    if context.catalog is None:
        warnings.append("NCS 목록을 읽지 못해 ①은 판단불가입니다")
    if context.laws is None:
        warnings.append("법령명 표(law_names.tsv)가 없어 ⑩은 판단불가입니다 — scripts/data/build_law_names.py")
    lookup = context.law_lookup
    if lookup and lookup["실패"]:
        warnings.append(f"법령명 {len(lookup['실패'])}건은 법제처 조회에 실패해 ⑩에서 확인하지 못했습니다({lookup['오류']}): " + ", ".join(lookup["실패"][:5]))
    if lookup and lookup["남김"]:
        warnings.append(f"법령명이 많아 {lookup['남김']}건은 이번에 조회하지 않았습니다. 다시 점검하면 이어서 조회합니다")
    return {
        "module_code": context.module_code,
        "stage": context.config.stage,
        "inputs": {"manuscript": str(context.manuscript.path) if context.manuscript else None, "plan": str(context.plan.path)},
        "format": context.plan.format,
        "기본": data["기본"],
        "counts": {"tables": len(context.plan.tables), "modules": len(data["모듈"]), "summary_rows": len(data["총괄표"] or []),
                   "change_rows": len(data["대조표"] or []),
                   "elements": sum(len(m["요소"]) for m in data["모듈"]), "lessons": sum(len(m["학습"]) for m in data["모듈"])},
        "modules": [{"코드": m["코드"], "명칭": m["명칭"], "요소": len(m["요소"]), "학습": len(m["학습"])} for m in data["모듈"]],
        **coverage(rules, ALL_ITEM_IDS),
        **({"법령 조회": {"새로 조회": lookup["조회"], "실패": lookup["실패"]}} if lookup else {}),   # 조회하는 환경에서만 싣는다
        "warnings": warnings,
    }


def evaluate_review(context: ReviewContext, *, rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    checklist = run_rules(context, rules)
    return ReviewResult(context.module_code, checklist, flatten(checklist), _diagnostics(context, rules), context, sheet(checklist))


def run_review(paths, *, roles: dict | None = None, module_code: str = "", config: CheckConfig = DEFAULT_CONFIG,
               rules: Sequence[Rule] = DEFAULT_RULES) -> ReviewResult:
    documents = select_documents(paths, roles, required=("plan",))
    context = prepare_review(documents.get("manuscript"), documents["plan"], module_code=module_code, config=config)
    return evaluate_review(context, rules=rules)
