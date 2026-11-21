"""NCS_TEST_DATABASE_URL을 지정하면 실제 PostgreSQL 저장·조회·이관을 검사한다."""

import hashlib
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
from ncs_service.postgres import (delete_review, delete_volume, get_manuscript, get_review, get_volume, input_metadata,
                                  list_reviews, list_volumes, migrate, save_review)
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

    @staticmethod
    def _kept_files() -> int:
        with psycopg.connect(DSN) as connection:
            return connection.execute("SELECT count(*) FROM review_files").fetchone()[0]

    def test_volume_history_save_list_open_delete(self):
        """원고 분량 산정 이력: 웹에서 산정 → volume_runs에 산정표·넣은 값·입력 파일 해시가 남고(원고 파일은 남지 않는다) 다시 열고 지운다."""
        run_id = None
        kept = self._kept_files()
        try:
            with TestClient(create_app(database_url=DSN, require_login=False)) as client:
                response = client.post("/api/volume", data={"unit_price": "46200", "contract_pages": "1"},
                                       files={"manuscript": (MANUSCRIPT.name, MANUSCRIPT.read_bytes())})
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                run_id = body["id"]
                self.assertRegex(run_id, r"^[0-9a-f-]{36}$")
                row = next(item for item in client.get("/api/volumes").json() if item["id"] == run_id)
                self.assertEqual((row["manuscript"], row["module_code"], row["unit_price"], row["unit_given"]),
                                 (MANUSCRIPT.name, "LM1203020201_24v3", 46200, True))
                self.assertEqual((row["pages"], row["fee"]), (body["집필료"]["산정 분량"], body["집필료"]["집필료"]))
                detail = client.get(f"/api/volumes/{run_id}").json()
                sheet = {key: value for key, value in body.items() if key != "id"}
                self.assertEqual({key: detail[key] for key in sheet}, sheet)        # 다시 연 산정표 = 산정 때 돌려준 산정표
                self.assertEqual(detail["입력"]["값"]["contract_pages"], 1)
                self.assertEqual(detail["입력"]["파일"][0]["sha256"], hashlib.sha256(MANUSCRIPT.read_bytes()).hexdigest())
                default = client.post("/api/volume", files={"manuscript": (MANUSCRIPT.name, MANUSCRIPT.read_bytes())}).json()
                try:
                    listed = {item["id"]: item for item in list_volumes(DSN, module_code="LM1203020201_24v3")}
                    self.assertFalse(listed[default["id"]]["unit_given"])
                    self.assertEqual([item["id"] for item in list_volumes(DSN)][:2], [default["id"], run_id])   # 최신순
                finally:
                    delete_volume(DSN, default["id"])
                self.assertEqual(client.delete(f"/api/volumes/{run_id}").status_code, 204)
                self.assertEqual(client.get(f"/api/volumes/{run_id}").status_code, 404)
            self.assertIsNone(get_volume(DSN, run_id))
            self.assertFalse(delete_volume(DSN, "not-a-uuid"))
            self.assertEqual(self._kept_files(), kept, "원고 보관 표(review_files)에는 아무것도 넣지 않는다")
        finally:
            if run_id:
                delete_volume(DSN, run_id)

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

            with TestClient(create_app(database_url=DSN, require_login=False)) as client:
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

            with TestClient(create_app(database_url=DSN, require_login=False)) as client:
                self.assertEqual(client.delete(f"/api/reviews/{web_id}").status_code, 204)
                self.assertEqual(client.delete(f"/api/reviews/{web_id}").status_code, 404)
            self.assertIsNone(get_review(DSN, web_id))
            with psycopg.connect(DSN) as connection:
                for table in ("review_results", "review_inputs"):
                    self.assertEqual(connection.execute(
                        f"SELECT count(*) FROM {table} WHERE run_id = %s", (web_id,)).fetchone()[0], 0, table)
            self.assertFalse(delete_review(DSN, "not-a-uuid"))

            # 전체 실행 묶음: 토큰으로 두 검수 → /api/groups 한 줄 → 상세 → 삭제 시 묶음 전체가 지워진다
            with TestClient(create_app(database_url=DSN, require_login=False)) as client:
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
