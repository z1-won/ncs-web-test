"""원고 분량 산정 웹 경로(/api/volume) — 최종 원고 하나, 기존 원고 비교, 수작업 대조, 부록 제외, 출력본 PDF, 집필료 단가·계약 분량, 잘못된 입력."""

import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
OK = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
NAME = FIXTURES / "원고_name_LM1203020201_24v3.hwpx"
PRINT = FIXTURES / "출력본_ok_LM1203020201_24v3.pdf"


class VolumeWebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(out_dir=self.out.name))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def post(self, data=None, **files):
        return self.client.post("/api/volume", data=data or {}, files={k: (v.name, v.read_bytes()) for k, v in files.items()})

    def test_manuscript_only_returns_sheet(self):
        response = self.post(manuscript=OK)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["원고"], OK.name)
        self.assertTrue(body["추정"])
        self.assertIsNone(body["변경"])
        self.assertIn("기입 분량", body["합계"])
        self.assertEqual(body["권고 분량"]["상태"], "판단불가")

    def test_previous_and_manual_pages(self):
        response = self.post({"manual_pages": "2"}, manuscript=OK, previous=NAME)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["변경"]["기존 원고"], NAME.name)
        self.assertGreater(body["변경"]["변경 행"], 0)
        self.assertEqual(body["수작업 대조"]["수작업"], 2)

    def test_same_file_name_for_both_is_kept_apart(self):
        response = self.post(manuscript=OK, previous=OK)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["변경"]["변경 행"], 0)

    def test_exclude_appendix_flag(self):
        body = self.post({"include_appendix": "false"}, manuscript=OK).json()
        self.assertIn("제외", body["가정"]["부록"])

    def test_print_copy_unit_price_and_contract_pages(self):
        response = self.post({"unit_price": "46200", "contract_pages": "1"}, manuscript=OK, print_copy=PRINT)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["출력본"]["사용"], body["출력본"]["사유"])
        self.assertEqual(body["출력본"]["파일"], PRINT.name)
        self.assertEqual(body["출력본"]["전체 쪽 수"], 45)
        self.assertIn("출력본", body["채택 분량"]["근거"])
        fee = body["집필료"]
        self.assertEqual((fee["단가"], fee["계약 분량"], fee["인정 분량"]), (46200, 1, 1))
        self.assertEqual(fee["집필료"], 46200)

    def test_fee_defaults_without_inputs(self):
        body = self.post(manuscript=OK).json()
        self.assertIsNone(body["출력본"])
        self.assertEqual(body["집필료"]["단가"], 50000)
        self.assertFalse(body["집필료"]["단가 입력"])

    def test_bad_print_copy_and_fee_inputs_are_400(self):
        response = self.post(manuscript=OK, print_copy=NAME)      # PDF 칸에 hwpx
        self.assertEqual(response.status_code, 400)
        self.assertIn("PDF", response.json()["error"])
        self.assertEqual(self.post({"unit_price": "0"}, manuscript=OK).status_code, 400)
        self.assertEqual(self.post({"unit_price": "만원"}, manuscript=OK).status_code, 400)
        self.assertEqual(self.post({"contract_pages": "-3"}, manuscript=OK).status_code, 400)

    def test_bad_inputs_are_400(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "메모.txt"
            bad.write_text("원고 아님", encoding="utf-8")
            response = self.post(manuscript=bad)
        self.assertEqual(response.status_code, 400)
        self.assertIn("메모.txt", response.json()["error"])
        self.assertEqual(self.client.post("/api/volume").status_code, 400)
        self.assertEqual(self.post({"manual_pages": "0"}, manuscript=OK).status_code, 400)


if __name__ == "__main__":
    unittest.main()
