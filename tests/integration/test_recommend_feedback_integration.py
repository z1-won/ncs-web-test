"""NCS_TEST_DATABASE_URL을 지정하면 이미지 추천의 그림 설명(설명 색인)과 선택 기록(REQ-02-011)을 실제 PostgreSQL로 검사한다.

그림 모델은 ncs_figures.vision.FakeVision 대역 — 외부로 아무것도 보내지 않는다. 테스트가 넣은 그림은 끝날 때 sha256으로 지운다
(그림을 지우면 설명과 선택 기록도 함께 지워진다)."""

import hashlib
import io
import os
import unittest
from unittest import mock
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from ncs_figures.vision import FakeVision, VisionError
from ncs_recommend import context as ctx
from ncs_recommend import evaluate
from ncs_service.images import image_choices, image_describe, image_recommend, image_store
from ncs_service.images.image_db import load_records
from ncs_service.postgres import migrate
from ncs_web.server import create_app

DSN = os.getenv("NCS_TEST_DATABASE_URL")
KOGL = {"category": "public_license", "ownership": "kogl", "license": {"kogl_type": 1}, "source_org": "예시기관",
        "source_url": "https://www.kogl.or.kr/x", "retrieved_on": "2026-11-17"}
OWN = {"category": "author_made", "ownership": "government"}


