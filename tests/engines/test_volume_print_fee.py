"""원고 분량 산정의 출력본(PDF) 측정과 계약서 기준 집필료(ncs_volume.printed·fee, REQ-02-013 11/20 회의 요구).

- 출력본 측정 경로는 가짜 출력본(Printed)을 read_printed 자리에 넣어 검사하고, PDF 좌표 읽기는 직접 만든 작은 PDF로 검사한다.
- 같은 원고 확인: 모듈 코드가 다르면, 코드를 모르면서 글이 거의 안 겹치면 판단불가.
- 실물 원고에 기대는 테스트는 없다(합성 hwpx·합성 PDF만).
"""

import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from ncs_core.pdf import PdfUnavailable
from ncs_volume import DEFAULT_CONFIG, measure
from ncs_volume.config import FEE_UNIT_DEFAULT, VolumeConfig
from ncs_volume.fee import compute_fee
from ncs_volume.printed import Item, Printed, PrintedPage, fill, read_printed

from tests.engines.test_volume import hwpx, manuscript

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
CODE = "LM1203020201_24v3"
TOP, BOTTOM = 842 - 30 * 72 / 25.4, 25 * 72 / 25.4     # 본문 띠(과업지시서 여백)
PITCH = 19.8                                             # 1,980 HWPUNIT


class FakePage:
    """출력본 한 쪽을 위에서부터 채우는 도우미 — 글 줄은 PITCH씩 내려간다."""

    def __init__(self, index, folio=None):
        self.page = PrintedPage(index, folio, TOP, BOTTOM)
        self.y = TOP

    def text(self, text, lines=1):
        for k in range(lines):
            self.page.items.append(Item("text", self.y, self.y - 12, text if k == 0 else f"{text} {k}"))
            self.y -= PITCH
        return self

    def picture(self, height):
        self.page.items.append(Item("picture", self.y, self.y - height))
        self.y -= height
        return self


def fake_printed(code=CODE, extra_lesson_lines=0):
    """test_volume.manuscript()와 같은 구성의 출력본: 표지 → 위치 → 차례 → 개요 → 학습 1 → 수행 → 교수·학습 → 평가 → 참고 자료(배너 그림) → 개발 이력."""
    pages = [
        FakePage(0).text("2026 NCS학습모듈 표지").text("교육부"),
        FakePage(1).text("[NCS-학습모듈의 위치]").text("대분류 정보통신", 3),
        FakePage(2).text("차 례").text("학습모듈의 개요 1").text("학습 1. 요구사항 확인하기 2").text("참고 자료 30"),
        FakePage(3, "1").text("요구사항 확인 학습모듈의 개요").text("학습모듈의 목표").text("요구사항을 확인할 수 있다.", 2),
        FakePage(4, "2").text("학습 1 요구사항 확인하기").text("학습 2 화면 구현하기").text("필요 지식 /")
                       .text("현행 시스템 분석의 개념", 20 + extra_lesson_lines).picture(150).text("[그림 1-1] 시스템 구성도"),
        FakePage(5, "3").text("수행 내용 / 현행 시스템 분석하기").text("현행 시스템을 분석한다.", 26),
        FakePage(6, "4").text("학습 1 교수·학습 방법").text("교수 방법", 10),
        FakePage(7, "5").text("학습 1 평 가").text("학습 내용 평가 항목").text("현행 시스템 분석 분석할 수 있다"),
        FakePage(8, "6").picture(37).text("교육부(2024). 「안내서」.", 2),
        FakePage(9).text("NCS학습모듈 개발이력 발행일").text("ISBN 979-11"),
    ]
    return Printed(Path("출력본.pdf"), [p.page for p in pages], code)


