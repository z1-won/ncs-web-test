"""NCS_TEST_DATABASE_URL을 지정하면 이미지 추천(/api/recommend/images, REQ-02-011)을 실제 PostgreSQL로 검사한다.

테스트가 넣은 그림은 끝날 때 sha256으로 찾아 지운다. 다른 자료가 섞여 있어도 되게 이 테스트만 쓰는 낱말(tag)로 찾는다.
"""

import hashlib
import os
import unittest
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
        cls.client = TestClient(create_app(database_url=DSN))

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
        nothing = self.ask(text=f"없는말{uuid4().hex}")
        self.assertEqual(nothing["items"], [])
        self.assertTrue(any("REQ-02-006" in line for line in nothing["guidance"]))
        self.assertIn("문단을 적거나", self.ask(expect=400)["error"])
        self.assertIn("숫자 10자리", self.ask(expect=400, text="x", unit_code="LM12")["error"])
        self.ask(expect=400, text="x", criterion_no="일점일")
        self.ask(expect=400, text="x", limit=0)

    def test_llm_answer_is_used_when_given(self):
        self.add("확정", OWN)
        result = image_recommend.recommend(DSN, text=f"{self.tag} 설명 문단", asker=lambda system, user: {
            "data": {"summary": "요약 글", "keywords": [self.tag, "글에없는말"]}, "model": "모델"})
        self.assertEqual((result["context"]["method"], result["context"]["summary"], result["context"]["keywords"], result["context"]["dropped"],
                          len(result["items"])), ("llm", "요약 글", [self.tag], ["글에없는말"], 1))


if __name__ == "__main__":
    unittest.main()
