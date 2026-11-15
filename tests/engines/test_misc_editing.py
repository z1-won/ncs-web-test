"""편집 체계(안내서 A-07) — 용지·여백과 글꼴 읽기(ncs_core.layout)와 판정(ncs_misc.rules.editing)."""

import io
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

from ncs_core.layout import other_fonts, page_problems, read_layout
from ncs_misc.rules.editing import FONT, PAGE, check_editing
from ncs_misc.sheet import ITEMS
from ncs_service.export import full_sheet

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HEADER = f"""<hh:head xmlns:hh="{HH}"><hh:fontfaces><hh:fontface lang="HANGUL">
<hh:font id="0" face="KoPub바탕체 Light"/><hh:font id="1" face="함초롬돋움"/></hh:fontface></hh:fontfaces>
<hh:charProperties><hh:charPr id="0"><hh:fontRef hangul="0"/></hh:charPr><hh:charPr id="1"><hh:fontRef hangul="1"/></hh:charPr>
</hh:charProperties></hh:head>"""


def section(top: int = 5669, extra: str = "") -> str:
    """A4, 좌우 25㎜·아래 13㎜·머리말 10㎜·꼬리말 12㎜. top만 바꿀 수 있다(5669 = 20㎜)."""
    return (f"""<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="{HP}"><hp:p><hp:run charPrIDRef="0">
<hp:secPr><hp:pagePr landscape="WIDELY" width="59528" height="84188">
<hp:margin left="7086" right="7086" top="{top}" bottom="3685" header="2834" footer="3401"/></hp:pagePr></hp:secPr>
<hp:t>학습모듈의 개요 123</hp:t></hp:run></hp:p>{extra}</hs:sec>""")


def manuscript(folder: str, *sections: str) -> Path:
    path = Path(folder) / "원고.hwpx"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/header.xml", HEADER)
        for i, text in enumerate(sections):
            z.writestr(f"Contents/section{i}.xml", text)
    path.write_bytes(buffer.getvalue())
    return path


def context(path: Path, fmt: str = "hwpx"):
    return types.SimpleNamespace(manuscript=types.SimpleNamespace(path=path, format=fmt))


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_form_values_pass(self):
        path = manuscript(self.temp.name, section(), section())
        layout = read_layout(path)
        self.assertEqual([p["구역"] for p in layout["구역"]], [0, 1])
        self.assertEqual(layout["구역"][0]["여백"], {"왼쪽": 25.0, "오른쪽": 25.0, "위": 20.0, "아래": 13.0, "머리말": 10.0, "꼬리말": 12.0})
        self.assertEqual((page_problems(layout), other_fonts(layout)), ([], []))
        [row] = check_editing(context(path))
        self.assertEqual((row["체크"], row["판정"], row["item_id"]), ({PAGE: "O", FONT: "O"}, "적합", "F02-기타-편집"))

    def test_wrong_margin_fails_and_names_the_section(self):
        path = manuscript(self.temp.name, section(), section(top=4819))   # 17㎜
        [row] = check_editing(context(path))
        self.assertEqual((row["체크"][PAGE], row["판정"]), ("X", "부적합"))
        self.assertEqual(row["비고"][PAGE], "구역 1: 위 여백 17.0㎜(기준 20㎜)")
        self.assertIn("위 20", row["수정 제안"])

    def test_other_font_is_a_candidate_and_memo_text_is_ignored(self):
        other = f'<hp:p xmlns:hp="{HP}"><hp:run charPrIDRef="1"><hp:t>붙여 넣은 글</hp:t></hp:run></hp:p>'
        memo = f'<hp:p xmlns:hp="{HP}"><hp:run charPrIDRef="0"><hp:memo><hp:run charPrIDRef="1"><hp:t>메모 글자</hp:t></hp:run></hp:memo></hp:run></hp:p>'
        [row] = check_editing(context(manuscript(self.temp.name, section(extra=other + memo))))
        self.assertEqual((row["체크"], row["판정"]), ({PAGE: "O", FONT: "△"}, "판단불가"))   # 글꼴은 후보까지만
        self.assertIn("함초롬돋움 5자", row["비고"][FONT])
        self.assertNotIn("메모", row["비고"][FONT])

    def test_hwp_is_undecided(self):
        [row] = check_editing(context(Path(self.temp.name) / "원고.hwp", fmt="hwp"))
        self.assertEqual((row["체크"], row["판정"]), ({PAGE: "△", FONT: "△"}, "판단불가"))

    def test_editing_item_stays_out_of_the_f02_sheet_file(self):
        self.assertEqual(ITEMS[-1].no, "편집")
        rows = full_sheet([{"구성요소": "기타", "번호": "편집", "체크 항목": "x", "검수결과": "부적합", "비고": ""}])
        self.assertEqual(len(rows), 54)
        self.assertNotIn("편집", [r["번호"] for r in rows])


if __name__ == "__main__":
    unittest.main()
