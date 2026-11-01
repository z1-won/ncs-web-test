"""NCS_TEST_DATABASE_URL을 지정하면 실제 PostgreSQL 저장·조회·이관을 검사한다."""

import os
import tempfile
import unittest
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import psycopg
from fastapi.testclient import TestClient

from ncs_service import ReviewRequest, execute_review, persist_review
from ncs_service.postgres import get_review, input_metadata, list_reviews, migrate, save_review
from ncs_service.postgres_cli import import_directory
from ncs_web.server import create_app

ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "tests/fixtures/원고_ok_LM1203020201_24v3.hwpx"
PLAN = ROOT / "tests/fixtures/개발계획서_LM1203020201_24v3.hwpx"
DSN = os.getenv("NCS_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def test_save_query_export_and_import(self):
        ids = []
        try:
            review = execute_review(ReviewRequest((MANUSCRIPT, PLAN)))
            inputs = input_metadata(review.result.diagnostics,
                                    [(MANUSCRIPT.name, MANUSCRIPT), (PLAN.name, PLAN)])
            run_id, summary = save_review(DSN, review, inputs)
            ids.append(run_id)
            self.assertEqual(get_review(DSN, run_id)["요약"], summary)
            self.assertEqual(get_review(DSN, run_id)["전체"], review.result.checklist)
            self.assertTrue(any(row["id"] == run_id for row in list_reviews(
                DSN, module_code=review.result.module_code, check="position")))

            with TestClient(create_app(database_url=DSN)) as client:
                self.assertEqual(client.get(f"/api/reviews/{run_id}").status_code, 200)
                self.assertEqual(client.get(f"/api/reviews/{run_id}/zip").status_code, 200)
                response = client.post("/api/review", files=[
                    ("files", (path.name, path.read_bytes())) for path in (MANUSCRIPT, PLAN)
                ])
                self.assertEqual(response.status_code, 200, response.text)
                web_id = response.json()["id"]
                ids.append(web_id)
                self.assertEqual(client.get(f"/api/reviews/{web_id}").json()["전체"],
                                 response.json()["전체"])
                self.assertTrue(all(not Path(value).is_absolute() for value in
                                    get_review(DSN, web_id)["진단"]["inputs"].values() if value))

            with tempfile.TemporaryDirectory() as folder:
                saved = persist_review(review, folder)
                imported_id = str(uuid5(NAMESPACE_URL, f"ncs-review-import:{saved.directory.name}"))
                ids.append(imported_id)
                self.assertTrue(import_directory(DSN, saved.directory))
                self.assertFalse(import_directory(DSN, saved.directory))
                self.assertEqual(get_review(DSN, imported_id)["source"], "import")
        finally:
            with psycopg.connect(DSN) as connection:
                for run_id in ids:
                    connection.execute("DELETE FROM review_runs WHERE id = %s", (run_id,))
