"""웹 그림 검수 — 규칙 결과(005 행·009 레코드·썸네일·검수표·CSV·메모)는 바로, 그림 판독은 누를 때만(가짜 그림 모델).

네트워크를 쓰지 않는다: app.state.figure_vision에 FakeVision을 넣는다.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "tests" / "fixtures" / "원고_ok_LM1203020201_24v3.hwpx"   # 그림 1자리(깨진 그림)
FINAL = next(ROOT.glob("samples/최종본_SW제품기획/LM2001010409_19v4_*.hwpx"), None)  # 실제 그림이 있는 최종본(저장소 밖 자료)


def fake_answer(task, text):
    return {"판독": {"유형": "도표", "설명": "상자와 화살표", "그림 속 글자": [], "키워드": ["시험"], "맥락 요약": "", "확신도": 0.5},
            "캡션": {"판정": "uncertain", "근거": "판단 근거 부족", "읽은 글자": []}}


class FigureWebTests(unittest.TestCase):
    manuscript = MANUSCRIPT

    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.app = create_app(out_dir=self.out.name)
        self.client = TestClient(self.app)
        self.client.__enter__()
        response = self.client.post("/api/uploads", files=[("files", (self.manuscript.name, self.manuscript.read_bytes()))])
        self.assertEqual(response.status_code, 200, response.text)
        self.token = response.json()["upload"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def test_rules_result_and_files(self):
        response = self.client.get(f"/api/uploads/{self.token}/figures")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("rows", body["review"])
        self.assertIn("위험도", body["review"]["summary"])
        self.assertIn("records", body["tags"])
        self.assertIn("text/html", self.client.get(f"/api/uploads/{self.token}/figures/report.html").headers["content-type"])
        self.assertEqual(self.client.get(f"/api/uploads/{self.token}/figures/figures.csv").status_code, 200)
        self.assertEqual(self.client.get(f"/api/uploads/{self.token}/figures/result.json").status_code, 200)
        memo = self.client.get(f"/api/uploads/{self.token}/figures/memo")
        self.assertEqual(memo.status_code, 200, memo.text)
        self.assertEqual(self.client.get(f"/api/uploads/{self.token}/figures/image/../x.png").status_code, 404)

    def test_risk_waits_for_caption_reading(self):
        """③ 캡션 일치(그림 판독) 전에는 위험도 '판정 안 함', 판독을 전부 하면 005 표를 다시 만들어 위험도를 정한다."""
        if FINAL is None:
            self.skipTest("최종본 없음")
        from ncs_figures.vision import FakeVision
        response = self.client.post("/api/uploads", files=[("files", (FINAL.name, FINAL.read_bytes()))])
        token = response.json()["upload"]
        before = self.client.get(f"/api/uploads/{token}/figures").json()["review"]
        self.assertGreater(before["summary"]["위험도"]["판정 안 함"], 0)
        fake = FakeVision(fake_answer)
        self.app.state.figure_vision = fake
        with mock.patch.dict(os.environ, {"FIG_TRANSFER_OTHERS": ""}):            # 기본 = 모두 보냄
            read = self.client.post(f"/api/uploads/{token}/figures/read", data={"limit": 0}).json()
        self.assertEqual(read["판독한 그림"], read["본문 그림"])
        after = self.client.get(f"/api/uploads/{token}/figures").json()["review"]
        self.assertEqual(after["summary"]["위험도"]["판정 안 함"], 0)
        calls = len(fake.calls)
        self.client.get(f"/api/uploads/{token}/figures/report.html")
        self.assertEqual(len(fake.calls), calls)                                     # 005 표를 다시 만들 때 모델을 새로 부르지 않음

    def test_submissions_upload(self):
        bad = self.client.post(f"/api/uploads/{self.token}/figures/submissions", files=[("files", ("a.pdf", b"%PDF"))])
        self.assertEqual(bad.status_code, 400)
        self.assertIsNone(self.client.get(f"/api/uploads/{self.token}/figures").json()["submissions"])
        form = Path(r"C:\Users\Mint\Desktop\캡스톤디자인\0.공통참고자료") / "F07_계약서_직능연_원고집필·권리양도_2026.hwp"
        if not form.is_file():
            self.skipTest("양식 원본 없음")
        saved = self.client.post(f"/api/uploads/{self.token}/figures/submissions", files=[("files", (form.name, form.read_bytes()))]).json()
        self.assertEqual(saved["파일"], [form.name])                      # 올릴 때는 저장만
        body = self.client.get(f"/api/uploads/{self.token}/figures").json()
        self.assertEqual(body["submissions"]["파일"], [form.name])
        self.assertGreater(body["submissions"]["수록 현황 목록"], 0)
        self.assertEqual(self.client.delete(f"/api/uploads/{self.token}/figures/submissions").status_code, 204)
        self.assertIsNone(self.client.get(f"/api/uploads/{self.token}/figures").json()["submissions"])

    def test_reading_only_on_button_and_respects_transfer_rule(self):
        from ncs_figures.vision import FakeVision
        fake = FakeVision(fake_answer)
        self.app.state.figure_vision = fake
        self.assertEqual(self.client.get(f"/api/uploads/{self.token}/figures/read").status_code, 404)   # 자동 실행 없음
        self.client.get(f"/api/uploads/{self.token}/figures")
        self.assertEqual(fake.calls, [])                                                             # 규칙 결과는 모델을 안 씀
        self.assertTrue(self.client.get("/api/figures/vision-status").json()["available"])
        with mock.patch.dict(os.environ, {"FIG_TRANSFER_OTHERS": "확인 전"}):
            blocked = self.client.post(f"/api/uploads/{self.token}/figures/read", data={"limit": 3}).json()
        self.assertEqual(fake.calls, [])                                                             # 막아 두면 보내지 않음
        self.assertEqual(blocked["합계"]["보냄"], 0)
        with mock.patch.dict(os.environ, {"FIG_TRANSFER_OTHERS": "허용"}):
            sent = self.client.post(f"/api/uploads/{self.token}/figures/read", data={"limit": 3}).json()
        again = self.client.get(f"/api/uploads/{self.token}/figures/read").json()
        self.assertEqual(again["figures"], sent["figures"])

    def test_modules_loaded_at_startup(self):
        """요청 스레드가 그림 모듈을 처음 읽다가 서로 막히지 않게(_DeadlockError) 서버를 만들 때 미리 읽어 둔다."""
        import sys
        for name in ("ncs_figures.pipeline", "ncs_figures.vision", "ncs_figures.tagging", "ncs_figures.export"):
            self.assertIn(name, sys.modules)

    def test_parallel_first_requests(self):
        """화면처럼 그림 결과와 그림 모델 상태를 동시에 불러도 둘 다 성공한다."""
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(4) as pool:
            got = list(pool.map(self.client.get, [f"/api/uploads/{self.token}/figures", "/api/figures/vision-status",
                                                  "/api/llm-review/status", "/api/figures/vision-status"]))
        self.assertEqual([r.status_code for r in got], [200] * 4)

    def test_vision_status_without_approval(self):
        with mock.patch.dict(os.environ, {"LLM_ALLOW_UPLOAD": "", "LLM_ALLOW_IMAGE_UPLOAD": ""}):
            status = self.client.get("/api/figures/vision-status").json()
        self.assertFalse(status["available"])
        self.assertTrue(status["problem"])


@unittest.skipIf(FINAL is None, "최종본 원고 없음")
class FinalFigureWebTests(FigureWebTests):
    """실제 그림이 있는 원고 — 썸네일과 판독 결과까지 본다."""

    manuscript = FINAL

    def test_thumbnails_and_reading(self):
        records = self.client.get(f"/api/uploads/{self.token}/figures").json()["tags"]["records"]
        self.assertTrue(records)
        image = self.client.get(f"/api/uploads/{self.token}/figures/image/{records[0]['image_id']}.png")
        self.assertEqual((image.status_code, image.headers["content-type"]), (200, "image/png"))
        from ncs_figures.vision import FakeVision
        self.app.state.figure_vision = FakeVision(fake_answer)
        with mock.patch.dict(os.environ, {"FIG_TRANSFER_OTHERS": "허용"}):
            sent = self.client.post(f"/api/uploads/{self.token}/figures/read", data={"limit": 2}).json()
        self.assertEqual(sent["합계"]["보냄"], 2)
        self.assertEqual(sent["figures"][0]["판독"]["유형"], "도표")


if __name__ == "__main__":
    unittest.main()
