"""F02 검수 확인서 내보내기(ncs_service.export) — xlsx·hwpx 내용과 웹 엔드포인트."""

import io
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ncs_service import ReviewRequest, execute_review
from ncs_service.export import HP, MARK, build_hwpx, build_xlsx, full_sheet

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"


def rows_for(*checks):
    out = []
    for check in checks:
        out.extend(execute_review(ReviewRequest((MANUSCRIPT, PLAN), check)).result.sheet)
    return out


class FullSheetTests(unittest.TestCase):
    def test_all_54_items_in_engine_order_with_unrun_marked(self):
        rows = full_sheet(rows_for("toc"))
        self.assertEqual(len(rows), 54)
        self.assertEqual(rows[0]["구성요소"], "NCS-학습모듈의 위치")
        self.assertEqual(rows[0]["검수결과"], "미검사")
        toc = [r for r in rows if r["구성요소"] == "차례"]
        self.assertEqual([r["번호"] for r in toc], list("①②③④⑤⑥⑦"))
        # ⑦(쪽수)은 출력본 PDF가 없으면 판단불가(미검사가 아니라 이유가 남는다)
        self.assertTrue(all(r["검수결과"] != "미검사" for r in toc))
        self.assertEqual(next(r for r in toc if r["번호"] == "⑦")["검수결과"], "판단불가")


class XlsxTests(unittest.TestCase):
    def test_workbook_has_sheet_rows_and_marks(self):
        from openpyxl import load_workbook

        content = build_xlsx("LM1203020201_24v3", rows_for("position", "toc"), meta={"세분류명": "객실관리", "학습모듈명": "객실 예약 관리"})
        wb = load_workbook(io.BytesIO(content))
        ws = wb["검수 확인서"]
        self.assertIn("LM1203020201_24v3", ws["A2"].value)
        self.assertIn("객실관리", ws["A2"].value)
        body = [[c.value for c in row] for row in ws.iter_rows(min_row=7, max_col=6)]
        self.assertEqual(len(body), 54)
        marks = [r[2] or r[3] or r[4] for r in body[:11]]   # 위치 5 + 차례 ①~⑥은 실행했으니 표시가 있다(⑦은 미구현)
        self.assertTrue(all(m in (MARK, "△") for m in marks), marks)
        self.assertTrue(all((r[2], r[3], r[4]) == (None, None, None) or (r[2], r[3], r[4]) == ("", "", "") for r in body[12:]))


class HwpxTests(unittest.TestCase):
    def test_manuscript_text_never_becomes_a_formula(self):
        """원고 문구가 '='로 시작해도 수식이 아닌 문자열로 저장된다(xlsx 수식 주입 방지)."""
        from openpyxl import load_workbook
        rows = rows_for("position")
        rows[0]["체크 항목"] = '=HYPERLINK("http://evil.example","클릭")'
        rows[0]["검수결과"] = "부적합"
        rows[0]["비고"] = "=cmd|' /C calc'!A0"
        wb = load_workbook(io.BytesIO(build_xlsx('=1+1', rows, meta={"세분류명": "+x", "학습모듈명": "-y"})))
        ws = wb.active
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    self.assertNotEqual(cell.data_type, "f", f"{cell.coordinate}: {cell.value!r}")
        texts = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
        self.assertTrue(any('=HYPERLINK' in t for t in texts))

    def test_form_is_filled_and_still_a_valid_hwpx(self):
        content = build_hwpx("LM1203020201_24v3", rows_for("position", "toc"), meta={"세분류명": "객실관리", "학습모듈명": "객실 예약 관리"})
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.namelist()[0], "mimetype")
            self.assertEqual(z.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
            section = ET.fromstring(z.read("Contents/section0.xml"))
        texts = ["".join(t.text or "" for t in p.iter(HP + "t")) for p in section.iter(HP + "p")]
        joined = "\n".join(texts)
        self.assertIn("객실관리", joined)
        self.assertIn("LM1203020201_24v3", joined)
        self.assertGreaterEqual(joined.count(MARK), 5, "실행한 항목에는 ✓가 찍혀야 한다")
        self.assertIn("미검사", joined)
        # 양식의 체크 항목 글은 그대로
        self.assertIn("① 대분류, 중분류, 소분류의 명칭을 모두 올바르게 기재하였는가?", joined)


class WebExportTests(unittest.TestCase):
    def test_endpoint_returns_both_formats(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        rows = rows_for("toc")
        with TestClient(create_app(out_dir=ROOT / "tests" / "_export_out")) as client:
            for fmt, head in (("xlsx", b"PK"), ("hwpx", b"PK")):
                response = client.post(f"/api/export/sheet?format={fmt}", json={"module_code": "LM1203020201_24v3", "rows": rows})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.content.startswith(head))
                self.assertIn(f".{fmt}", response.headers["content-disposition"])
            self.assertEqual(client.post("/api/export/sheet?format=pdf", json={"module_code": "x", "rows": []}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
