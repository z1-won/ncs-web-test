"""원고 문장 추천 웹 경로(/api/suggest·/api/suggest/sentence·/api/suggest/kinds) — AI 미설정(판단불가·이유, 200), 문장 하나, 잘못된 입력.

웹 경로에는 가짜 LLM을 넣을 수 없으므로 테스트 환경(키 없음)의 미설정 경로만 본다. AI 판정은 tests/engines/test_suggest.py가 본다."""

import tempfile
import unittest
from pathlib import Path

from tests.engines.test_suggest import write_manuscript



class SuggestWebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(out_dir=self.out.name))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def test_kinds(self):
        body = self.client.get("/api/suggest/kinds").json()
        names = [kind["이름"] for kind in body["종류"]]
        self.assertIn("교수 방법", names)
        self.assertEqual(len(names), 9)

    def test_manuscript_without_ai_is_undecided(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_manuscript(Path(folder) / "원고_LM1203020201_24v3.hwpx")
            response = self.client.post("/api/suggest", files={"manuscript": (path.name, path.read_bytes())})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["원고"], "원고_LM1203020201_24v3.hwpx")
        self.assertTrue(body["AI"]["상태"].startswith("AI 미설정"), body["AI"])   # 테스트 환경에는 키·승인이 없다
        self.assertEqual(body["구성"], [])                                           # 규칙으로 대신 판정하지 않는다
        self.assertGreater(body["요약"]["검사한 문장"], 0)
        self.assertFalse(any(Path(self.out.name).iterdir()))          # 결과를 저장하지 않는다

    def test_sentence_without_ai_is_undecided(self):
        response = self.client.post("/api/suggest/sentence", data={"text": "절차를 설명함.", "kind": "교수 방법"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["상태"], body["후보"]), ("판단불가", []))
        self.assertTrue(body["AI"].startswith("AI 미설정"))

    def test_bad_inputs_are_400(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "메모.txt"
            bad.write_text("원고 아님", encoding="utf-8")
            response = self.client.post("/api/suggest", files={"manuscript": (bad.name, bad.read_bytes())})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/api/suggest").status_code, 400)
        self.assertEqual(self.client.post("/api/suggest/sentence", data={"text": "문장", "kind": "없는 종류"}).status_code, 400)
        self.assertEqual(self.client.post("/api/suggest/sentence", data={"text": " ", "kind": "교수 방법"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
