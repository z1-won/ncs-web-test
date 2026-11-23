"""② 그림 속 공공누리 마크·저작권 문구·스톡 워터마크 — OCR 줄 해석(흔한 오인식 포함)과 점검 값(가짜 OCR, 외부·OS 기능 안 씀)."""

import unittest

from ncs_figures.checks import run_checks
from ncs_figures.config import DEFAULT_CONFIG
from ncs_figures.marks import MarkReader, analyze, kogl_type
from ncs_figures.models import Resources

from .test_review_rules import ctx, item


class FakeOcr:
    name = "fake OCR"

    def __init__(self, lines):
        self.text, self.calls = lines, 0

    def read_many(self, images):
        self.calls += 1
        return {key: (self.text if key.endswith("_full") else []) for key in images}


def outcome(lines, source="출처: 집필진 제작(2025)"):
    checks, _ = run_checks(item(ctx(source=source)), Resources(marks=MarkReader(FakeOcr(lines))), DEFAULT_CONFIG)
    return next(c for c in checks if c.name == "②마크·워터마크")


class AnalyzeTests(unittest.TestCase):
    def test_kogl_types_with_ocr_misreads(self):
        self.assertEqual(kogl_type("OPEN 공공누리 공공저작물 자유이용허락 줄저표시"), "1")          # 출처→줄저
        self.assertEqual(kogl_type("공공누리 공공저작을 자유이용혀락 출저표시 상업용금지"), "2")    # 허락→혀락이어도 0유형 아님
        self.assertEqual(kogl_type("공공누리 출처표시 변경금지"), "3")
        self.assertEqual(kogl_type("공공누리 출처표시 상업용금지 변경금지"), "4")
        self.assertEqual(kogl_type("OPEN 공공누리 공공저작물 자유이용허락 자유이용"), "0")
        self.assertIsNone(kogl_type("OPEN 공공누리"))

    def test_copyright_and_stock(self):
        self.assertTrue(analyze(["㉢ 202?) Hanhit Media C.orp AII nghts resetved"])["copyright"])
        self.assertTrue(analyze(["무단 전재 및 재배포 금지"])["copyright"])
        self.assertTrue(analyze(["shutterstock"])["stock"])
        plain = analyze(["요구사항 정의서", "기능 명세", "2025년 계획"])
        self.assertFalse(plain["kogl"] or plain["copyright"] or plain["stock"])


class CheckTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(outcome(["요구사항 정의"]).value, "O")
        mismatch = outcome(["OPEN 공공누리", "출처표시 변경금지"], source="출처: 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 1. 5. 검색. 공공누리 제1유형.")
        self.assertEqual(mismatch.value, "△")
        self.assertIn("제3유형", mismatch.note)
        same = outcome(["OPEN 공공누리", "출처표시"], source="출처: 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 1. 5. 검색. 공공누리 제1유형.")
        self.assertEqual(same.value, "O")
        stated_none = outcome(["OPEN 공공누리", "출처표시"])
        self.assertEqual(stated_none.value, "△")
        stock = outcome(["shutterstock"])
        self.assertEqual(stock.value, "△")
        self.assertIn("워터마크", stock.note)

    def test_one_ocr_batch_for_many_figures(self):
        ocr = FakeOcr(["x"])
        reader = MarkReader(ocr)
        reader.prefetch([item(ctx()), item(ctx(caption="[그림 1-2] 나"))])
        self.assertEqual(ocr.calls, 1)

    def test_no_ocr_means_skipped(self):
        checks, _ = run_checks(item(ctx()), Resources(), DEFAULT_CONFIG)
        self.assertIsNone(next(c for c in checks if c.name == "②마크·워터마크").value)


if __name__ == "__main__":
    unittest.main()
