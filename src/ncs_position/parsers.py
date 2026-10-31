"""문단과 표에서 위치 정보(대·중·소분류, 세분류·능력단위·학습모듈명 표, 개발계획서 학습모듈명)를 추출한다."""

from ncs_core import Table
from ncs_core.tables import column, find_table, header_columns

from .patterns import LABELS3, PLAN_NAME_INLINE, PLAN_NAME_LABEL, POSITION_ANCHOR, TABLE_HEADERS


def parse_classification(lines: list[str]) -> dict[str, str]:
    """'[NCS-학습모듈의 위치]' 이후 처음 나오는 대/중/소분류 라벨의 다음 줄 = 값."""
    values: dict[str, str] = {}
    anchor = next((i for i, l in enumerate(lines) if l.startswith(POSITION_ANCHOR)), 0)
    for i in range(anchor, len(lines)):
        line = lines[i]
        if line in LABELS3 and line not in values and i + 1 < len(lines):
            values[line] = lines[i + 1]
        if len(values) == 3:
            break
    return values


def position_tables(tables: list[Table]) -> tuple[Table | None, Table | None]:
    """(대·중·소분류 표, 그 뒤의 세분류·능력단위·학습모듈명 표)."""
    first = find_table(tables, "대분류")
    second = find_table(tables, "세분류", after=first) if first else None
    return first, second


def parse_position(tables: list[Table]) -> dict:
    """{'세분류': [...], '능력단위': [...], '학습모듈명': [...], '행쌍': [(능력단위, 학습모듈명), ...]}"""
    _, table = position_tables(tables)
    out = {"세분류": [], "능력단위": [], "학습모듈명": [], "행쌍": []}
    if not table:
        return out
    headers = header_columns(table, TABLE_HEADERS)
    col_s, col_u, col_m = headers.get("세분류", 0), headers.get("능력단위"), headers.get("학습모듈명")
    out["세분류"] = [v for v in column(table, col_s) if v != "세분류"]
    if col_u is not None:
        out["능력단위"] = [v for v in column(table, col_u) if v != "능력단위"]
    if col_m is not None:
        out["학습모듈명"] = [v for v in column(table, col_m) if v != "학습모듈명"]
    if col_u is not None and col_m is not None:
        for row in sorted({r for (r, c) in table["cells"] if c in (col_u, col_m)}):
            unit, module = table["cells"].get((row, col_u), ""), table["cells"].get((row, col_m), "")
            if (unit or module) and unit != "능력단위" and module != "학습모듈명":
                out["행쌍"].append((unit, module))
    return out


def find_styled_position_table(tables: list[Table]) -> Table | None:
    """서식 정보가 있는 표 중 세분류·학습모듈명 머리글이 모두 있는 첫 표."""
    for table in tables:
        if table["styles"] is None:
            continue
        texts = set(table["cells"].values())
        if "세분류" in texts and "학습모듈명" in texts:
            return table
    return None


def parse_plan_module_name(sections, module_code: str) -> str | None:
    """개발계획서의 해당 모듈 블록에서 '학습 모듈명' 값을 찾는다."""
    lines = [l for section in sections for l in section]
    code = module_code.replace("LM", "")
    start = next(
        (i for i, l in enumerate(lines) if l == code and i > 0 and lines[i - 1].startswith("능력단위 코드번호")),
        None,
    )
    if start is None:
        return None
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("NCS (수정 금지)")), len(lines))
    block = lines[start:end]
    for i, line in enumerate(block):
        if PLAN_NAME_LABEL.fullmatch(line) and i + 1 < len(block):
            return block[i + 1]
        if m := PLAN_NAME_INLINE.match(line):
            return m.group(1).strip()
    return None
