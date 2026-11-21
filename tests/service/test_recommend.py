"""이미지 추천(ncs_recommend, REQ-02-011) — 문맥 분석과 순위. DB·네트워크 없이 돈다(생성형 AI는 asker 대역)."""

import os
import unittest
from unittest import mock

from ncs_core import llm
from ncs_recommend import context as ctx
from ncs_recommend import embed
from ncs_recommend import rank

TEXT = ("호텔의 객실 유형(위치, 면적, 객실 타입 등)에 따라 객실 및 부대시설 정보를 구분한다. "
        "프런트 데스크에서는 객실 배정표를 확인하고 고객에게 부대시설 이용 방법을 안내한다.")


def answer(summary="객실 유형별 정보를 구분한다.", keywords=("객실 유형", "부대시설")):
    return lambda system, user: {"data": {"summary": summary, "keywords": list(keywords)}, "model": "m"}


def image(image_id="a", **fields):
    base = {"id": image_id, "title": None, "keywords": [], "captions": [], "contexts": [], "links": [], "ownership": "government",
            "reuse_scope": "module_only", "license_scheme": None, "kogl_type": None, "kogl_ai": False, "width_px": 1200,
            "attribution": False, "non_commercial": False, "no_derivatives": False, "share_alike": False, "credit_line": None}
    return {**base, **fields}


def context(*keywords):
    return ctx.Context("", list(keywords), "rule")


class ContextTests(unittest.TestCase):
    def test_rule_keywords_strip_particles_and_stopwords(self):
        found = ctx.rule_keywords(TEXT)
        self.assertEqual(found[:2], ["객실", "부대시설"], "자주 나온 낱말이 앞에 온다")
        for word in ("따라", "및", "등", "객실을", "데스크에서는", "한다"):
            self.assertNotIn(word, found)
        self.assertIn("데스크", ctx.rule_keywords(TEXT, limit=20))
        self.assertEqual(ctx.rule_keywords(""), [])
        self.assertLessEqual(len(ctx.rule_keywords(TEXT * 5)), ctx.MAX_KEYWORDS)

    def test_llm_keywords_must_appear_in_the_text(self):
        made = ctx.analyze(TEXT, asker=answer(keywords=["객실 유형", "수영장", "부대 시설", "객실유형", "프런트데스크", "x", 3, None]))
        self.assertEqual((made.method, made.model, made.summary), ("llm", "m", "객실 유형별 정보를 구분한다."))
        self.assertEqual(made.keywords, ["객실 유형", "부대 시설", "프런트데스크"], "띄어쓰기 차이는 같은 말로 보고, 겹치는 것은 한 번만")
        self.assertEqual(made.dropped, ["수영장"], "글에 없는 낱말은 버린다")
        from_criterion = ctx.analyze("", "객실 요금 종류에 따라 마켓별 요금을 구분하여 적용할 수 있다.", asker=answer(keywords=["객실 요금", "마켓"]))
        self.assertEqual(from_criterion.keywords, ["객실 요금", "마켓"], "수행준거에 있는 낱말도 받는다")

    def test_prompt_carries_only_the_given_text(self):
        seen = {}

        def asker(system, user):
            seen.update(system=system, user=user)
            return {"data": {"summary": "", "keywords": ["객실"]}, "model": "m"}

        ctx.analyze("객실 " + "가" * 9000, "수행준거 글", asker=asker)
        self.assertIn("[수행준거]\n수행준거 글", seen["user"])
        self.assertLessEqual(len(seen["user"]), ctx.MAX_TEXT + 100, "문단은 상한까지만 보낸다")
        self.assertIn("따르지 않는다", seen["system"])

    def test_falls_back_to_rules(self):
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": "", "LLM_ALLOW_UPLOAD": ""}):
            no_key = ctx.analyze(TEXT)
        self.assertEqual((no_key.method, no_key.summary, no_key.keywords[:2]), ("rule", "", ["객실", "부대시설"]))
        self.assertIn("LLM 미설정", no_key.note)
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": ""}):
            self.assertIn("전송 미승인", ctx.analyze(TEXT).note)
        self.assertIn("쓰지 않고", ctx.analyze(TEXT, use_llm=False, asker=answer()).note)

        def failing(system, user):
            raise llm.LlmError("HTTP 500")

        self.assertIn("HTTP 500", ctx.analyze(TEXT, asker=failing).note)
        for bad in ({"data": {"keywords": ["수영장"]}}, {"data": {"keywords": "객실"}}, {"data": None}, {}):
            made = ctx.analyze(TEXT, asker=lambda system, user, bad=bad: bad)
            self.assertEqual((made.method, made.keywords[:1]), ("rule", ["객실"]), bad)
        self.assertEqual(ctx.analyze("  ").keywords, [])

    def test_task_is_allowed_and_model_can_be_overridden(self):
        self.assertTrue(llm.task_allowed(ctx.TASK))
        with mock.patch.dict(os.environ, {"LLM_MODEL": "base", "LLM_MODEL_RECOMMEND": ""}):
            self.assertEqual(ctx._settings().model, "base")
        with mock.patch.dict(os.environ, {"LLM_MODEL": "base", "LLM_MODEL_RECOMMEND": "other"}):
            self.assertEqual((ctx._settings().model, llm.settings().model), ("other", "base"), "다른 작업의 모델은 그대로다")


