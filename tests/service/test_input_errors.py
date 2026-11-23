"""잘못된 입력에 대한 안내(2026-11-23 QA, 1123-U01~U07) — 오류로 죽지 않고, 이용자가 읽을 말로 알린다."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from ncs_web.server import create_app

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "tests" / "fixtures" / "원고_ok_LM1203020201_24v3.hwpx"
PLAN = ROOT / "tests" / "fixtures" / "개발계획서_LM1203020201_24v3.hwpx"


def part(path, name=None):
    return (name or path.name, path.read_bytes(), "application/octet-stream")


class InputErrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = TestClient(create_app(out_dir=Path(self.temp.name) / "r", dist_dir=Path(self.temp.name) / "none"))
        self.addCleanup(self.client.close)

    def error(self, response, status=400):
        self.assertEqual(response.status_code, status, response.text)
        return response.json()["error"]

    def test_validation_messages_are_korean(self):
        price = self.error(self.client.post("/api/volume", files={"manuscript": part(MANUSCRIPT)}, data={"unit_price": "-5"}))
        self.assertEqual(price, "원고료 단가는 0보다 커야 합니다")
        text = self.error(self.client.post("/api/volume", files={"manuscript": part(MANUSCRIPT)}, data={"unit_price": "오만원"}))
        self.assertEqual(text, "원고료 단가는 숫자로 적어 주세요")
        missing = self.error(self.client.post("/api/opinion", files={"manuscript": part(MANUSCRIPT)}))
        self.assertEqual(missing, "의견서를 올려 주세요")
        for message in (price, text, missing):
            self.assertNotRegex(message, r"[A-Za-z_]{4,}")          # 영어 문구나 내부 칸 이름이 없다

    def test_not_a_hangul_file_and_empty_file(self):
        junk = self.error(self.client.post("/api/review", data={"check": "toc"}, files=[("files", ("메모.hwpx", b"not hwpx", "text/plain"))]))
        self.assertEqual(junk, "한글 파일(hwp, hwpx)이 아닙니다: 메모.hwpx")
        empty = self.error(self.client.post("/api/review", data={"check": "toc"}, files=[("files", ("빈파일.hwpx", b"", "text/plain"))]))
        self.assertIn("내용이 없는 파일입니다", empty)
        self.assertIn("빈파일.hwpx", empty)
        token = self.error(self.client.post("/api/uploads", files=[("files", ("빈파일.hwpx", b"", "text/plain"))]))
        self.assertIn("내용이 없는 파일입니다", token)

    def test_volume_refuses_a_file_that_is_not_a_manuscript(self):
        message = self.error(self.client.post("/api/volume", files={"manuscript": part(PLAN)}))
        self.assertIn("학습모듈 원고가 아닌 것으로 보입니다", message)
        self.assertEqual(self.client.post("/api/volume", files={"manuscript": part(MANUSCRIPT)}).status_code, 200)

    def test_setup_words_are_not_shown(self):
        draft = self.error(self.client.post("/api/plan/draft", json={"duty": "00000000"}))
        self.assertNotIn("scripts/", draft)
        saved = self.error(self.client.post("/api/rights/check", data={"save": "true", "by": "홍"}, files=[("manuscript", part(MANUSCRIPT))]))
        self.assertNotIn("DATABASE_URL", saved)


class UpscalePlanTests(unittest.TestCase):
    def test_zero_dpi_picture_is_skipped_not_a_crash(self):
        """해상도가 0으로 계산되는 그림(아주 작은 그림을 크게 넣은 것)이 있어도 목록을 만든다 — 0으로 나누지 않는다."""
        from ncs_upscale.pipeline import plan

        class Engine:
            def pick_scale(self, need, max_scale):
                return 2

        records = [{"bin_id": "image1", "data": b"x", "dpi": 0, "format": "png", "px": (1, 1)},
                   {"bin_id": "image2", "data": b"x", "dpi": 100, "format": "png", "px": (100, 100)}]
        jobs, skipped = plan(records, {}, Engine(), target_dpi=300, max_scale=4)
        self.assertEqual([job.bin_id for job in jobs], ["image2"])
        self.assertEqual([(item["record"]["bin_id"], item["이유"]) for item in skipped], [("image1", "해상도를 계산하지 못함(그림 크기가 0에 가까움)")])


if __name__ == "__main__":
    unittest.main()