class FeeRules(unittest.TestCase):
    def test_default_unit_is_budget_guideline_ceiling_and_marked(self):
        fee = compute_fee(80, "한글 줄 배치 계산", config=DEFAULT_CONFIG)
        self.assertEqual((fee["단가"], fee["집필료"]), (FEE_UNIT_DEFAULT, 80 * 50000))
        self.assertEqual(fee["산식"], "80매 × 50,000원 = 4,000,000원")
        self.assertFalse(fee["단가 입력"])
        self.assertIn("상한", fee["단가 근거"])
        self.assertTrue(any("단가를 넣지 않아" in note for note in fee["알림"]))
        self.assertIn("제13조 1항", fee["세금"])
        clauses = [row["조항"] for row in fee["근거"]]
        self.assertIn("F07 계약서 제13조 4항", clauses)
        self.assertIn("F16 정산지침 인쇄 36쪽", clauses)

    def test_entered_unit_and_contract_cap(self):
        over = compute_fee(83, "x", config=DEFAULT_CONFIG, unit=46200, contract_pages=80)
        self.assertEqual((over["인정 분량"], over["집필료"]), (80, 80 * 46200))     # 초과분 추가금 없음
        self.assertTrue(over["단가 입력"])
        under = compute_fee(75, "x", config=DEFAULT_CONFIG, unit=46200, contract_pages=80)
        self.assertEqual((under["인정 분량"], under["집필료"]), (75, 75 * 46200))    # 미달이면 제출 분량만큼
        self.assertTrue(any("미달" in note for note in under["알림"]))

    def test_changed_pages_give_improvement_basis(self):
        fee = compute_fee(80, "x", config=DEFAULT_CONFIG, unit=50000, changed_pages=12)
        self.assertEqual(fee["개선 기준"]["집필료"], 600000)
        self.assertIn("20쪽", fee["개선 기준"]["근거"])
        self.assertIsNone(compute_fee(80, "x", config=DEFAULT_CONFIG)["개선 기준"])

    def test_above_ceiling_and_estimate_are_noted_and_bad_values_rejected(self):
        fee = compute_fee(10, "추정", config=DEFAULT_CONFIG, unit=60000, estimated=True)
        self.assertTrue(any("상한" in note for note in fee["알림"]))
        self.assertTrue(fee["추정"])
        with self.assertRaises(ValueError):
            compute_fee(10, "x", config=DEFAULT_CONFIG, unit=0)
        with self.assertRaises(ValueError):
            compute_fee(10, "x", config=DEFAULT_CONFIG, contract_pages=0)

    def test_config_unit_is_used_when_not_entered(self):
        self.assertEqual(compute_fee(2, "x", config=VolumeConfig(fee_unit=40000))["집필료"], 80000)


class Fill(unittest.TestCase):
    def test_picture_gap_is_excluded_but_lines_and_blank_space_count(self):
        items = [Item("text", 700, 688, "가"), Item("picture", 680, 530), Item("text", 520, 508, "나")]
        height, visual = fill(items, PITCH)
        self.assertAlmostEqual(visual, 150)
        self.assertAlmostEqual(height, (700 - (520 - PITCH)) - 150)

    def test_picture_beside_text_is_not_excluded(self):
        items = [Item("text", 700, 688, "가"), Item("picture", 700, 600)] + [Item("text", 700 - k * PITCH, 688 - k * PITCH, "줄") for k in range(1, 6)]
        _, visual = fill(items, PITCH)
        self.assertAlmostEqual(visual, 0)

    def test_empty_page(self):
        self.assertEqual(fill([], PITCH), (0.0, 0.0))