def png(color: tuple[int, int, int]) -> bytes:
    """그림 모델에 보낼 수 있는 진짜 PNG(작은 단색) — 색이 다르면 다른 그림이다."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, "PNG")
    return buffer.getvalue()


def described(keywords, scene="호텔 로비의 접수대. 긴 나무 카운터가 가운데에 있다.", **more):
    return {"kind": "photo", "scene": scene, "objects": [{"name": "카운터", "detail": "긴 나무", "position": "가운데"}], "visible_text": ["HOTEL"],
            "keywords": list(keywords), **more}


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)
        cls.client = TestClient(create_app(database_url=DSN, require_login=False))

    def setUp(self):
        self.tag = "낱말" + uuid4().hex[:10]
        self.used: list[str] = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_assets WHERE sha256 = ANY(%s)", (self.used,))

    def add(self, title: str, rights: dict, *, scope: str | None = "all", confirm: bool = True, keywords=None, **fields) -> str:
        content = png(tuple(uuid4().bytes[:3]))
        sha256 = hashlib.sha256(content).hexdigest()
        self.used.append(sha256)
        rights = {**rights, **({"reuse_scope": scope} if scope else {})}
        report = load_records(DSN, [{"content": content, "title": title, "keywords": [self.tag] if keywords is None else keywords,
                                     "rights": rights, **fields}], changed_by="적재")
        self.assertEqual(report.rejected, [])
        with psycopg.connect(DSN) as connection:
            image_id = str(connection.execute("SELECT id FROM image_assets WHERE sha256 = %s", (sha256,)).fetchone()[0])
        if confirm:
            image_store.confirm(DSN, image_id, by="에디팅기관")
        return image_id

    def mine(self, pool):
        """후보 가운데 이 테스트가 넣은 그림만."""
        return [row for row in pool if row["sha256"] in self.used]


class DescribeIntegrationTests(Base):
    def forget_fillers(self):
        """다른 자료의 그림에 채워 둔 자리 채움 설명을 지운다."""
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_descriptions WHERE engine IN ('fake:a', 'fake:b') AND scene = '다른 자료'")

    def test_only_public_pictures_are_sent_by_default_and_once_per_engine(self):
        public = self.add("공공누리 사진", KOGL, keywords=[])
        manuscript = self.add("원고에서 온 그림", OWN, keywords=[])
        private = self.add("비공개 그림", {**KOGL, "release_class": "private"}, keywords=[])
        model = FakeVision(lambda task, text: described([self.tag, "프런트 데스크"]), name="fake:a")
        with psycopg.connect(DSN) as connection:      # 다른 자료가 섞인 DB에서도 이 테스트의 그림만 보도록 먼저 채워 둔다
            connection.execute("INSERT INTO image_descriptions (image_id, engine, scene) SELECT a.id, 'fake:a', '다른 자료' FROM image_assets a "
                               "WHERE NOT (a.sha256 = ANY(%s)) ON CONFLICT DO NOTHING", (self.used,))
            self.addCleanup(self.forget_fillers)
        first = image_describe.describe_missing(DSN, model)
        self.assertEqual((first["새로 만든 설명"], first["거른 그림"], first["실패"]), (1, [], []), "이미 공개된 그림만 보낸다")
        self.assertEqual(model.calls[0][0], "image_describe")
        again = image_describe.describe_missing(DSN, model)
        self.assertEqual((again["새로 만든 설명"], len(model.calls)), (0, 1), "이미 있는 설명은 다시 만들지 않는다")
        wide = image_describe.describe_missing(DSN, model, scope="all")
        self.assertEqual(wide["새로 만든 설명"], 1, "범위를 넓히면 원고 그림도 보내지만 비공개 그림은 보내지 않는다")
        with psycopg.connect(DSN) as connection:
            rows = dict(connection.execute("SELECT image_id::text, engine FROM image_descriptions WHERE image_id = ANY(%s)",
                                           ([public, manuscript, private],)).fetchall())
        self.assertEqual(rows, {public: "fake:a", manuscript: "fake:a"})
        with self.assertRaises(ValueError):
            image_describe.describe_missing(DSN, model, scope="everything")

    def test_bad_answers_are_not_stored_and_failures_are_reported(self):
        self.add("그림 1", KOGL, keywords=[])
        with psycopg.connect(DSN) as connection:
            connection.execute("INSERT INTO image_descriptions (image_id, engine, scene) SELECT a.id, 'fake:b', '다른 자료' FROM image_assets a "
                               "WHERE NOT (a.sha256 = ANY(%s)) ON CONFLICT DO NOTHING", (self.used,))
            self.addCleanup(self.forget_fillers)
        bad = image_describe.describe_missing(DSN, FakeVision(lambda task, text: {"kind": "photo", "scene": "짧다", "keywords": []}, name="fake:b"))
        self.assertEqual((bad["새로 만든 설명"], len(bad["거른 그림"])), (0, 1))
        self.assertTrue(any("너무 짧음" in why for why in bad["거른 그림"][0]["까닭"]))

        class Blocked:
            name = "fake:b"

            def ask(self, **_):
                raise VisionError("그림 외부 전송 미승인 — 승인 후 .env에 LLM_ALLOW_IMAGE_UPLOAD=1")

        blocked = image_describe.describe_missing(DSN, Blocked())
        self.assertEqual((blocked["새로 만든 설명"], len(blocked["실패"])), (0, 1))
        with mock.patch.dict(os.environ, {"NCS_DESCRIBE_ENGINE": ""}):
            self.assertIn("꺼져", image_describe.why_not())
            with self.assertRaises(ValueError):
                image_describe.load_model()
        with mock.patch.dict(os.environ, {"NCS_DESCRIBE_ENGINE": "api", "LLM_ALLOW_UPLOAD": "1", "LLM_ALLOW_IMAGE_UPLOAD": "", "LLM_LOCAL_ONLY": ""}):
            self.assertIn("그림 외부 전송 미승인", image_describe.why_not())
        self.assertIn("설명이 있는 그림", image_describe.status(DSN))

    def test_described_words_find_a_picture_nobody_tagged(self):
        """사람이 키워드를 달지 않은 그림도 설명의 낱말로 찾는다 — 사람이 단 키워드보다 낮은 점수로."""
        untagged = self.add("이름 없는 사진", KOGL, keywords=[])
        tagged = self.add("키워드를 단 사진", KOGL, keywords=[self.tag])
        with psycopg.connect(DSN) as connection:
            connection.execute("INSERT INTO image_descriptions (image_id, engine, kind, scene, keywords, visible_text) VALUES (%s, 'fake:c', 'photo', %s, %s, %s)",
                               (untagged, "접수대 사진", [self.tag, "카운터"], ["HOTEL"]))
        pool = self.mine(image_recommend.candidates(DSN))
        by_id = {row["id"]: row for row in pool}
        self.assertEqual(by_id[untagged]["described_terms"], [self.tag, "카운터", "HOTEL"])
        self.assertEqual(by_id[untagged]["described"], {"engine": "fake:c", "kind": "photo", "scene": "접수대 사진", "checked": False})
        self.assertEqual((by_id[tagged]["described_terms"], by_id[tagged]["described"]), ([], None))
        body = self.client.post("/api/recommend/images", json={"text": f"{self.tag}에서 예약을 확인한다.", "use_llm": False}).json()
        found = {item["id"]: item for item in body["items"]}
        self.assertEqual((found[tagged]["matched"], found[tagged]["described_matched"]), ([self.tag], []))
        self.assertEqual(found[untagged]["described_matched"], [self.tag])
        self.assertGreater(found[tagged]["score"], found[untagged]["score"])
        self.assertNotIn("described_terms", found[untagged], "긴 글은 화면에 싣지 않는다")
        self.assertGreaterEqual(body["described"], 1)

    def test_points_reach_the_ranking(self):
        """생성형 AI가 준 지점의 '다른 이름'으로 낱말이 다른 그림을 찾고, 결과에 지점이 실린다."""
        desk = self.add("프런트 사진", KOGL, keywords=[self.tag + "데스크"], kind="photo")
        asker = lambda system, user: {"model": "m", "data": {  # noqa: E731
            "summary": "접수대에서 예약을 확인한다.", "keywords": ["접수대"], "needs_image": True, "needs_reason": "장면이 있다",
            "points": [{"description": "호텔 접수대", "kind": "photo", "terms": ["접수대"], "aliases": [self.tag + "데스크"]}]}}
        body = image_recommend.recommend(DSN, text="고객이 접수대에서 예약을 확인한다.", asker=asker)
        self.assertEqual(body["context"]["points"], [{"description": "호텔 접수대", "kind": "photo", "terms": ["접수대"], "aliases": [self.tag + "데스크"]}])
        (item,) = [item for item in body["items"] if item["id"] == desk]
        self.assertEqual((item["matched_alias"], item["point"], item["kind_match"]), ([self.tag + "데스크"], 0, True))
        no_need = image_recommend.recommend(DSN, text="고객이 접수대에서 예약을 확인한다.", asker=lambda s, u: {"model": "m", "data": {
            "summary": "", "keywords": ["접수대"], "needs_image": False, "needs_reason": "정의만 있다", "points": []}})
        self.assertIn("그림이 꼭 필요해 보이지 않습니다", no_need["guidance"][0])
        self.assertEqual(ctx.MAX_POINTS, 3)


class ChoiceIntegrationTests(Base):
    def choose(self, expect=200, **body):
        response = self.client.post("/api/recommend/choices", json=body)
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def test_choices_are_kept_changed_and_cleared(self):
        desk, hall = self.add("프런트", KOGL, source_id="T-" + self.tag), self.add("연회장", KOGL)
        text = f"{self.tag} 접수대에서 예약을 확인한다."
        self.assertEqual(self.choose(text=text, image_id=desk, choice="used", rank=1, score=6.5, by="집필자", detail={"matched": ["접수대"]}), {"choice": "used"})
        self.assertEqual(self.choose(text=text + "  ", image_id=hall, choice="rejected", rank=2, by="집필자"), {"choice": "rejected"})
        self.assertEqual(image_choices.mine(DSN, by="집필자", text=text), {desk: "used", hall: "rejected"}, "띄어쓰기만 다른 문단은 같은 문단")
        self.assertEqual(self.choose(text=text, image_id=hall, choice="used", by="집필자"), {"choice": "used"})          # 마음을 바꿈
        with psycopg.connect(DSN) as connection:
            rows = connection.execute("SELECT choice, rank, detail FROM recommend_choices WHERE image_id = %s", (hall,)).fetchall()
        self.assertEqual(rows, [("used", None, {})], "같은 사람·같은 문단·같은 그림은 한 줄만 남는다")
        self.assertEqual(self.choose(text=text, image_id=hall, choice="none", by="집필자"), {"choice": None})
        self.assertEqual(image_choices.mine(DSN, by="집필자", text=text), {desk: "used"})
        listed = self.client.post("/api/recommend/choices/mine", json={"text": text}).json()      # 로그인을 쓰지 않는 서버의 이름 없는 사람
        self.assertEqual(listed, {"choices": {}})

    def test_only_recommendable_pictures_and_valid_input(self):
        waiting = self.add("확정 전", KOGL, confirm=False)
        private = self.add("비공개", {**KOGL, "release_class": "private"})
        ok = self.add("확정", KOGL)
        self.choose(404, text="문단", image_id=waiting, choice="used", by="집필자")
        self.choose(404, text="문단", image_id=private, choice="used", by="집필자")
        self.choose(404, text="문단", image_id=str(uuid4()), choice="used", by="집필자")
        self.choose(404, text="문단", image_id="uuid-아님", choice="used", by="집필자")
        self.choose(400, text="", image_id=ok, choice="used", by="집필자")
        self.choose(400, text="문단", image_id=ok, choice="used", by="집필자", detail={"글": "가" * 5000})
        self.assertEqual(self.client.post("/api/recommend/choices", json={"text": "문단", "image_id": ok, "choice": "maybe"}).status_code, 400)
        self.assertEqual(self.choose(text="문단 " + self.tag, image_id=ok, choice="used"), {"choice": "used"})       # 이름을 주지 않아도 남는다
        self.assertEqual(image_choices.mine(DSN, by="이름 없음", text="문단 " + self.tag), {ok: "used"})

    def test_export_is_a_gold_set_the_evaluator_reads(self):
        desk, hall, other = self.add("프런트", KOGL, source_id="T-" + self.tag), self.add("연회장", KOGL), self.add("복도", KOGL)
        text, unused = f"{self.tag} 접수대에서 예약을 확인한다.", f"{self.tag} 맞는 그림이 없던 문단"
        self.choose(text=text, image_id=desk, choice="used", by="가")
        self.choose(text=text, image_id=desk, choice="rejected", by="나")      # 한 사람이라도 썼으면 쓴 그림
        self.choose(text=text, image_id=hall, choice="rejected", by="가")
        self.choose(text=unused, image_id=other, choice="rejected", by="가")
        body = self.client.get("/api/recommend/choices/export").json()
        self.assertEqual(body["schema"], evaluate.SCHEMA)
        self.assertGreaterEqual(body["counts"]["used"], 1)
        (query,) = [query for query in body["queries"] if query["text"] == text]
        with psycopg.connect(DSN) as connection:
            hall_sha = connection.execute("SELECT sha256 FROM image_assets WHERE id = %s", (hall,)).fetchone()[0]
        self.assertEqual((query["relevant"], query["rejected"]), ({"T-" + self.tag: 2}, [hall_sha]), "이름표는 source_id, 없으면 sha256")
        self.assertFalse(any(query["text"] == unused for query in body["queries"]), "쓴 그림이 없는 문단은 정답이 없어 뺀다")
        loaded = evaluate.load_gold({"queries": [query]})[0]
        pool = self.mine(image_recommend.candidates(DSN))
        ranked = image_recommend.rank_pool(pool, ctx.analyze(text, use_llm=False), limit=5)
        self.assertEqual(evaluate.missing(loaded, pool), [])
        self.assertIn("hit@1", evaluate.score(loaded, ranked["items"], pool))


if __name__ == "__main__":
    unittest.main()
