"""규칙 등록. 개발계획서 ①~⑩."""

from ncs_core import Rule

from .rules.front import check_catalog, check_change_table, check_identity, check_required
from .rules.laws import check_laws
from .rules.module import check_element_codes, check_goal, check_lessons, check_subs, check_targets


def _each_module(fn):
    def run(context):
        rows = []
        for module in context.data["모듈"]:
            rows.extend(fn(module))
        return rows
    return run


def _no_module_rows(no: str):
    def run(context):
        if context.data["모듈"]:
            return []
        label = f"{no} 모듈 표"
        return [{"item_id": f"PLAN-{no}", "region_path": "개발계획서", "위치": "", "원고": None, "체크": {label: "△"}, "판정": "판단불가",
                 "비고": {label: "모듈 표(NCS 수정 금지 ⇰ NCS학습모듈)를 읽지 못해 판단할 수 없음"}, "수정 제안": None}]
    return run


def _module_rule(no: str, fn):
    each = _each_module(fn)
    fallback = _no_module_rows(no)
    return lambda context: each(context) + fallback(context)


DEFAULT_RULES = (
    Rule("catalog", "PLAN-①", lambda c: check_catalog(c.data, c.catalog if c.config.use_catalog else None)),
    Rule("identity", "PLAN-②", lambda c: check_identity(c.data, draft=c.config.stage == "draft")),
    Rule("goal", "PLAN-③", _module_rule("③", check_goal)),
    Rule("lessons", "PLAN-④", _module_rule("④", check_lessons)),
    Rule("element_codes", "PLAN-⑤", _module_rule("⑤", check_element_codes)),
    Rule("targets", "PLAN-⑥", _module_rule("⑥", check_targets)),
    Rule("subs", "PLAN-⑦", lambda c: _module_rule("⑦", lambda m: check_subs(m, c.lexicon, draft=c.config.stage == "draft"))(c)),
    Rule("required", "PLAN-⑧", lambda c: check_required(c.data, c.module_cells, draft=c.config.stage == "draft")),
    Rule("change_table", "PLAN-⑨", lambda c: check_change_table(c.data)),
    Rule("laws", "PLAN-⑩", lambda c: _module_rule("⑩", lambda m: check_laws(m, c.laws))(c)),
)
ALL_ITEM_IDS = tuple(f"PLAN-{n}" for n in "①②③④⑤⑥⑦⑧⑨⑩")
