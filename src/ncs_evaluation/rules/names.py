"""평가 ①: 번호 기반 명칭 비교와 평가 준거/방법의 독립 검사. 추정 일치는 사용하지 않는다."""
import re

from ncs_core import O, X, TRI, verdict

ITEM_ID = "F02-평가-①"
NUMBERED = re.compile(r"^(\d+)\s*-\s*(\d+)\s*\.\s*(.+)$")


def clean(text):
    # 어휘·문장부호·단어 사이 공백은 보존한다. 연속 공백/줄바꿈만 축약한다.
    return re.sub(r"\s+", " ", text).strip()


def row(place, value, actual=None, expected=None, note=""):
    checks = {"학습 내용명 일치": value}
    return {"item_id": ITEM_ID, "region_path": place, "원고": actual, "기준": expected,
            "체크": checks, "판정": verdict(checks), "비고": {"학습 내용명 일치": note},
            "수정 제안": "개발계획서의 학습 내용명과 대조하여 수정" if value == X else None}


def indexed(items):
    result = {}
    for item in items:
        key = (item["no"], item["sub"])
        if key in result or not clean(item["text"]):
            return None
        result[key] = clean(item["text"])
    return result or None


def display(mapping):
    return {f"{a}-{b}": text for (a, b), text in mapping.items()}


def compare_indexed(place, items, expected):
    actual = indexed(items)
    if actual is None:
        return row(place, TRI, items, display(expected), "명칭이 비었거나 번호가 중복되어 완전한 목록을 식별하지 못함")
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k])
    return row(place, X if missing or extra or changed else O, display(actual), display(expected),
               f"누락 번호: {missing}, 추가 번호: {extra}, 명칭 불일치 번호: {changed}")


def table_names(table):
    """정확한 헤더를 한 행에서 찾는다. 모호한 헤더/빈 열은 확정하지 않는다."""
    cells = table["cells"]
    headers = [(r, c) for (r, c), value in cells.items() if re.sub(r"\s", "", value) == "학습내용"]
    if len(headers) != 1:
        return None
    header_row, col = headers[0]
    keys = {re.sub(r"\s", "", v) for (r, _), v in cells.items() if r == header_row}
    kind = "평가 준거" if "학습목표" in keys else "평가 방법" if "평가항목" in keys else None
    if kind is None:
        return None
    values = [(r, clean(v)) for (r, c), v in sorted(cells.items()) if c == col and r > header_row and clean(v)]
    return kind, values


def compare_table(place, values, expected):
    values = [[r, clean(value)] for r, value in values]
    texts = [value for _, value in values]
    if not texts:
        return row(place, TRI, values, display(expected), "학습 내용 열의 값을 추출하지 못함")
    # 같은 명칭이 여러 평가 항목/방법 행에 반복되어도 ①의 명칭 일치에는 문제가 없다.
    # 번호가 없는 명칭은 계획서에서 유일하게 일치하는 번호가 있을 때만 연결한다.
    names = {}
    for key, text in expected.items():
        names.setdefault(text, []).append(key)
    actual = {}
    unresolved = []
    for text in texts:
        match = NUMBERED.fullmatch(text)
        if match:
            key, name = (int(match[1]), int(match[2])), clean(match[3])
        else:
            candidates = names.get(text, [])
            if len(candidates) > 1:
                return row(place, TRI, values, display(expected), "같은 명칭의 기준 번호가 여러 개여서 연결을 확정할 수 없음")
            if not candidates:
                unresolved.append(text)
                continue
            key, name = candidates[0], text
        if key in actual and actual[key] != name:
            return row(place, X, values, display(expected), f"동일 번호 {key}에 서로 다른 명칭이 기재됨")
        actual[key] = name
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(key for key in actual.keys() & expected.keys() if actual[key] != expected[key])
    return row(place, X if missing or extra or changed or unresolved else O, values, display(expected),
               f"누락 번호: {missing}; 추가 번호: {extra}; 명칭 불일치 번호: {changed}; "
               f"기준에 없는 명칭: {unresolved}")