class PrintedMeasure(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = hwpx(Path(self.folder.name) / f"원고_{CODE}.hwpx", manuscript())

    def run_with(self, printed, path=None, **kwargs):
        with mock.patch("ncs_volume.printed.read_printed", return_value=printed):
            return measure(path or self.path, print_pdf="출력본.pdf", **kwargs)

    def test_pages_and_segments_are_measured_from_print(self):
        result = self.run_with(fake_printed())
        printed = result["출력본"]
        self.assertTrue(printed["사용"], printed["사유"])
        self.assertEqual((printed["전체 쪽 수"], printed["한글 물리 쪽 수"], printed["쪽 수 차이"]), (10, 10, 0))
        rows = {row["구성"]: row for row in printed["구성"]}
        self.assertEqual(rows["학습 — 필요 지식"]["출력본 쪽"], "5~5")
        self.assertEqual(rows["학습 — 수행 내용"]["인쇄 쪽"], "3~3")
        self.assertEqual(rows["참고 자료"]["출력본 쪽"], "9~9")          # 배너 그림으로 시작하는 꼬리 구성
        self.assertFalse(rows["표지"]["반영"])
        self.assertIsNotNone(rows["학습 — 필요 지식"]["차이"])
        # ½쪽 규칙: 필요 지식(그림 자리 뺌)·수행 내용 두 쪽만 1쪽
        self.assertEqual(printed["합계"]["쪽"], 2)
        self.assertEqual([p["인정"] for p in printed["쪽별"]][4:6], ["1쪽", "1쪽"])
        self.assertEqual(printed["쪽별"][0]["인정"], "제외")
        self.assertGreater(rows["학습 — 필요 지식"]["시각 자료 제외(쪽)"], 0)
        methods = {m["항목"]: m["방법"] for m in printed["측정 구분"]}
        self.assertEqual(methods["전체 쪽 수"], "측정")
        self.assertEqual(methods["쪽별 채움 높이(½쪽 규칙)"], "측정")
        self.assertEqual(methods["남은 행(½쪽 미만인 쪽)"], "계산")
        # 산정에는 출력본 값을 쓰고, 한글 값은 합계에 그대로 남긴다
        self.assertEqual(result["채택 분량"]["기입 분량"], printed["합계"]["기입 분량"])
        self.assertIn("출력본", result["채택 분량"]["근거"])
        self.assertEqual(printed["합계"]["한글 계산 기입 분량"], result["합계"]["기입 분량"])
        self.assertEqual(result["집필료"]["산정 분량"], printed["합계"]["기입 분량"])

    def test_page_count_difference_is_reported(self):
        printed = fake_printed()
        printed.pages.append(PrintedPage(10, None, TOP, BOTTOM))
        result = self.run_with(printed)["출력본"]
        self.assertEqual(result["쪽 수 차이"], 1)
        self.assertTrue(any("1쪽 많습니다" in note for note in result["알림"]))

    def test_print_of_another_manuscript_is_undecided(self):
        result = self.run_with(fake_printed(code="LM9999999999_24v1"))
        self.assertFalse(result["출력본"]["사용"])
        self.assertIn("판단불가", result["출력본"]["사유"])
        self.assertIn("LM9999999999_24v1", result["출력본"]["사유"])
        self.assertEqual(result["채택 분량"]["근거"], "한글 줄 배치 계산")
        self.assertTrue(any("판단불가" in note for note in result["알림"]))

    def test_unknown_code_and_different_text_is_undecided(self):
        path = hwpx(Path(self.folder.name) / "원고.hwpx", manuscript())
        printed = Printed(Path("x.pdf"), [FakePage(i).text("전혀 다른 내용의 문서입니다 " * 2, 20).page for i in range(10)], None)
        result = self.run_with(printed, path=path)["출력본"]
        self.assertFalse(result["사용"])
        self.assertIn("다른 원고", result["사유"])

    def test_print_without_lessons_is_undecided(self):
        printed = Printed(Path("x.pdf"), [FakePage(0).text("2026 NCS학습모듈 표지").page], CODE)
        result = self.run_with(printed)["출력본"]
        self.assertFalse(result["사용"])
        self.assertIn("학습", result["사유"])

    def test_without_print_no_print_section_and_fee_uses_layout(self):
        result = measure(self.path)
        self.assertIsNone(result["출력본"])
        self.assertEqual(result["채택 분량"]["근거"], "한글 줄 배치 계산")
        self.assertEqual(result["집필료"]["집필료"], result["합계"]["기입 분량"] * FEE_UNIT_DEFAULT)

    def test_fee_inputs_and_change_basis_flow_through_measure(self):
        edited = hwpx(Path(self.folder.name) / f"새 원고_{CODE}.hwpx", manuscript(extra_body="와 범위", tail_change=True))
        result = measure(edited, previous=self.path, fee_unit=40000, contract_pages=1)
        fee = result["집필료"]
        self.assertEqual((fee["단가"], fee["인정 분량"]), (40000, 1))
        self.assertEqual(fee["개선 기준"]["분량"], result["변경"]["변경 분량"]["기입 분량"])

    def test_missing_pypdf_is_undecided_not_error(self):
        with mock.patch("ncs_volume.pipeline.measure_printed", side_effect=PdfUnavailable("pypdf 없음")):
            result = measure(self.path, print_pdf="출력본.pdf")
        self.assertFalse(result["출력본"]["사용"])
        self.assertIn("pypdf", result["출력본"]["사유"])

    def test_non_pdf_print_is_rejected(self):
        with self.assertRaises(ValueError):
            measure(self.path, print_pdf=self.path)


class FixturePrintCopy(unittest.TestCase):
    def test_estimated_manuscript_with_print_copy_is_measured(self):
        """줄 배치가 없는 합성 원고도 같은 원고의 출력본이 있으면 쪽은 PDF로 재고 권고 범위를 판정한다."""
        result = measure(FIXTURES / f"원고_ok_{CODE}.hwpx", print_pdf=FIXTURES / f"출력본_ok_{CODE}.pdf")
        printed = result["출력본"]
        self.assertTrue(result["추정"])
        self.assertTrue(printed["사용"], printed["사유"])
        self.assertEqual(printed["전체 쪽 수"], 45)
        self.assertIsNone(printed["쪽 수 차이"])
        self.assertNotEqual(result["권고 분량"]["상태"], "판단불가")
        self.assertFalse(result["집필료"]["추정"])
        self.assertEqual({m["항목"]: m["방법"] for m in printed["측정 구분"]}["행 합계·변경 분량"], "추정")


def tiny_pdf(path: Path) -> Path:
    """글 두 줄(Helvetica)과 그림(1×1 회색 이미지) 하나를 그린 A4 한 쪽 PDF."""
    content = (b"BT /F1 12 Tf 72 700 Td (" + CODE.encode() + b" printed copy for volume test) Tj ET\n"
               b"BT /F1 12 Tf 72 680.2 Td (second line of the body text here) Tj ET\n"
               b"BT /F1 10 Tf 280 30 Td (7) Tj ET\n"
               b"q 200 0 0 150 72 500 cm /Im1 Do Q\n")
    image = zlib.compress(b"\x80")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> /XObject << /Im1 6 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 "
        b"/Filter /FlateDecode /Length %d >>\nstream\n" % len(image) + image + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))
    return path


class PdfGeometry(unittest.TestCase):
    def test_reads_text_lines_picture_box_and_folio(self):
        with tempfile.TemporaryDirectory() as folder:
            printed = read_printed(tiny_pdf(Path(folder) / "작은.pdf"), DEFAULT_CONFIG)
        self.assertEqual(printed.module_code, CODE)
        page = printed.pages[0]
        self.assertEqual(page.folio, "7")                    # 꼬리말 띠의 쪽 번호(본문 요소는 아님)
        texts = [i for i in page.items if i.kind == "text"]
        self.assertEqual(len(texts), 2)
        self.assertTrue(texts[0].text.startswith(CODE))
        self.assertAlmostEqual(texts[0].top - texts[1].top, PITCH, places=1)
        pictures = [i for i in page.items if i.kind == "picture"]
        self.assertEqual(len(pictures), 1)
        self.assertAlmostEqual(pictures[0].top, 650)
        self.assertAlmostEqual(pictures[0].bottom, 500)


if __name__ == "__main__":
    unittest.main()
