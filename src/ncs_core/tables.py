"""Document.tables(문서 순서의 표 목록)를 다루는 작은 도우미."""

from .documents import Table


def column(table: Table, col: int) -> list[str]:
    """해당 열의 비어 있지 않은 셀 텍스트를 행 순서대로."""
    return [v for (r, c), v in sorted(table["cells"].items()) if c == col and v]


def column_cells(table: Table, col: int, header: str | None = None) -> list[tuple[int, str]]:
    """해당 열의 비어 있지 않은 셀을 (행, 텍스트)로, header 텍스트는 제외."""
    return [
        (r, v)
        for (r, c), v in sorted(table["cells"].items())
        if c == col and v and v != header
    ]


def header_columns(table: Table, names: tuple[str, ...]) -> dict[str, int]:
    """names에 있는 머리글 셀 텍스트 → 열 번호 (먼저 나온 것 우선)."""
    found: dict[str, int] = {}
    for (r, c), value in sorted(table["cells"].items()):
        if value in names and value not in found:
            found[value] = c
    return found


def find_table(tables: list[Table], must_contain: str, after: Table | None = None) -> Table | None:
    """must_contain을 포함한 셀이 있는 첫 표 (after 표 다음부터)."""
    start = tables.index(after) + 1 if after is not None else 0
    for table in tables[start:]:
        if any(must_contain in v for v in table["cells"].values()):
            return table
    return None
