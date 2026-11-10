"""PDF 읽기(ncs_core.pdf)와 출력본 제목 쪽 찾기(ncs_core.manuscript.pages) — 합성 출력본 PDF로."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from ncs_core import pdf
from ncs_core.manuscript.pages import locate_headings, toc_pages

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PRINT_COPY = FIXTURES / "출력본_ok_LM1203020201_24v3.pdf"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"


class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = pdf.load_pdf(PRINT_COPY)

    def test_is_pdf_by_signature_not_extension(self):
        self.assertTrue(pdf.is_pdf(PRINT_COPY))
        self.assertFalse(pdf.is_pdf(MANUSCRIPT))
        self.assertFalse(pdf.is_pdf(FIXTURES / "없는 파일.pdf"))

    def test_pages_bands_and_folios(self):
        doc = self.doc
        self.assertEqual(len(doc.pages), 45)
        self.assertGreater(doc.text_ratio, 0.9)
        self.assertEqual(doc.module_code, "LM1203020201_24v3")      # 표지에서
        # 표지·차례·개요에는 쪽 번호가 없고, 음수·0으로 추정하지도 않는다
        self.assertEqual([p.folio for p in doc.pages[:3]], [None, None, None])
        self.assertEqual([p.folio_source for p in doc.pages[:3]], [None, None, None])
        # 본문 첫 쪽: 꼬리말의 '1'을 읽고, 달리는 머리말은 header로 분리되어 body에 없다
        first = doc.pages[3]
        self.assertEqual((first.folio, first.folio_source), ("1", "읽음"))
        self.assertEqual(first.footer, ("1",))
        self.assertIn("학습 1 요구사항 확인하기", first.header)
        self.assertEqual(first.body[:2], ("학습 1", "요구사항 확인하기"))
        self.assertEqual(doc.pages[-1].folio, "42")
        self.assertIs(doc.page_by_folio("16"), doc.pages[18])
        self.assertIsNone(doc.page_by_folio("999"))

    def test_caption_in_footer_band_returns_to_body(self):
        page = self.doc.page_by_folio("4")
        self.assertIn("[그림 1-1] 현행 시스템 구성도", page.body)
        self.assertEqual(page.footer, ("4",))

    def test_find_iterates_body_lines(self):
        hits = [(p.folio, line) for p, line, _ in self.doc.find(r"^참고\s*자료$")]
        self.assertEqual(hits, [("40", "참고 자료")])

    def test_not_a_pdf_and_missing_library(self):
        with self.assertRaisesRegex(ValueError, "PDF 파일이 아닙니다"):
            pdf.load_pdf(MANUSCRIPT)
        with mock.patch.dict(sys.modules, {"pypdf": None, "pypdf.errors": None}):
            with self.assertRaises(pdf.PdfUnavailable):
                pdf.load_pdf(PRINT_COPY)

    def test_unreadable_text_is_rejected(self):
        # 글자 비율 문턱을 올려 '스캔본' 경로를 탄다
        with self.assertRaisesRegex(ValueError, "글자를 추출할 수 없는 PDF"):
            pdf.load_pdf(PRINT_COPY, min_text_ratio=1.01)


class FolioTests(unittest.TestCase):
    def test_read_folio_shapes(self):
        self.assertEqual(pdf.read_folio(["- 12 -"]), "12")
        self.assertEqual(pdf.read_folio(["ⅲ"]), "ⅲ")
        self.assertEqual(pdf.read_folio(["iv"]), "iv")
        self.assertEqual(pdf.read_folio(["12 | 연회 관리"]), "12")
        self.assertEqual(pdf.read_folio(["연회 관리 · 7"]), "7")
        self.assertIsNone(pdf.read_folio(["학습 1 연회 예약하기"]))
        self.assertIsNone(pdf.read_folio([]))

    def test_missing_folios_are_estimated_from_majority_offset(self):
        raw = [{"header": [], "body": ["x"], "footer": f} for f in ([], ["3"], ["4"], [], ["6"])]
        pages = pdf._assign_folios(raw)
        self.assertEqual([(p.folio, p.folio_source) for p in pages],
                         [("2", "추정"), ("3", "읽음"), ("4", "읽음"), ("5", "추정"), ("6", "읽음")])
        # 읽은 쪽 번호가 하나도 없으면 추정하지 않는다
        none = pdf._assign_folios([{"header": [], "body": ["x"], "footer": []}] * 3)
        self.assertEqual([p.folio for p in none], [None, None, None])


class LocateHeadingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = pdf.load_pdf(PRINT_COPY)

    def test_toc_page_is_the_one_with_numbered_lesson_lines(self):
        self.assertEqual(toc_pages(self.doc), [1])

    def test_every_toc_target_is_found_on_its_page(self):
        found = {k: v["folio"] for k, v in locate_headings(self.doc).items()}
        self.assertEqual(found, {
            "학습 1": "1", "1-1": "3", "1-2": "7", "학습 1 교수·학습 방법": "10", "학습 1 평가": "12",
            "학습 2": "15", "2-1": "16", "학습 2 교수·학습 방법": "20", "학습 2 평가": "22",
            "참고 자료": "40", "활용 서식": "42",
        })

    def test_navigator_block_takes_lesson_of_following_heading(self):
        # 내비게이터 묶음마다 '학습 1'·'학습 2'가 모두 적혀 있어도, 두 번째 묶음(15쪽)이 학습 2의 시작이다
        found = locate_headings(self.doc)
        self.assertEqual(found["학습 2"]["index"], 17)
        self.assertEqual(found["학습 2"]["line"], "학습 1")  # 묶음의 첫 줄은 여전히 '학습 1'

    def test_running_head_does_not_count(self):
        # 머리말 '학습 1 요구사항 확인하기'가 매 쪽 있어도 '학습 1'은 본문 첫 묶음에서만 잡힌다
        self.assertEqual(locate_headings(self.doc)["학습 1"]["index"], 3)


if __name__ == "__main__":
    unittest.main()
