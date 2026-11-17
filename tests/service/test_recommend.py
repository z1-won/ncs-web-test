"""이미지 추천(ncs_recommend, REQ-02-011) — 문맥 분석과 순위. DB·네트워크 없이 돈다(생성형 AI는 asker 대역)."""

import os
import unittest
from unittest import mock

from ncs_core import llm
from ncs_recommend import context as ctx
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


if __name__ == "__main__":
    unittest.main()
