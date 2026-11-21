"""NCS_TEST_DATABASE_URL을 지정하면 원고 진행 현황(REQ-02-007)의 저장·목록·조회를 실제 PostgreSQL로 검사한다."""

import os
import unittest
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from ncs_service.postgres import list_manuscripts, migrate, progress_sources, save_work_record
from ncs_service.progress import OPINION, RECORDED, RIGHTS, build
from ncs_web.server import create_app

DSN = os.getenv("NCS_TEST_DATABASE_URL")
CODE = "LM9999999901_26v1"     # 다른 테스트·실제 기록과 겹치지 않는 코드
COUNTS = {"전체": {"총 의견": 3}, "차수별": {
    "1차": {"총 의견": 2, "조치 요구": 2, "반영 후보": 1, "미반영 후보": 1, "확인 필요": 0, "조치 불필요": 0},
    "심의": {"총 의견": 1, "조치 요구": 1, "반영 후보": 0, "미반영 후보": 0, "확인 필요": 1, "조치 불필요": 0}}, "생성형 AI": "미사용"}


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class ProgressIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.clean()

    def tearDown(self):
        self.clean()

    def clean(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM work_records WHERE module_code = %s OR manuscript LIKE %s", (CODE, "진행현황테스트%"))
            connection.execute("DELETE FROM volume_runs WHERE module_code = %s", (CODE,))
            connection.execute("DELETE FROM review_runs WHERE module_code = %s", (CODE,))

    def seed(self):
        name = f"진행현황테스트_{CODE}.hwpx"
        saved = save_work_record(DSN, OPINION, name, COUNTS, [{"role": "manuscript", "filename": name}])
        self.assertEqual(saved["module_code"], CODE)                       # 파일 이름에서 읽는다
        save_work_record(DSN, RIGHTS, "진행현황테스트_코드없음.hwpx", {"판정": "부적합", "원고 그림": 4, "누락": 1}, [], module_code=CODE)
        loose = save_work_record(DSN, RIGHTS, "진행현황테스트_코드없음.hwpx", {"판정": "적합"}, [], module_code="엉뚱한 값")
        self.assertEqual(loose["module_code"], "")                         # 코드가 없으면 어느 원고에도 붙지 않는다
        group = str(uuid4())
        with psycopg.connect(DSN) as connection:
            for check, verdict in (("toc", "부적합"), ("position", "적합")):
                run = str(uuid4())
                connection.execute("INSERT INTO review_runs (id, check_name, module_code, verdict, group_id) VALUES (%s, %s, %s, %s, %s)",
                                   (run, check, CODE, verdict, group))
                connection.execute(
                    "INSERT INTO review_results (run_id, summary, sheet, diagnostics, findings, checklist) VALUES (%s, '{}', %s, '{}', '[]', '[]')",
                    (run, psycopg.types.json.Jsonb([{"번호": "①", "검수결과": verdict}])))
            connection.execute("INSERT INTO review_runs (id, check_name, module_code, verdict) VALUES (%s, 'plan', %s, '적합')", (str(uuid4()), CODE))
            connection.execute(
                "INSERT INTO volume_runs (id, module_code, manuscript, pages, unit_price, fee, params, inputs, result) "
                "VALUES (%s, %s, %s, 80, 50000, 4000000, '{}', '[]', '{}')", (str(uuid4()), CODE, name))

    def test_sources_list_and_build(self):
        self.assertIsNone(progress_sources(DSN, CODE))
        self.seed()
        row = next(r for r in list_manuscripts(DSN, limit=100) if r["module_code"] == CODE)
        self.assertEqual(row["records"], 6)                                # 검수 2 + 계획서 1 + 분량 1 + 의견 1 + 권리 1
        self.assertEqual(row["kinds"], sorted(["plan", "review", "group", "volume", "rights", "opinion", "opinion:1차", "opinion:심의"]))
        self.assertFalse(any(r["module_code"] == "" for r in list_manuscripts(DSN, limit=100)))
        result = build(CODE, progress_sources(DSN, CODE))
        by = {s["번호"]: s["상태"] == RECORDED for s in result["단계"]}
        self.assertEqual(by, {1: True, 2: True, 3: True, 4: False, 5: True, 6: True, 7: True})
        self.assertEqual(result["진행도"]["편집 검수"]["항목"], {"적합": 1, "부적합": 1, "판단불가": 0, "그 밖": 0})
        self.assertEqual(result["진행도"]["저작권 검수"]["권리 증빙"]["누락"], 1)
        self.assertEqual(result["진행도"]["분량"]["pages"], 80)
        self.assertEqual(result["기록 수"]["분량 산정"], 1)

    def test_web_routes(self):
        self.seed()
        with TestClient(create_app(database_url=DSN)) as client:
            listed = client.get("/api/manuscripts", params={"limit": 100})
            self.assertEqual(listed.status_code, 200, listed.text)
            row = next(r for r in listed.json() if r["module_code"] == CODE)
            self.assertEqual((row["stages_recorded"], row["name"]), (6, ""))
            detail = client.get(f"/api/manuscripts/{CODE}")
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(len(detail.json()["단계"]), 7)
            self.assertEqual(client.get("/api/manuscripts/LM0000000000_26v1").status_code, 404)
            self.assertEqual(client.get("/api/manuscripts/엉뚱한값").status_code, 400)

if __name__ == "__main__":
    unittest.main()