def check_names(context):
    plan = context.plan_toc
    expected = indexed(plan.get("내용명", [])) if plan else None
    if expected is None:
        return [row("개발계획서", TRI, note="해당 모듈의 고유한 학습 내용 번호·명칭 목록을 읽지 못함. 차례로 기준을 대체하지 않음")]
    front, body_section = context.config.front_section, context.config.body_section
    rows = []
    if len(context.manuscript.sections) > 2:
        rows.append(row("검사 범위", TRI, note="선택한 두 섹션 밖에도 문서가 있어 전체 명칭의 완전성을 확인할 수 없음"))
    for title, source in (("차례", context.toc), ("개요 내용 체계", context.overview)):
        if not source or source.get("건너뜀"):
            rows.append(row(f"section{front} > {title}", TRI, note="영역 또는 학습 번호를 완전히 식별하지 못함"))
        else:
            rows.append(compare_indexed(f"section{front} > {title}", source.get("내용", []), expected))
    body = context.body
    lessons = body["lessons"]
    lesson_numbers = sorted({key[0] for key in expected})
    if [lesson["no"] for lesson in lessons] != lesson_numbers:
        rows.append(row(f"section{body_section} > 본문·평가", TRI,
                        note="내비게이터로 식별한 학습 구간과 계획서의 학습 번호가 달라 평가표 소속을 확정하지 못함"))
        return rows
    table_paragraphs = context.manuscript.section_table_paragraphs(body_section)
    if table_paragraphs is None:
        rows.append(row(f"section{body_section} > 필요 지식", TRI,
                        note="표 내부 명칭과 본문 제목을 구별할 수 없음. HWPX 입력 필요"))
    else:
        # parse_body가 중복 번호를 합치는 동작을 사용하지 않고 표 밖 제목을 직접 수집한다.
        for lesson in lessons:
            items = []
            split_heading = False
            start, end = lesson["raw_span"]
            for p in range(start, end):
                if p in table_paragraphs:
                    continue
                value = context.manuscript.sections[body_section][p]
                match = NUMBERED.fullmatch(value)
                if match:
                    items.append({"no": int(match[1]), "sub": int(match[2]), "text": match[3]})
                elif re.fullmatch(r"\d+\s*-\s*\d+\s*\.", value):
                    split_heading = True
                    rows.append(row(f"section{body_section} > 문단 {p}", TRI,
                                    note="번호와 제목이 다른 문단으로 분리되어 제목 연결 확인 필요"))
            if not split_heading:
                own = {key: value for key, value in expected.items() if key[0] == lesson["no"]}
                rows.append(compare_indexed(f"section{body_section} > 학습 {lesson['no']} > 필요 지식", items, own))
    for lesson in lessons:
        own = {key: value for key, value in expected.items() if key[0] == lesson["no"]}
        place = f"section{body_section} > 학습 {lesson['no']}"
        if len(lesson["eval"]) != 1:
            rows.append(row(place + " > 평가", TRI, note="평가 영역의 시작을 유일하게 식별하지 못함"))
            continue
        start = body["lines"][lesson["eval"][0]][0]
        end = lesson["raw_span"][1]
        found = set()
        parsed_tables = []
        for table in context.manuscript.section_tables(body_section):
            if not start <= table["paragraph"] < end:
                continue
            parsed = table_names(table)
            if parsed is None:
                rows.append(row(place + f" > 평가 > 문단 {table['paragraph']}", TRI,
                                note="평가 영역의 표를 지원하는 헤더 구조로 식별하지 못함"))
                continue
            kind, values = parsed
            found.add(kind)
            parsed_tables.append((kind, table["paragraph"], values))
        for kind, paragraph, values in parsed_tables:
            comparison = compare_table(place + f" > {kind} > 문단 {paragraph}", values, own)
            known_names_only = all(
                (own.get((int(match[1]), int(match[2]))) == clean(match[3]))
                if (match := NUMBERED.fullmatch(clean(value))) else clean(value) in own.values()
                for _, value in values
            )
            if (sum(k == kind for k, _, _ in parsed_tables) > 1
                    and comparison["판정"] != "적합" and known_names_only):
                # 완전한 목록을 가진 방법별 표는 각각 검사할 수 있다. 일부 목록만 있는 표는
                # 분할 표와 누락을 구별할 근거가 없으므로 합쳐서 적합 판정하지 않는다.
                rows.append(row(place + f" > {kind} > 문단 {paragraph}", TRI,
                                actual=comparison["원고"], expected=comparison["기준"],
                                note="동일 종류의 표가 여러 개이고 일부 명칭이 일치하지 않음. 분할 표/누락 여부 확인 필요; "
                                     + comparison["비고"]["학습 내용명 일치"]))
            else:
                rows.append(comparison)
        for missing in sorted({"평가 준거", "평가 방법"} - found):
            rows.append(row(place + " > " + missing, TRI,
                            note="해당 표를 찾지 못함. 실제 누락인지 추출 실패인지 확인 필요"))
    return rows
