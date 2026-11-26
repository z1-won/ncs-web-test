"""역할별로 막는 경로 — 판정을 정하는 일과 비용이 드는 검토(LLM 검토, 그림 판독, 의견 반영 검토)는 에디터와 직능연 계정만 한다.

로그인 미들웨어 대신 request.state.account를 넣어 주는 미들웨어를 테스트에서 건다(계정 DB 없음). 계정이 없으면(로그인을 쓰지 않는 서버)
누구나 한다 — 그 경우는 다른 웹 테스트들이 본다. 막힌 요청은 원고를 읽거나 모델을 부르기 전에 403이어야 한다.
"""

import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "tests" / "fixtures" / "원고_ok_LM1203020201_24v3.hwpx"
ROLES = ("author", "reviewer", "committee", "editor", "krivet")
MANAGERS = ("editor", "krivet")


class RoleGateTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.app = create_app(out_dir=self.out.name)
        self.role = "author"
        self.called = []

        @self.app.middleware("http")
        async def as_account(request, call_next):
            if self.role:
                request.state.account = {"id": "1", "login": f"t-{self.role}", "name": "시험", "role": self.role}
            return await call_next(request)

        def generate(system, user, *, task):      # LLM 대역 — 불렸는지만 적는다
            self.called.append(task)
            return {"data": {"findings": []}, "usage": {}, "cached": False, "model": "test"}

        self.app.state.llm_review_generate = generate
        self.client = TestClient(self.app)
        self.client.__enter__()
        response = self.client.post("/api/uploads", files=[("files", (MANUSCRIPT.name, MANUSCRIPT.read_bytes()))])
        self.assertEqual(response.status_code, 200, response.text)
        self.token = response.json()["upload"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def gated(self):
        """(이름, 요청을 보내는 함수) — 에디터와 직능연만 되는 경로."""
        token = self.token
        sheet = ("의견서.hwpx", MANUSCRIPT.read_bytes())
        return [
            ("LLM 검토 실행", lambda: self.client.post(f"/api/uploads/{token}/llm-review", data={"tasks": "perform2_brands"})),
            ("LLM 검토 결과", lambda: self.client.get(f"/api/uploads/{token}/llm-review")),
            ("LLM 검토 JSON", lambda: self.client.get(f"/api/uploads/{token}/llm-review/result.json")),
            ("LLM 검토 메모 원고", lambda: self.client.get(f"/api/uploads/{token}/llm-review/memo")),
            ("그림 판독", lambda: self.client.post(f"/api/uploads/{token}/figures/read", data={"limit": "1"})),
            ("의견 반영 검토", lambda: self.client.post("/api/opinion", files=[("manuscript", (MANUSCRIPT.name, MANUSCRIPT.read_bytes())), ("opinions", sheet)])),
            ("의견 반영 결과표", lambda: self.client.post("/api/opinion/export", json={"manuscript": "원고.hwpx", "rows": [], "decisions": {}})),
            ("의견 반영 확정 저장", lambda: self.client.post("/api/opinion/decisions", json={"manuscript": "원고.hwpx", "rows": [], "decisions": {}})),
        ]

    def test_only_editor_and_krivet_pass(self):
        for role in ROLES:
            self.role = role
            for name, send in self.gated():
                with self.subTest(role=role, path=name):
                    response = send()
                    if role in MANAGERS:
                        self.assertNotEqual(response.status_code, 403, response.text)
                    else:
                        self.assertEqual(response.status_code, 403, response.text)
                        self.assertIn("에디터와 직능연 계정만", response.text)

    def test_blocked_request_does_not_call_the_model(self):
        self.role = "author"
        self.client.post(f"/api/uploads/{self.token}/llm-review", data={"tasks": "perform2_brands"})
        self.assertEqual(self.called, [])

    def test_rule_based_results_stay_open_to_authors(self):
        """집필진이 하는 것: 올리기, 규칙 검수, 그림 검수(규칙)와 표 출처 검토 보기, 버튼을 켤지 묻는 상태 경로."""
        self.role = "author"
        for path in (f"/api/uploads/{self.token}/figures", f"/api/uploads/{self.token}/sources", "/api/llm-review/status", "/api/figures/vision-status"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        review = self.client.post("/api/review", data={"upload": self.token, "check": "toc"})
        self.assertEqual(review.status_code, 200, review.text)

    def test_no_account_means_open(self):
        self.role = ""                      # 로그인을 쓰지 않는 서버
        response = self.client.get(f"/api/uploads/{self.token}/llm-review")
        self.assertEqual(response.status_code, 404)      # 막힌 것이 아니라 '아직 하지 않음'


if __name__ == "__main__":
    unittest.main()