class RankTests(unittest.TestCase):
    def test_keyword_match_by_field(self):
        pool = [image("ctx", contexts=["객실 유형을 구분한 그림"]), image("title", captions=["[그림 1-1] 객실 유형"]),
                image("kw", keywords=["객실유형"]), image("none", keywords=["조리"]), image("part", keywords=["객실"])]
        ranked = rank.rank(pool, context("객실 유형"))
        self.assertEqual([(item["id"], item["score"]) for item in ranked], [("kw", 3.0), ("part", 3.0), ("title", 2.0), ("ctx", 1.0)],
                         "키워드 > 제목·캡션 > 사용 문장. 맞지 않는 그림은 빠진다")
        self.assertEqual(ranked[0]["matched"], ["객실 유형"])
        first, last = rank.rank([image("first", keywords=["객실"]), image("last", keywords=["요금"])], context("객실", "x1", "요금"))
        self.assertEqual((first["id"], first["score"], last["score"]), ("first", 3.0, 1.8), "앞 순위 핵심어를 더 쳐 준다")

    def test_link_levels(self):
        def linked(image_id, unit, element="", criterion=""):
            return image(image_id, links=[{"unit_code": unit, "element_code": element, "criterion_no": criterion}])

        pool = [linked("unit", "1203020201_24v3"), linked("element", "1203020201_24v3", "1203020201_24v3.1"),
                linked("criterion", "1203020201_24v3", "1203020201_24v3.1", "1.2"), linked("other", "1203020202_24v3", "1203020202_24v3.1", "1.2"),
                linked("element2", "1203020201_24v3", "1203020201_24v3.2", "2.1")]
        ranked = rank.rank(pool, context(), unit_code="LM1203020201", criterion_no="1.2")
        self.assertEqual([(item["id"], item["link_level"]) for item in ranked],
                         [("criterion", "criterion"), ("element", "element"), ("element2", "unit"), ("unit", "unit")])
        self.assertEqual(rank.rank(pool, context(), unit_code="", criterion_no="1.2"), [], "능력단위 없이 번호만으로는 잇지 않는다")
        self.assertEqual([rank.unit_base(code) for code in ("LM1203020201_24v3", "1203020201", "12", None)], ["1203020201", "1203020201", "", ""])

    def test_government_asset_goes_first_among_similar(self):
        kogl = image("kogl", keywords=["객실"], ownership="kogl", reuse_scope="all")
        own = image("own", keywords=["객실"], ownership="government", reuse_scope="all")
        much_better = image("better", keywords=["객실", "부대시설", "배정표"], ownership="kogl", reuse_scope="all")
        ranked = rank.rank([kogl, own, much_better], context("객실", "부대시설", "배정표"))
        self.assertEqual([item["id"] for item in ranked], ["better", "own", "kogl"],
                         "비슷하면 정부 귀속이 앞, 관련이 훨씬 높은 그림은 밀어내지 않는다")
        self.assertEqual([item["priority"] for item in ranked], [False, True, False])
        self.assertEqual(len(rank.rank([own] * 5, context("객실"), limit=2)), 2)

    def test_rights_notes_for_the_writer(self):
        licensed = rank.describe(image(ownership="licensed", reuse_scope="all"))
        module_only = rank.describe(image(ownership="government", reuse_scope="module_only"))
        self.assertEqual((licensed["scope_check_needed"], module_only["scope_check_needed"], module_only["priority"]), (True, True, False))
        fourth = rank.describe(image(license_scheme="kogl", kogl_type=4, kogl_ai=True, attribution=True, non_commercial=True,
                                     no_derivatives=True, credit_line="공공누리 홈페이지(https://www.kogl.or.kr/)에서 2026. 11. 17. 검색. 공공누리 제4유형."))
        self.assertEqual(fourth["conditions"], ["출처표시", "상업적 이용금지", "변경금지"])
        self.assertIn("제4유형 조건이 그대로 적용", fourth["notes"][0])
        self.assertTrue(fourth["credit"].startswith("출처: 공공누리 홈페이지("))
        zero = rank.describe(image(license_scheme="kogl", kogl_type=0, credit_line="x"))
        self.assertEqual((zero["conditions"], zero["credit"]), ([], "출처: x"))
        self.assertIn("계약서 제4조", zero["notes"][0])
        blank = rank.describe(image())
        self.assertEqual((blank["credit"], blank["notes"]), (None, []))
        self.assertIn("출처 문구가 DB에 없습니다", blank["credit_note"])

    def test_quality_and_ai_guidance(self):
        small, upscaled, unknown = (rank.describe(image(width_px=400)), rank.describe(image(width_px=400, upscaled_width_px=1600)),
                                    rank.describe(image(width_px=None)))
        self.assertEqual((small["max_width_mm"], small["low_quality"]), (34, True))
        self.assertEqual((upscaled["max_width_mm"], upscaled["low_quality"]), (135, False), "업스케일본이 있으면 그 크기로 본다")
        self.assertEqual((unknown["max_width_mm"], unknown["low_quality"]), (None, False))
        self.assertIn("없습니다", rank.guidance([])[0])
        self.assertTrue(any("REQ-02-006" in line for line in rank.guidance([])))
        self.assertIn("화질이 낮습니다", rank.guidance([small])[0])
        self.assertEqual(rank.guidance([small, upscaled]), [])


