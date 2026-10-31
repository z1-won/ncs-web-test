"""입력 선택 → 추출 → 규칙 실행. 저장/화면 출력은 호출자가 결정한다."""
import re
from pathlib import Path
from .config import DEFAULT_CONFIG
from .documents import load_document
from .loader import detect_role
from .models import CheckContext, InspectionResult
from .parsers import parse_toc, parse_overview, parse_plan_toc, parse_body
from .presence import section_presence
from .registry import DEFAULT_RULES, run_rules
from .reporting import flatten

MODULE_CODE = re.compile(r"LM\d{10}_\d+v\d+(?!\d)")


def resolve_module_code(path, module_code=None):
    if module_code is not None:
        if not MODULE_CODE.fullmatch(module_code):
            raise ValueError("모듈코드 형식: LM + 10자리 숫자 + _연도v버전")
        return module_code
    matches = set(MODULE_CODE.findall(Path(path).name))
    if len(matches) != 1:
        raise ValueError("원고 파일명에서 모듈코드를 확정할 수 없습니다. module_code를 지정하세요")
    return matches.pop()


def select_documents(paths, roles=None):
    """roles={경로: 'plan' 또는 'manuscript'}로 자동 분류를 덮어쓸 수 있다."""
    roles = {str(Path(p).resolve()): r for p, r in (roles or {}).items()}
    documents = {}
    seen = set()
    for path in paths:
        key = str(Path(path).resolve())
        if key in seen:
            raise ValueError(f"같은 입력 파일이 중복 지정되었습니다: {path}")
        seen.add(key)
        document = load_document(path)
        role = roles.get(key, detect_role(document.sections))
        if role not in ("manuscript", "plan"):
            raise ValueError(f"파일 역할을 판단하지 못했습니다: {path}. roles로 역할을 지정하세요")
        if role in documents:
            raise ValueError(f"{role} 역할의 파일이 둘 이상입니다. 한 번에 원고 1개와 개발계획서 1개를 선택하세요")
        documents[role] = document
    if "manuscript" not in documents:
        raise ValueError("원고 파일이 필요합니다")
    unused = roles.keys() - seen
    if unused:
        raise ValueError(f"roles에 입력 목록에 없는 경로가 있습니다: {sorted(unused)}")
    return documents


def inspect_documents(manuscript, plan=None, *, module_code=None,
                      config=DEFAULT_CONFIG, rules=DEFAULT_RULES):
    code = resolve_module_code(manuscript.path, module_code)
    if config.front_section >= len(manuscript.sections) or config.body_section >= len(manuscript.sections):
        raise ValueError("지정한 차례/본문 섹션이 없습니다. 문서 구조와 CheckConfig를 확인하세요")
    # 기존 파서의 논리적 section0/section1에 양식의 실제 섹션을 연결한다.
    sections = [manuscript.sections[config.front_section], manuscript.sections[config.body_section]]
    toc = parse_toc(sections)
    if not toc or not toc["학습"]:
        raise ValueError("차례 또는 차례 학습명을 읽지 못했습니다. 양식과 섹션 설정을 확인하세요")
    overview = parse_overview(sections)
    plan_toc = parse_plan_toc(plan.sections, code) if plan else None
    banners = [(1, p, name) for s, p, name in manuscript.banners if s == config.body_section]
    presence = section_presence(sections, banners, config)
    body = parse_body(sections, len(toc["학습"]), cutoff=presence["참고 자료"]["k"], config=config)
    context = CheckContext(code, toc, overview, plan_toc, body, presence,
                           manuscript.tables.get(config.body_section, []))
    checklist = run_rules(context, rules)

    def actual_sections(value):
        if isinstance(value, str):
            return re.sub(r"section([01])\b", lambda m: "section" + str(
                config.front_section if m[1] == "0" else config.body_section), value)
        if isinstance(value, dict):
            return {k: actual_sections(v) for k, v in value.items()}
        if isinstance(value, list):
            return [actual_sections(v) for v in value]
        return value

    # 결과 영역과 근거의 섹션 표기를 실제 입력 섹션으로 맞춘다.
    for row in checklist:
        row["region_path"] = actual_sections(row["region_path"])
        row["비고"] = actual_sections(row["비고"])
        if row["item_id"] == "F02-차례-⑤":
            row["원고"] = actual_sections(row["원고"])
    warnings = []
    if not plan_toc:
        warnings.append("개발계획서가 없거나 해당 모듈 블록을 읽지 못했습니다")
    elif not plan_toc["학습명"] or not plan_toc["내용명"]:
        warnings.append("개발계획서 명칭을 일부만 읽었습니다. 항목별 비교 기준을 확인하세요")
    if not body["lessons"]:
        warnings.append("본문 학습 구간을 읽지 못했습니다. 평가 대조는 판단불가입니다")
    if not context.eval_tables:
        warnings.append("평가 표 셀 정보가 없어 문단 휴리스틱으로 비교합니다")
    if len(manuscript.sections) > 2:
        warnings.append("선택한 차례/개요 및 본문 섹션만 검사합니다. 다른 섹션에 이어진 본문은 검사하지 않습니다")
    diagnostics = {
        "module_code": code,
        "inputs": {"manuscript": str(manuscript.path), "plan": str(plan.path) if plan else None},
        "format": manuscript.format,
        "sections": {"front": config.front_section, "body": config.body_section},
        "counts": {"lessons": len(toc["학습"]), "contents": len(toc["내용"]),
                   "navigator_runs": len(body["nav_runs"]), "evaluation_tables": len(context.eval_tables)},
        "implemented": [r.item_id for r in rules],
        "not_implemented": ["F02-차례-" + n for n in ("②", "④", "⑦")
                            if "F02-차례-" + n not in {r.item_id for r in rules}],
        "warnings": warnings,
    }
    return InspectionResult(code, checklist, flatten(checklist), diagnostics, context)


def inspect_files(paths, *, roles=None, module_code=None, config=DEFAULT_CONFIG, rules=DEFAULT_RULES):
    documents = select_documents(paths, roles)
    return inspect_documents(documents["manuscript"], documents.get("plan"),
                             module_code=module_code, config=config, rules=rules)
