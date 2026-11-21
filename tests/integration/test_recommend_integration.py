"""NCS_TEST_DATABASE_URL을 지정하면 이미지 추천(/api/recommend/images, REQ-02-011)을 실제 PostgreSQL로 검사한다.

테스트가 넣은 그림은 끝날 때 sha256으로 찾아 지운다. 다른 자료가 섞여 있어도 되게 이 테스트만 쓰는 낱말(tag)로 찾는다.
"""

import hashlib
import os
import unittest
from unittest import mock
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from ncs_service import image_recommend, image_store
from ncs_service.image_db import load_records
from ncs_service.postgres import migrate
from ncs_web.server import create_app

DSN = os.getenv("NCS_TEST_DATABASE_URL")
UNIT = "1203020201_24v3"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (1600).to_bytes(4, "big") + (900).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
KOGL = {"category": "public_license", "ownership": "kogl", "license": {"kogl_type": 4, "kogl_ai": True}, "source_org": "예시기관",
        "source_url": "https://www.kogl.or.kr/x", "retrieved_on": "2026-11-17"}
OWN = {"category": "author_made", "ownership": "government"}


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class RecommendIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)
        cls.client = TestClient(create_app(database_url=DSN, require_login=False))

    def setUp(self):
        self.tag = "낱말" + uuid4().hex[:10]        # 이 테스트가 넣은 그림에만 있는 핵심어
        self.used: list[str] = []
        self.addCleanup(self.cleanup)
        saved = os.environ.pop("NCS_CATALOG_FILE", None)      # 골든 테스트가 꺼 둔 NCS 목록을 이 테스트 동안만 켠다
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, "NCS_CATALOG_FILE", saved)

    def cleanup(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_assets WHERE sha256 = ANY(%s)", (self.used,))

    def add(self, title: str, rights: dict, *, scope: str | None = "all", confirm: bool = True, **fields) -> str:
        """그림 1건을 넣고(필요하면 재사용 범위를 정해 확정) id를 돌려준다."""
        content = PNG + uuid4().bytes
        sha256 = hashlib.sha256(content).hexdigest()
        self.used.append(sha256)
        rights = {**rights, **({"reuse_scope": scope} if scope else {})}
        report = load_records(DSN, [{"content": content, "title": title, "keywords": [self.tag], "rights": rights, **fields}], changed_by="적재")
        self.assertEqual(report.rejected, [])
        with psycopg.connect(DSN) as connection:
            image_id = str(connection.execute("SELECT id FROM image_assets WHERE sha256 = %s", (sha256,)).fetchone()[0])
        if confirm:
            image_store.confirm(DSN, image_id, by="에디팅기관")
        return image_id

    def ask(self, expect: int = 200, **body) -> dict:
        response = self.client.post("/api/recommend/images", json={"use_llm": False, **body})
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def test_only_confirmed_images_with_known_scope_are_recommended(self):
        shown = self.add("확정", OWN)
        self.add("자동 태깅", OWN, confirm=False)
        self.add("범위 미확인", OWN, scope=None)
        self.add("비공개", {**OWN, "release_class": "private"})
        result = self.ask(text=f"{self.tag} 그림을 찾는다")
        self.assertEqual([item["id"] for item in result["items"]], [shown], "권리 미확인 이미지 추천 노출 0건")
        self.assertEqual((result["context"]["method"], result["context"]["keywords"][0], result["guidance"]), ("rule", self.tag, []))
        self.assertNotIn("contexts", result["items"][0])
        self.assertEqual(self.client.get(f"/api/images/recommendable/{shown}/file").status_code, 200)

    def test_order_notes_and_credit(self):
        kogl = self.add("공공누리", KOGL, links=[{"unit_code": UNIT, "element_code": f"{UNIT}.1", "criterion_no": "1.1"}])
        own = self.add("직접 제작", OWN)
        licensed = self.add("이용허락", {"category": "blanket_license", "ownership": "licensed"}, scope="module_only")
        by_keyword = self.ask(text=self.tag)["items"]
        self.assertEqual([item["id"] for item in by_keyword][0], own, "같은 정도로 맞으면 정부 귀속 + 전체 재사용이 앞")
        rows = {item["id"]: item for item in by_keyword}
        self.assertEqual((rows[own]["priority"], rows[licensed]["scope_check_needed"], rows[kogl]["scope_check_needed"]), (True, True, False))
        self.assertEqual(rows[kogl]["conditions"], ["출처표시", "상업적 이용금지", "변경금지"])
        self.assertEqual(rows[kogl]["credit"], "출처: 공공누리 홈페이지(https://www.kogl.or.kr/x)에서 2026. 11. 17. 검색. 공공누리 제4유형.",
                         "출처 문구가 비어 있던 공공누리 그림은 URL·검색일·유형으로 만든다")
        self.assertIn("제4유형 조건이 그대로 적용", rows[kogl]["notes"][0])
        self.assertEqual((rows[own]["credit"], rows[own]["max_width_mm"], rows[own]["low_quality"]), (None, 135, False))

        with_criterion = self.ask(text=self.tag, unit_code="LM1203020201", criterion_no="1.1")
        self.assertEqual((with_criterion["items"][0]["id"], with_criterion["items"][0]["link_level"]), (kogl, "criterion"),
                         "같은 수행준거에 이어진 그림이 앞에 온다")
        self.assertTrue(with_criterion["criterion"]["found"])
        self.assertIn("객실", with_criterion["criterion"]["text"])
        self.assertIn(kogl, [item["id"] for item in self.ask(unit_code=UNIT)["items"]], "문단 없이 능력단위만으로도 찾는다")

    def test_no_match_guides_to_ai_generation_and_bad_requests(self):
        self.add("확정", OWN)          # 후보는 있지만 문단과 맞는 것이 없는 경우
        nothing = self.ask(text=f"없는말{uuid4().hex}")
        self.assertEqual(nothing["items"], [])
        self.assertTrue(any("REQ-02-006" in line for line in nothing["guidance"]))
        self.assertIn("문단을 적거나", self.ask(expect=400)["error"])
        self.assertIn("숫자 10자리", self.ask(expect=400, text="x", unit_code="LM12")["error"])
        self.ask(expect=400, text="x", criterion_no="일점일")
        self.ask(expect=400, text="x", limit=0)

    def test_empty_pool_points_to_confirmation_not_ai_generation(self):
        from unittest import mock
        self.add("범위 미확인", OWN, scope=None)
        self.add("자동 태깅", OWN, confirm=False)
        counts = image_recommend.waiting(DSN)
        self.assertGreaterEqual(min(counts["unknown_scope"], counts["unconfirmed"]), 1)
        with mock.patch.object(image_recommend, "candidates", return_value=[]):
            result = image_recommend.recommend(DSN, text="객실 유형", use_llm=False)
        self.assertEqual((result["items"], result["total_candidates"]), ([], 0))
        text = " ".join(result["guidance"])
        for fragment in ("추천에 쓸 수 있는 그림이 아직 없습니다", f"‘미확인’인 그림이 {counts['unknown_scope']}건", "확정 취소",
                         f"확정하지 않은 그림이 {counts['unconfirmed']}건"):
            self.assertIn(fragment, text)
        self.assertNotIn("REQ-02-006", text)

    def test_llm_answer_is_used_when_given(self):
        self.add("확정", OWN)
        result = image_recommend.recommend(DSN, text=f"{self.tag} 설명 문단", asker=lambda system, user: {
            "data": {"summary": "요약 글", "keywords": [self.tag, "글에없는말"]}, "model": "모델"})
        self.assertEqual((result["context"]["method"], result["context"]["summary"], result["context"]["keywords"], result["context"]["dropped"],
                          len(result["items"])), ("llm", "요약 글", [self.tag], ["글에없는말"], 1))


class FakeEmbedder:
    """그림 내용의 마지막 바이트(0·1·2)를 축으로 삼는 가짜 모델 — 네트워크·모델 파일 없이 흐름만 본다."""
    name = "fake-embedder"
    WORDS = {"객실": 0, "연회장": 1, "주방": 2}

    def images(self, contents):
        return [None if content.endswith(b"broken") else [1.0 if axis == content[-1] else 0.0 for axis in range(3)] for content in contents]

    def text(self, text):
        return [1.0 if any(word in text and axis == index for word, index in self.WORDS.items()) else 0.0 for axis in range(3)]


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class EmbeddingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.used: list[str] = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_assets WHERE sha256 = ANY(%s)", (self.used,))

    def add(self, title: str, axis: int | bytes, **fields) -> str:
        content = PNG + uuid4().bytes + (axis if isinstance(axis, bytes) else bytes([axis]))
        sha256 = hashlib.sha256(content).hexdigest()
        self.used.append(sha256)
        report = load_records(DSN, [{"content": content, "title": title, "rights": {**OWN, "reuse_scope": "all"}, **fields}], changed_by="적재")
        self.assertEqual(report.rejected, [])
        with psycopg.connect(DSN) as connection:
            image_id = str(connection.execute("SELECT id FROM image_assets WHERE sha256 = %s", (sha256,)).fetchone()[0])
        image_store.confirm(DSN, image_id, by="에디팅기관")
        return image_id

    def mine(self, result: dict, ids: list[str]) -> list[dict]:
        return [item for item in result["items"] if item["id"] in ids]

    def test_vectors_are_stored_once_and_used_for_ranking(self):
        from ncs_service import image_embed
        room, hall, kitchen, broken = (self.add("제목 없음 1", 0), self.add("제목 없음 2", 1), self.add("제목 없음 3", 2), self.add("깨진 그림", b"broken"))
        ids = [room, hall, kitchen, broken]
        fake = FakeEmbedder()
        first = image_embed.embed_missing(DSN, fake)
        self.assertGreaterEqual(first["새로 계산"], 3)
        self.assertGreaterEqual(first["읽지 못한 그림"], 1)
        with psycopg.connect(DSN) as connection:
            stored = dict(connection.execute("SELECT image_id::text, vector FROM image_embeddings WHERE model = %s AND image_id = ANY(%s)",
                                             (fake.name, ids)).fetchall())
        self.assertEqual((stored[room], stored[hall], set(stored)), ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], {room, hall, kitchen}))
        again = image_embed.embed_missing(DSN, fake)
        self.assertEqual(again["새로 계산"], 0, "이미 있는 벡터는 다시 계산하지 않는다")
        self.assertGreaterEqual(image_embed.status(DSN, fake.name)["벡터가 있는 그림"], 3)

        # 제목·키워드에 '연회장'이 없어도 그림이 닮은 것을 찾는다
        result = image_recommend.recommend(DSN, text="연회장 배치를 설명한다", use_llm=False, embedder=fake, limit=30)
        found = self.mine(result, ids)
        self.assertEqual((found[0]["id"], found[0]["matched"], found[0]["visual"]), (hall, [], 1.0))
        self.assertNotIn(kitchen, [item["id"] for item in found])
        self.assertTrue(result["embedding"]["used"])
        self.assertEqual((result["embedding"]["model"], result["embedding"]["query"]), (fake.name, "연회장 배치"))
        self.assertTrue(all("vector" not in item for item in result["items"]))

        # 임베딩이 꺼져 있으면 예전 방식 그대로(이 그림들은 핵심어가 없어 나오지 않는다)
        with mock.patch.dict(os.environ, {"NCS_EMBED_MODEL": ""}):
            off = image_recommend.recommend(DSN, text="연회장 배치를 설명한다", use_llm=False, limit=30)
        self.assertEqual((self.mine(off, ids), off["embedding"]["used"]), ([], False))
        self.assertIn("꺼져", off["embedding"]["note"])

    def test_deleting_an_image_removes_its_vector(self):
        from ncs_service import image_embed
        image_id = self.add("지울 그림", 0)
        image_embed.embed_missing(DSN, FakeEmbedder())
        self.cleanup()
        with psycopg.connect(DSN) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM image_embeddings WHERE image_id = %s", (image_id,)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
