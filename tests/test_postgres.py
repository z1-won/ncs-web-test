"""PostgreSQL 모드의 웹 계약과 기존 파일 이관 형식을 검증한다."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from ncs_service import ReviewRequest, execute_review, persist_review
from ncs_service.postgres import input_metadata, summary_for
from ncs_service.postgres_cli import import_directory
from ncs_web.server import create_app

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"


class PostgresModeTests(unittest.TestCase):
    def test_database_summary_matches_file_report_for_each_check(self):
        with tempfile.TemporaryDirectory() as folder:
            for check in ("position", "toc", "overview", "knowledge"):
                with self.subTest(check=check):
                    review = execute_review(ReviewRequest((MANUSCRIPT, PLAN), check))
                    self.assertEqual(summary_for(review), persist_review(review, Path(folder) / check).summary)

    def test_input_metadata_records_role_and_hash(self):
        review = execute_review(ReviewRequest((MANUSCRIPT, PLAN)))
        items = input_metadata(review.result.diagnostics, [(MANUSCRIPT.name, MANUSCRIPT), (PLAN.name, PLAN)])
        self.assertEqual({item["role"] for item in items}, {"manuscript", "plan"})
        self.assertTrue(all(len(item["sha256"]) == 64 and item["byte_size"] > 0 for item in items))

    def test_database_web_response_history_and_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "results"
            with patch("ncs_service.postgres.migrate"), patch("ncs_service.postgres.save_review") as save:
                save.return_value = ("12345678-1234-1234-1234-123456789abc", {"검수결과": "적합", "항목": {}})
                app = create_app(out_dir=output, database_url="postgresql://example")
                with TestClient(app) as client:
                    response = client.post("/api/review", files=[
                        ("files", (path.name, path.read_bytes())) for path in (MANUSCRIPT, PLAN)
                    ])
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["id"], "12345678-1234-1234-1234-123456789abc")
            self.assertIsNone(response.json()["저장"])
            self.assertFalse(output.exists())
            self.assertEqual({item["role"] for item in save.call_args.args[2]}, {"manuscript", "plan"})

            detail = {
                "check": "position", "module_code": response.json()["module_code"],
                "전체": response.json()["전체"], "지적사항": response.json()["지적사항"],
                "진단": response.json()["진단"], "검수확인서": response.json()["검수확인서"],
            }
            with patch("ncs_service.postgres.migrate"), patch("ncs_service.postgres.get_review", return_value=detail), \
                 patch("ncs_service.postgres.list_reviews", return_value=[{"id": response.json()["id"]}]):
                with TestClient(create_app(database_url="postgresql://example")) as client:
                    self.assertEqual(len(client.get("/api/reviews").json()), 1)
                    self.assertEqual(client.get(f"/api/reviews/{response.json()['id']}").json(), detail)
                    exported = client.get(f"/api/reviews/{response.json()['id']}/zip")
                    self.assertEqual(exported.status_code, 200)
                    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
                        self.assertIsNone(archive.testzip())

    def test_existing_folder_can_be_imported_without_mutation(self):
        folder = next((ROOT / "webapp" / "결과").glob("*"), None)
        if folder is None:
            self.skipTest("기존 결과 폴더가 없음")
        with patch("ncs_service.postgres_cli.import_review", return_value=True) as imported:
            self.assertTrue(import_directory("postgresql://example", folder))
        self.assertIn(imported.call_args.kwargs["check"], ("position", "toc", "overview", "knowledge"))
        self.assertIsInstance(imported.call_args.kwargs["checklist"], list)


if __name__ == "__main__":
    unittest.main()
