"""원고 분량 산정 웹 경로(/api/volume) — 최종 원고 하나, 기존 원고 비교, 수작업 대조, 부록 제외, 출력본 PDF, 집필료 단가·계약 분량, 잘못된 입력.
DB 모드의 산정 이력(/api/volumes)은 postgres 함수를 가짜로 바꿔 경로 계약만 본다(실제 저장은 tests/integration)."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.assertNotIn("id", body)                       # 파일 저장 모드: 이력에 남기지 않는다
        self.assertEqual(self.client.get("/api/volumes").status_code, 404)
        self.assertTrue(any("추정" in note for note in body["경고"]) and set(body["경고"]) <= set(body["알림"]))
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


RUN_ID = "12345678-1234-1234-1234-123456789abc"


class VolumeHistoryWebTests(unittest.TestCase):
    """DB 모드: 산정하면 이력에 남기고 id를 돌려준다. 목록·열기·삭제 경로가 붙는다."""

    def client(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        return TestClient(create_app(database_url="postgresql://example", require_login=False))

    def post(self, client, data=None, **files):
        return client.post("/api/volume", data=data or {}, files={k: (v.name, v.read_bytes()) for k, v in files.items()})

    def test_saves_result_inputs_and_params_and_returns_id(self):
        with patch("ncs_service.postgres.migrate"), patch("ncs_service.postgres.save_volume", return_value=RUN_ID) as save:
            with self.client() as client:
                response = self.post(client, {"unit_price": "46200", "contract_pages": "1"}, manuscript=OK, previous=OK, print_copy=PRINT)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["id"], RUN_ID)
        self.assertNotIn("저장 오류", body)
        _dsn, result, inputs, params = save.call_args.args
        self.assertEqual({key: value for key, value in body.items() if key != "id"}, result)   # 저장한 산정표 = 돌려준 산정표
        # 같은 이름의 기존 원고도 올린 이름 그대로(임시 폴더의 '기존_' 접두어가 아니라) 해시와 함께 남는다
        self.assertEqual([(item["role"], item["filename"]) for item in inputs],
                         [("manuscript", OK.name), ("previous", OK.name), ("print", PRINT.name)])
        self.assertEqual(inputs[0]["sha256"], hashlib.sha256(OK.read_bytes()).hexdigest())
        self.assertEqual(inputs[2]["byte_size"], PRINT.stat().st_size)
        self.assertEqual(params, {"unit_price": 46200, "contract_pages": 1, "manual_pages": None, "include_appendix": True})

    def test_save_failure_still_returns_the_sheet(self):
        with patch("ncs_service.postgres.migrate"), patch("ncs_service.postgres.save_volume", side_effect=RuntimeError("connection refused\n상세")):
            with self.client() as client, self.assertLogs("ncs_web", level="ERROR"):
                response = self.post(client, manuscript=OK)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsNone(body["id"])
        self.assertIn("connection refused", body["저장 오류"])
        self.assertNotIn("상세", body["저장 오류"])
        self.assertIn("기입 분량", body["합계"])

    def test_bad_input_is_not_saved(self):
        with patch("ncs_service.postgres.migrate"), patch("ncs_service.postgres.save_volume") as save:
            with self.client() as client:
                self.assertEqual(self.post(client, manuscript=OK, print_copy=NAME).status_code, 400)
        save.assert_not_called()

    def test_list_detail_and_delete(self):
        row = {"id": RUN_ID, "manuscript": OK.name, "pages": 2, "fee": 100000}
        detail = {"id": RUN_ID, "원고": OK.name, "합계": {"기입 분량": 2}}
        with patch("ncs_service.postgres.migrate"), patch("ncs_service.postgres.list_volumes", return_value=[row]) as listed, \
             patch("ncs_service.postgres.get_volume", side_effect=[detail, None]), \
             patch("ncs_service.postgres.delete_volume", side_effect=[True, False]) as delete:
            with self.client() as client:
                self.assertEqual(client.get("/api/volumes?module_code=LM1203020201_24v3&limit=5").json(), [row])
                self.assertEqual(listed.call_args.kwargs, {"module_code": "LM1203020201_24v3", "limit": 5, "offset": 0})
                self.assertEqual(client.get(f"/api/volumes/{RUN_ID}").json(), detail)
                missing = client.get("/api/volumes/none")
                self.assertEqual((missing.status_code, missing.json()["error"]), (404, "산정 이력을 찾을 수 없습니다"))
                self.assertEqual(client.delete(f"/api/volumes/{RUN_ID}").status_code, 204)
                self.assertEqual(client.delete("/api/volumes/none").status_code, 404)
                self.assertEqual(client.get("/api/volumes?limit=0").status_code, 400)
        self.assertEqual([call.args[1] for call in delete.call_args_list], [RUN_ID, "none"])


if __name__ == "__main__":
    unittest.main()
