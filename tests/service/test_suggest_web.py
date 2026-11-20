"""원고 문장 추천 웹 경로(/api/suggest·/api/suggest/sentence·/api/suggest/kinds) — 원고 카드, 문장 하나, AI 요청(차단 이유), 잘못된 입력."""

import tempfile
import unittest
from pathlib import Path

from tests.engines.test_suggest import write_manuscript

ROOT = Path(__file__).resolve().parents[2]
OK = ROOT / "tests" / "fixtures" / "원고_ok_LM1203020201_24v3.hwpx"


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

    def test_manuscript_cards(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_manuscript(Path(folder) / "원고_LM1203020201_24v3.hwpx")
            response = self.client.post("/api/suggest", files={"manuscript": (path.name, path.read_bytes())})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["원고"], "원고_LM1203020201_24v3.hwpx")
        cards = [card for part in body["구성"] for card in part["문장"]]
        self.assertTrue(cards and all(card["후보"][0]["순위"] == 1 for card in cards))
        self.assertEqual(body["AI"]["상태"], "AI 미사용 — 요청하지 않음")
        self.assertFalse(any(Path(self.out.name).iterdir()))          # 결과를 저장하지 않는다

    def test_clean_manuscript_has_no_cards(self):
        body = self.client.post("/api/suggest", files={"manuscript": (OK.name, OK.read_bytes())}).json()
        self.assertEqual(body["구성"], [])
        self.assertGreater(body["요약"]["검사한 문장"], 0)

    def test_sentence_and_ai_blocked(self):
        response = self.client.post("/api/suggest/sentence", data={"text": "절차를 설명함.", "kind": "교수 방법", "use_llm": "true"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["후보"][0]["문장"], "절차를 설명한다.")
        self.assertIn("ALLOWED_TASKS", body["AI"])

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
