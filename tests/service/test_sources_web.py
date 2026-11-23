"""웹 출처 검토(REQ-02-008) — 결과, 출처 목록, 출처 메모를 단 원고 사본(사람 작업 3번 '한글에 교정하여 저장하고 전달')."""

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "samples" / "LM1203020201_24v3_light.hwpx"      # 출처 줄에 AI 활용을 섞어 적은 그림이 있는 원고


class SourcesWebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(out_dir=self.out.name))
        self.client.__enter__()
        response = self.client.post("/api/uploads", files=[("files", (MANUSCRIPT.name, MANUSCRIPT.read_bytes()))])
        self.assertEqual(response.status_code, 200, response.text)
        self.token = response.json()["upload"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def test_memo_copy_carries_the_source_findings(self):
        review = self.client.get(f"/api/uploads/{self.token}/sources").json()
        problems = [row for row in review["rows"] if row["판정"] != "적합"]
        self.assertTrue(problems)
        memo = self.client.get(f"/api/uploads/{self.token}/sources/memo")
        self.assertEqual(memo.status_code, 200, memo.text)
        summary = json.loads(memo.headers["X-Memo-Summary"])
        self.assertGreater(summary["placed"], 0)
        with zipfile.ZipFile(io.BytesIO(memo.content)) as archive:        # 열 수 있는 hwpx이고 본문 구역이 그대로 있다
            self.assertIn("Contents/section1.xml", archive.namelist())


if __name__ == "__main__":
    unittest.main()
