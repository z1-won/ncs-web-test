"""NCS_TEST_DATABASE_URL을 지정하면 실제 PostgreSQL 저장·조회·이관을 검사한다."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import psycopg
from fastapi.testclient import TestClient

from ncs_service import ReviewRequest, execute_review, persist_review
from ncs_service.postgres import (delete_review, get_manuscript, get_review, input_metadata, list_reviews, migrate,
                                  save_review)
from ncs_service.postgres_cli import import_directory
from ncs_web.server import create_app

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "tests/fixtures/원고_ok_LM1203020201_24v3.hwpx"
PLAN = ROOT / "tests/fixtures/개발계획서_LM1203020201_24v3.hwpx"
DSN = os.getenv("NCS_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def test_cli_without_out_saves_history_only_as_cli_source(self):
        """검수 CLI: DATABASE_URL이 있고 --out이 없으면 DB 이력에만 남긴다(출처 cli, 입력 기록·원고 보관 포함)."""
        run_id = None
        try:
            with tempfile.TemporaryDirectory() as folder:
                done = subprocess.run(
                    [sys.executable, "-m", "ncs_toc", str(MANUSCRIPT), str(PLAN)], cwd=folder,
                    env={**{k: v for k, v in os.environ.items() if k != "PYTHONPATH"}, "DATABASE_URL": DSN},
                    capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                match = re.search(r"DB 이력 ([0-9a-f-]{36})", done.stdout)
                self.assertIsNotNone(match, done.stdout[-300:])
                run_id = match.group(1)
                self.assertEqual(os.listdir(folder), [], "폴더를 만들지 않는다")
            found = get_review(DSN, run_id)
            self.assertEqual((found["source"], found["check"]), ("cli", "toc"))
            self.assertEqual(found["진단"]["inputs"], {"manuscript": MANUSCRIPT.name, "plan": PLAN.name})
            self.assertEqual(get_manuscript(DSN, run_id), (MANUSCRIPT.name, MANUSCRIPT.read_bytes()))
        finally:
            if run_id:
                delete_review(DSN, run_id)

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

            with TestClient(create_app(database_url=DSN)) as client:
                self.assertEqual(client.delete(f"/api/reviews/{web_id}").status_code, 204)
                self.assertEqual(client.delete(f"/api/reviews/{web_id}").status_code, 404)
            self.assertIsNone(get_review(DSN, web_id))
            with psycopg.connect(DSN) as connection:
                for table in ("review_results", "review_inputs"):
                    self.assertEqual(connection.execute(
                        f"SELECT count(*) FROM {table} WHERE run_id = %s", (web_id,)).fetchone()[0], 0, table)
            self.assertFalse(delete_review(DSN, "not-a-uuid"))

            # 전체 실행 묶음: 토큰으로 두 검수 → /api/groups 한 줄 → 상세 → 삭제 시 묶음 전체가 지워진다
            with TestClient(create_app(database_url=DSN)) as client:
                token = client.post("/api/uploads", files=[
                    ("files", (path.name, path.read_bytes())) for path in (MANUSCRIPT, PLAN)
                ]).json()
                group_ids = []
                for check in ("position", "toc"):
                    run = client.post("/api/review", data={"check": check, "upload": token["upload"], "group": token["group"]})
                    self.assertEqual(run.status_code, 200, run.text)
                    self.assertEqual(run.json()["group"], token["group"])
                    group_ids.append(run.json()["id"])
                ids.extend(group_ids)
                groups = client.get("/api/groups").json()
                mine = next(g for g in groups if g["group_id"] == token["group"])
                self.assertEqual(mine["checks"], ["position", "toc"])
                self.assertIn(mine["verdict"], ("적합", "부적합", "판단불가"))
                self.assertTrue(all(row["id"] not in group_ids for row in client.get("/api/reviews?standalone=true").json()))
                detail = client.get(f"/api/groups/{token['group']}").json()
                self.assertEqual([run["check"] for run in detail["runs"]], ["position", "toc"])
                self.assertEqual(client.delete(f"/api/groups/{token['group']}").status_code, 204)
                self.assertEqual(client.get(f"/api/groups/{token['group']}").status_code, 404)
                self.assertTrue(all(get_review(DSN, run_id) is None for run_id in group_ids))
        finally:
            with psycopg.connect(DSN) as connection:
                for run_id in ids:
                    connection.execute("DELETE FROM review_runs WHERE id = %s", (run_id,))