class CommonKeywordTests(unittest.TestCase):
    """후보 대부분에 맞는 핵심어는 그림을 가려 주지 못한다."""

    def hotels(self, count=8):
        return [image(f"h{n}", title=f"호텔 내부 {n}") for n in range(count)]

    def test_keyword_on_every_candidate_does_not_qualify_alone(self):
        pool = self.hotels()
        pool[3]["keywords"] = ["프런트"]
        ranked = rank.rank(pool, context("호텔", "프런트"))
        self.assertEqual([(item["id"], item["score"], item["matched"], item["common"]) for item in ranked],
                         [("h3", 2.3, ["호텔", "프런트"], ["호텔"])], "가려 주는 핵심어가 맞은 그림만 남고, 흔한 핵심어는 1/4만 친다")

    def test_falls_back_when_nothing_else_matches(self):
        ranked = rank.rank(self.hotels(), context("호텔"))
        self.assertEqual([(item["id"], item["score"]) for item in ranked], [(f"h{n}", 0.5) for n in range(8)],
                         "그래서 추천이 하나도 없으면 흔한 핵심어가 맞은 그림을 그대로 보여 준다")

    def test_small_pools_are_left_alone(self):
        ranked = rank.rank(self.hotels(7), context("호텔"))
        self.assertEqual([(item["score"], item["common"]) for item in ranked], [(2.0, [])] * 7, "후보가 8장 미만이면 따지지 않는다")


def toward(first: float) -> list[float]:
    """첫 축 성분이 first인 길이 1 벡터(나머지는 셋째 축)."""
    return [first, 0.0, (1.0 - first * first) ** 0.5]


