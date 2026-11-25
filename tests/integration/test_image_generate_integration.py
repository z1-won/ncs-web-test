"""NCS_TEST_DATABASE_URL을 지정하면 만든 도표·그래프의 닮은 그림 대조와 이미지 저작권 DB 등록(REQ-02-006 ①)을 실제 PostgreSQL로 검사한다.

그리기에는 한글 글꼴이 있어야 한다(없으면 건너뛴다). 테스트가 넣은 그림은 끝날 때 sha256으로 지운다."""

import hashlib
import io
import os
import unittest
from datetime import date
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from ncs_aiimage import read_spec, render
from ncs_aiimage.draw import font_available
from ncs_service.images import image_generate
from ncs_service.postgres import migrate
from ncs_web.server import create_app

DSN = os.getenv("NCS_TEST_DATABASE_URL")


def spec(tag: str, kind: str = "sequence") -> dict:
    if kind == "bar":
        return {"kind": "bar", "title": f"연도별 건수 {tag}", "unit": "건", "categories": ["2023년", "2024년", "2025년"],
                "series": [{"name": "", "values": [1200, 1850, 2400]}]}
    return {"kind": "sequence", "title": f"예약 접수 {tag}", "items": [{"label": "예약 요청 접수"}, {"label": "객실 현황 확인"}, {"label": f"확인서 발송 {tag}"}]}


