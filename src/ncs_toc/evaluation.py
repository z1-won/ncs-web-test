"""본문 표 가운데 평가 준거·평가 방법 표를 찾아 '학습 내용' 열 값을 꺼낸다."""

from ncs_core import Table

HEADER_KEYS = ("학습내용", "학습목표", "평가항목")


def evaluation_tables(tables: list[Table]) -> list[tuple[int, str, list[str]]]:
    """[(표가 있는 문단 인덱스, '평가 준거'|'평가 방법', ['학습 내용' 열 값 …])].

    '학습 내용' 머리글이 있고 '학습 목표'(평가 준거) 또는 '평가 항목'(평가 방법) 머리글이
    함께 있는 표만 평가 표로 본다.
    """
    out = []
    for table in tables:
        headers: dict[str, tuple[int, int]] = {}
        for (row, col), value in sorted(table["cells"].items()):
            key = next((k for k in HEADER_KEYS if value.replace(" ", "").startswith(k)), None)
            if key and key not in headers:
                headers[key] = (row, col)
        if "학습내용" not in headers or not ({"학습목표", "평가항목"} & headers.keys()):
            continue
        kind = "평가 준거" if "학습목표" in headers else "평가 방법"
        header_row, content_col = headers["학습내용"]
        values = [
            v for (r, c), v in sorted(table["cells"].items()) if c == content_col and r > header_row and v
        ]
        out.append((table["paragraph"], kind, values))
    return out