class VisualTests(unittest.TestCase):
    """그림 임베딩으로 견주기 — 벡터는 손으로 만든 것(모델 없이).

    바탕 글 8개는 첫 축 성분이 0.10~0.24다. 그래서 그림 'same'([1,0,0])의 바탕(관련 없는 글과 닮은 정도의 중앙값)은 0.17이고,
    'hub'([0.6,0,0.8])은 무슨 글에나 0.86~0.92로 닮게 나오는 그림, 'far'([0,1,0])는 어느 글과도 0이다.
    """

    QUERY = [1.0, 0.0, 0.0]
    REFS = [toward(first / 100) for first in range(10, 25, 2)]

    def pool(self):
        return [image("same", vector=[1.0, 0.0, 0.0]), image("hub", vector=[0.6, 0.0, 0.8]), image("far", vector=[0.0, 1.0, 0.0]),
                image("no-vector")]

    def z(self, pool, above):
        """'same' 그림의 바탕보다 above만큼 더 닮은 글을 넣었을 때 첫 후보의 (σ, 가산 비율)."""
        return rank.visual_scores(pool, toward(0.17 + above), self.REFS)[0][1:]

    def test_cosine(self):
        self.assertAlmostEqual(embed.cosine([0.6, 0.8], [0.6, 0.8]), 1.0)
        self.assertAlmostEqual(embed.cosine([1.0, 0.0], [0.0, 1.0]), 0.0)
        for a, b in ((None, [1.0]), ([1.0], None), ([], [1.0]), ([1.0, 0.0], [1.0])):
            self.assertIsNone(embed.cosine(a, b))

    def test_similarity_is_measured_against_unrelated_texts(self):
        scores = rank.visual_scores(self.pool(), self.QUERY, self.REFS)
        self.assertEqual(sorted(scores), [0, 1, 2], "벡터가 없는 후보는 빠진다")
        self.assertEqual((scores[0][0], scores[0][2]), (1.0, 1.0))
        self.assertEqual((round(scores[1][0], 2), scores[1][2]), (0.6, 0.0), "유사도가 높아도 무슨 글에나 닮는 그림이면 가산하지 않는다")
        self.assertLess(scores[1][1], 0)
        self.assertEqual(scores[2][1:], (0.0, 0.0))

    def test_sigma_is_the_distance_from_the_baseline_in_one_unit_for_all(self):
        pool = self.pool()
        unit = 0.03 / self.z(pool, 0.03)[0]
        self.assertAlmostEqual(self.z(pool, 0.06)[0], 0.06 / unit, places=6, msg="바탕에서 벗어난 만큼에 비례한다")
        halfway = (rank.VISUAL_Z_MIN + rank.VISUAL_Z_FULL) / 2
        self.assertAlmostEqual(self.z(pool, halfway * unit)[1], 0.5, places=6)
        self.assertEqual((self.z(pool, rank.VISUAL_Z_MIN * unit - 0.001)[1], self.z(pool, rank.VISUAL_Z_FULL * unit + 0.001)[1]), (0.0, 1.0))
        # 그림마다 제 퍼짐으로 나누지 않는다: 바탕이 고른 그림(far, 퍼짐 0)이라고 σ가 부풀지 않는다
        tight = [image("far", vector=[0.0, 1.0, 0.0]), *pool[:2]]
        query = [0.05, 0.9987492177719089, 0.0]          # far와 0.9987, same과 0.05
        scores = rank.visual_scores(tight, query, self.REFS)
        self.assertAlmostEqual(scores[0][1], 0.9987492177719089 / unit, places=6, msg="단위는 후보들의 바탕 퍼짐의 중앙값 하나다")

    def test_text_that_fits_every_candidate_alike_scores_nobody(self):
        alike = [image(str(n), vector=[1.0, 0.0, 0.0]) for n in range(rank.VISUAL_POOL_MIN)]
        self.assertEqual({position for _, _, position in rank.visual_scores(alike, toward(0.17 + 0.2), self.REFS).values()}, {0.0},
                         "후보 모두에 고르게 닮는 글은 그림을 가려 주지 못한다")
        one = [image("same", vector=[1.0, 0.0, 0.0]), *[image(f"far{n}", vector=[0.0, 1.0, 0.0]) for n in range(rank.VISUAL_POOL_MIN - 1)]]
        self.assertEqual([position for _, _, position in rank.visual_scores(one, toward(0.17 + 0.2), self.REFS).values()],
                         [1.0, *[0.0] * (rank.VISUAL_POOL_MIN - 1)], "하나만 닮으면 그 그림이 받는다")
        few = alike[:rank.VISUAL_POOL_MIN - 1]
        self.assertEqual({position for _, _, position in rank.visual_scores(few, toward(0.17 + 0.2), self.REFS).values()}, {1.0},
                         "후보가 적으면 후보끼리 견주지 않는다")

    def test_nobody_scores_when_nothing_matches(self):
        unrelated = toward(0.17)                            # 바탕 글과 같은 쪽을 보는 글
        scores = rank.visual_scores(self.pool(), unrelated, self.REFS)
        self.assertEqual({position for _, _, position in scores.values()}, {0.0}, "가장 닮은 그림이라고 점수를 받지는 않는다")
        self.assertEqual(rank.rank(self.pool(), context("용접"), query_vector=unrelated, reference_vectors=self.REFS), [])

    def test_needs_reference_texts(self):
        for query, references in ((None, self.REFS), (self.QUERY, None), (self.QUERY, []), (self.QUERY, self.REFS[:rank.VISUAL_MIN_REFS - 1])):
            self.assertEqual(rank.visual_scores(self.pool(), query, references), {})
        self.assertEqual(rank.rank(self.pool(), context("객실"), query_vector=self.QUERY), [], "바탕이 없으면 그림 유사도를 쓰지 않는다")
        self.assertEqual(rank.rank(self.pool(), context("객실")), [], "임베딩이 없으면 예전처럼 핵심어·연결로만")

    def test_similar_pictures_are_recommended_without_any_keyword(self):
        ranked = rank.rank(self.pool(), context("객실"), query_vector=self.QUERY, reference_vectors=self.REFS)
        self.assertEqual([(item["id"], item["score"], item["similarity"], item["visual"]) for item in ranked], [("same", 6.0, 1.0, 1.0)],
                         "핵심어가 하나도 안 맞아도 그림이 문맥과 뚜렷이 맞으면 나온다")
        self.assertGreater(ranked[0]["visual_z"], rank.VISUAL_Z_FULL)
        self.assertTrue(all("vector" not in item for item in ranked), "벡터는 결과에 싣지 않는다")

    def test_visual_and_keyword_scores_add_up(self):
        pool = self.pool()
        pool[2]["keywords"] = ["객실"]            # 그림은 멀지만 핵심어가 맞는다
        pool[3]["keywords"] = ["객실"]            # 벡터 없음 + 핵심어
        ranked = rank.rank(pool, context("객실"), query_vector=self.QUERY, reference_vectors=self.REFS)
        self.assertEqual([(item["id"], item["score"]) for item in ranked], [("same", 6.0), ("far", 3.0), ("no-vector", 3.0)])
        self.assertEqual([item["visual"] for item in ranked], [1.0, 0.0, None], "벡터가 없는 그림은 유사도를 비워 둔다")

    def test_reference_vectors_are_computed_once_per_model(self):
        class Fake:
            name = "fake-for-references"
            calls = 0

            def text(self, text):
                Fake.calls += 1
                return [1.0, 0.0]

        fake = Fake()
        self.addCleanup(embed._references.pop, fake.name, None)
        first = embed.reference_vectors(fake)
        self.assertEqual((len(first), Fake.calls), (len(embed.REFERENCE_TEXTS), len(embed.REFERENCE_TEXTS)))
        self.assertIs(embed.reference_vectors(fake), first)
        self.assertEqual(Fake.calls, len(embed.REFERENCE_TEXTS))

        class Broken:
            name = "broken-for-references"

            def text(self, text):
                raise RuntimeError("모델 오류")

        self.assertEqual(embed.reference_vectors(Broken()), [], "바탕을 못 만들면 그림 유사도만 꺼진다")

    def test_embedding_is_off_unless_a_model_is_named(self):
        with mock.patch.dict(os.environ, {"NCS_EMBED_MODEL": ""}):
            self.assertIsNone(embed.get())
            self.assertIn("NCS_EMBED_MODEL이 비어", embed.why_not())
        with mock.patch.dict(os.environ, {"NCS_EMBED_MODEL": "없는/모델"}), mock.patch.object(embed, "Embedder", side_effect=OSError("모델 없음")), \
                mock.patch.object(embed, "_cached", None):
            self.assertIsNone(embed.get())
            self.assertIn("없는/모델", embed.why_not())
            self.assertIn("모델 없음", embed.why_not())


if __name__ == "__main__":
    unittest.main()