def shrunk(png: bytes) -> bytes:
    """같은 그림을 줄여 JPEG로 다시 저장한 것 — 파일은 다르고 그림은 닮았다."""
    from PIL import Image

    image = Image.open(io.BytesIO(png)).convert("RGB")
    buffer = io.BytesIO()
    image.resize((image.width // 3, image.height // 3)).save(buffer, "JPEG", quality=70)
    return buffer.getvalue()


@unittest.skipUnless(DSN and font_available(), "NCS_TEST_DATABASE_URL 미설정 또는 한글 글꼴 없음")
class ImageGenerateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)
        cls.client = TestClient(create_app(database_url=DSN, require_login=False))

    def setUp(self):
        self.tag = uuid4().hex[:6]
        self.used: list[str] = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_assets WHERE sha256 = ANY(%s)", (self.used,))

    def draw(self, raw: dict) -> bytes:
        png = render(raw).png
        self.used.append(hashlib.sha256(png).hexdigest())
        return png

    def test_register_writes_kind_ai_fields_and_placement(self):
        raw = spec(self.tag, "bar")
        png = self.draw(raw)
        done = image_generate.register(DSN, png, read_spec(raw), by="에디터", on=date(2026, 11, 25), tool="Claude",
                                       module_code="LM1203020201_24v3", number="1-2")
        self.assertEqual((done["새 그림"], done["수록 위치"]), (True, 1))
        with psycopg.connect(DSN) as connection:
            row = connection.execute(
                "SELECT a.kind, a.title, r.status, r.category, r.reuse_scope, r.ai_used, r.ai_usage, r.ai_mode, r.ai_tool, r.ai_date, "
                "p.label, p.source_line, h.phash FROM image_assets a JOIN image_rights r ON r.image_id = a.id "
                "JOIN image_placements p ON p.image_id = a.id JOIN image_phashes h ON h.image_id = a.id WHERE a.id = %s", (done["id"],)).fetchone()
        self.assertEqual(row[:12], ("graph", raw["title"], "auto", "author_made", "unknown", True, 1, "generated", "Claude", date(2026, 11, 25),
                                    "그림 1-2", "출처: 집필진 제작(2026)"))
        self.assertRegex(row[12], r"^[0-9a-f]{16}$")
        again = image_generate.register(DSN, png, read_spec(raw), by="에디터", on=date(2026, 11, 25), tool="Claude")
        self.assertEqual((again["id"], again["새 그림"]), (done["id"], False))

    def test_register_without_ai_and_bad_input(self):
        raw = spec(self.tag)
        png = self.draw(raw)
        done = image_generate.register(DSN, png, read_spec(raw), by="에디터", on=date(2026, 11, 25), ai=False)
        with psycopg.connect(DSN) as connection:
            row = connection.execute("SELECT a.kind, r.ai_used, r.ai_tool FROM image_assets a JOIN image_rights r ON r.image_id = a.id WHERE a.id = %s",
                                     (done["id"],)).fetchone()
        self.assertEqual(row, ("table", False, None))
        with self.assertRaises(ValueError):
            image_generate.register(DSN, png, read_spec(raw), by="에디터", on=date(2026, 11, 25))            # AI인데 도구 없음
        with self.assertRaises(ValueError):
            image_generate.register(DSN, png, read_spec(raw), by="에디터", on=date(2026, 11, 25), ai=False, number="1-2")

    def test_similar_finds_same_file_and_resized_copy(self):
        raw = spec(self.tag)
        png = self.draw(raw)
        self.assertIsNone(image_generate.similar(DSN, png)["같은 파일"])
        done = image_generate.register(DSN, png, read_spec(raw), by="에디터", on=date(2026, 11, 25), tool="Claude")
        found = image_generate.similar(DSN, png)
        self.assertEqual(found["같은 파일"], done["id"])
        self.assertEqual((found["닮은 그림"][0]["id"], found["닮은 그림"][0]["방법"], found["닮은 그림"][0]["확정"]), (done["id"], "같은 파일", False))
        near = image_generate.similar(DSN, shrunk(png), limit=20)
        self.assertIsNone(near["같은 파일"])
        hit = [entry for entry in near["닮은 그림"] if entry["id"] == done["id"]]
        self.assertEqual([entry["방법"] for entry in hit], ["지각 해시"])
        self.assertFalse(near["임베딩"])
        # 확정한 그림하고만 견주면 확정 전 그림은 나오지 않는다
        self.assertEqual([e for e in image_generate.similar(DSN, png, confirmed_only=True)["닮은 그림"] if e["id"] == done["id"]], [])

    def test_generated_photo_is_registered_with_usage_and_inspected(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.effect_noise((1024, 768), 60).convert("RGB").save(buffer, "PNG")      # 그림마다 다른 바이트
        png = buffer.getvalue() + b""
        self.used.append(hashlib.sha256(png).hexdigest())
        done = image_generate.register_image(DSN, png, kind="photo", usage=4, title=f"용접 보호구 {self.tag}", by="에디터", on=date(2026, 11, 25), tool="FLUX")
        with psycopg.connect(DSN) as connection:
            row = connection.execute("SELECT a.kind, r.category, r.ai_usage, r.ai_mode, r.ai_tool, r.status FROM image_assets a "
                                     "JOIN image_rights r ON r.image_id = a.id WHERE a.id = %s", (done["id"],)).fetchone()
        self.assertEqual(row, ("photo", "author_made", 4, "generated", "FLUX", "auto"))
        self.assertEqual(image_generate.inspect(png, 150)["dpi"], 173)
        for bad in ({"kind": "table"}, {"usage": 3}, {"tool": ""}):
            with self.assertRaises(ValueError):
                image_generate.register_image(DSN, png, **{"kind": "photo", "usage": 1, "by": "에디터", "on": date(2026, 11, 25), "tool": "FLUX", **bad})
        with self.assertRaises(ValueError):
            image_generate.register_image(DSN, b"not a png", kind="photo", usage=1, by="에디터", on=date(2026, 11, 25), tool="FLUX")
        import base64
        seen = self.client.post("/api/ai-image/generate/inspect", json={"png": base64.b64encode(png).decode()}).json()
        self.assertEqual(seen["닮은 그림"]["같은 파일"], done["id"])

    def test_web_similar_and_register(self):
        raw = spec(self.tag)
        self.draw(raw)
        self.assertTrue(self.client.get("/api/ai-image/generate/status").json()["DB"])
        body = {"spec": raw, "tool": "Claude", "date": "2026-11-25", "by": "에디터"}
        done = self.client.post("/api/ai-image/generate/register", json=body)
        self.assertEqual(done.status_code, 200, done.text)
        found = self.client.post("/api/ai-image/generate/similar", json={"spec": raw}).json()
        self.assertEqual((found["같은 파일"], found["범위"]), (done.json()["id"], "DB의 모든 그림"))
        self.assertEqual(self.client.post("/api/ai-image/generate/register", json={**body, "by": ""}).status_code, 400)
        self.assertEqual(self.client.post("/api/ai-image/generate/register", json={**body, "tool": ""}).status_code, 400)
        self.assertEqual(self.client.post("/api/ai-image/generate/register", json={**body, "number": "1-2"}).status_code, 400)
        self.assertEqual(self.client.post("/api/ai-image/generate/similar", json={"spec": {"kind": "x"}}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
