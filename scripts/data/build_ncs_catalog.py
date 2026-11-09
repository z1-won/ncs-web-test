"""NCS 포털 '학습모듈 분류보기' 엑셀(실제로는 HTML 표, ClassificationView*.xls)을 읽어 NCS 분류·능력단위 목록을 만든다.

  python scripts/data/build_ncs_catalog.py 폴더 [--out src/ncs_core/data/ncs_units.tsv]

포털에서 대분류마다 하나씩 내려받은 파일(24개)을 한 표로 합친다. 셀 병합(rowspan)을 풀어 모든 행에 분류 값을 채운다.
출력(탭 구분, 주석 # 허용): 세분류코드(8자리)  대분류  중분류  소분류  세분류  NCS개발연도  학습모듈개발연도  능력단위코드  능력단위명
이름 앞의 '01. ' 같은 순번은 떼고, 순번은 코드에서 읽는다(능력단위 코드 끝 두 자리 = 능력단위 번호).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ["세분류코드", "대분류", "중분류", "소분류", "세분류", "NCS개발연도", "학습모듈개발연도", "능력단위코드", "능력단위명"]
NUMBERED = re.compile(r"^\d{2}\.\s*")
UNIT_CODE = re.compile(r"^(\d{10})_\d+v\d+$")


class TableParser(HTMLParser):
    """<tr>/<td>를 (텍스트, rowspan) 행 목록으로."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[tuple[str, int]]] = []
        self.row = None
        self.cell = None
        self.span = 1

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell, self.span = "", int(dict(attrs).get("rowspan") or 1)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None and self.cell is not None:
            self.row.append((re.sub(r"\s+", " ", self.cell).strip(), self.span))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data


def expand(rows: list[list[tuple[str, int]]], width: int = 8) -> list[list[str]]:
    """rowspan을 풀어 모든 행을 width 칸으로 채운다."""
    carry: dict[int, tuple[str, int]] = {}  # 열 → (값, 남은 행 수)
    out = []
    for row in rows:
        if len(row) == width and all(sp == 1 for _, sp in row) and row[0][0] in ("대분류",):
            continue  # 머리 행
        cells, src = [], iter(row)
        for col in range(width):
            if col in carry and carry[col][1] > 0:
                value, left = carry[col]
                cells.append(value)
                carry[col] = (value, left - 1)
                continue
            try:
                value, span = next(src)
            except StopIteration:
                cells.append("")
                continue
            cells.append(value)
            if span > 1:
                carry[col] = (value, span - 1)
        if UNIT_CODE.match(cells[6]):
            out.append(cells)
    return out


def read_folder(folder: Path) -> list[list[str]]:
    records = []
    for path in sorted(folder.glob("*.xls")):
        parser = TableParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        for big, mid, small, sub, ncs_year, module_year, code, unit in expand(parser.rows):
            records.append([code[:8], NUMBERED.sub("", big), NUMBERED.sub("", mid), NUMBERED.sub("", small), NUMBERED.sub("", sub),
                            ncs_year, module_year, code, NUMBERED.sub("", unit)])
    records.sort(key=lambda r: r[7])
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "src" / "ncs_core" / "data" / "ncs_units.tsv")
    args = parser.parse_args()
    records = read_folder(args.folder)
    if not records:
        sys.exit("능력단위 행을 찾지 못했습니다")
    subclasses = {r[0] for r in records}
    lines = [f"# NCS 분류·능력단위 목록 — NCS 포털 '학습모듈 분류보기' 내려받기({date.today().isoformat()} 변환). 갱신: scripts/data/build_ncs_catalog.py",
             "# " + "\t".join(HEADER)]
    lines += ["\t".join(r) for r in records]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"능력단위 {len(records)}개, 세분류 {len(subclasses)}개 → {args.out}")


if __name__ == "__main__":
    main()
