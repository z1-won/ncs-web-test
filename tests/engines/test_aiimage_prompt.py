"""사진·삽화 생성(REQ-02-006 ① AI 생성) — 프롬프트 검사(얼굴, 상표, 화풍 따라 하기), 모델에 보낼 글, 장면 후보 거르기, 엔진 자리.

생성형 AI는 가짜 응답(asker)으로, 이미지 모델은 가짜 실행 함수(runner)로 넣는다. 실제 모델은 돌리지 않는다.
"""

import os
import unittest
from unittest import mock

from ncs_aiimage import imagegen, prompt
from ncs_core import llm

TEXT = "용접 작업 전에는 보호구를 착용한다. 용접면과 가죽 장갑을 끼고, 주변의 인화 물질을 치운다."


def fake(scenes, reason=""):
    return lambda system, user: {"data": {"scenes": scenes, "reason": reason}, "model": "fake"}


class CheckTests(unittest.TestCase):
    def test_back_view_and_hands_pass(self):
        for text in ("작업자의 뒷모습과 장갑 낀 손", "A welder seen from behind, gloved hands holding a torch", "멀리서 본 작업장"):
            self.assertTrue(prompt.check(text)["ok"], text)

    def test_face_is_refused(self):
        for text in ("작업자의 얼굴이 보이게", "환하게 웃는 직원", "a portrait of a welder", "close-up of a worker", "worker smiling, looking at the camera"):
            found = prompt.check(text)
            self.assertFalse(found["ok"], text)
            self.assertEqual(found["problems"][0]["kind"], "face")

    def test_surface_is_not_a_face(self):
        self.assertTrue(prompt.check("a flat metal surface on a workbench")["ok"])

    def test_imitation_and_brand_are_refused(self):
        self.assertEqual(prompt.check("지브리 화풍으로 그린 주방")["problems"][0]["kind"], "imitate")
        self.assertEqual(prompt.check("a kitchen in the style of Van Gogh")["problems"][0]["kind"], "imitate")
        self.assertEqual([p["kind"] for p in prompt.check("카카오톡으로 예약을 받는 직원의 손")["problems"]], ["brand"])

    def test_letters_are_a_note_not_a_refusal(self):
        found = prompt.check("'안전 제일'이라고 적힌 간판")
        self.assertTrue(found["ok"])
        self.assertEqual(len(found["notes"]), 1)

    def test_same_problem_once(self):
        self.assertEqual(len(prompt.check("얼굴", "얼굴")["problems"]), 1)


class ComposeTests(unittest.TestCase):
    def test_restriction_is_always_appended(self):
        sent = prompt.compose("A welder seen from behind.", "photo")
        self.assertTrue(sent.startswith("A welder seen from behind. Realistic photograph"))
        self.assertIn("No visible human faces", sent)
        self.assertIn("No text", sent)
        self.assertIn("flat vector-style illustration", prompt.compose("gloves on a bench", "illustration"))

    def test_bad_input(self):
        for scene, kind in (("", "photo"), ("x", "diagram")):
            with self.assertRaises(ValueError):
                prompt.compose(scene, kind)


class DraftTests(unittest.TestCase):
    def test_scenes_are_checked(self):
        result = prompt.draft(TEXT, kind="photo", asker=fake([
            {"ko": "용접면을 쓴 작업자의 뒷모습과 가죽 장갑", "en": "A welder seen from behind wearing a welding helmet and leather gloves"},
            {"ko": "작업자의 얼굴", "en": "portrait of a welder"}]))
        self.assertEqual((result["method"], result["usable"], result["usage"]), ("llm", 1, 1))
        self.assertEqual([scene["ok"] for scene in result["scenes"]], [True, False])

    def test_topic_only_is_usage_4(self):
        result = prompt.draft("", kind="illustration", focus="소화기의 구조", asker=fake([{"ko": "소화기 한 대", "en": "a fire extinguisher"}]))
        self.assertEqual((result["usage"], result["usable"]), (4, 1))

    def test_edited_scene_keeps_the_writers_korean(self):
        result = prompt.draft(TEXT, kind="photo", scene="장갑 낀 손이 용접봉을 쥔 모습", asker=fake([
            {"ko": "다른 말", "en": "gloved hands holding a welding rod"}, {"ko": "둘째", "en": "second"}]))
        self.assertEqual([(scene["ko"], scene["en"]) for scene in result["scenes"]], [("장갑 낀 손이 용접봉을 쥔 모습", "gloved hands holding a welding rod")])

    def test_nothing_to_show(self):
        result = prompt.draft(TEXT, kind="photo", asker=fake([], "정의만 있는 글"))
        self.assertEqual((result["scenes"], result["reason"]), ([], "정의만 있는 글"))

    def test_without_ai_makes_nothing_up(self):
        result = prompt.draft(TEXT, kind="photo")
        self.assertEqual((result["method"], result["scenes"]), ("none", []))
        self.assertIn("직접 적을 수 있습니다", result["note"])

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            prompt.draft("", kind="photo")
        with self.assertRaises(ValueError):
            prompt.draft(TEXT, kind="bar")

    def test_task_is_on_the_allow_list(self):
        self.assertTrue(llm.task_allowed("image_generate_prompt"))


class EngineTests(unittest.TestCase):
    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(imagegen.ENGINE_ENV, None)
            self.assertFalse(imagegen.status()["사용 가능"])
            with self.assertRaises(imagegen.EngineOff):
                imagegen.generate("a bench")

    def test_unknown_engine(self):
        with mock.patch.dict(os.environ, {imagegen.ENGINE_ENV: "cloud"}):
            self.assertIn("알 수 없는 엔진", imagegen.status()["이유"])

    def test_gated_model_error_says_what_to_do(self):
        error = OSError("black-forest-labs/FLUX.1-schnell is not a local folder and is not a valid model identifier listed on 'https://huggingface.co/models'")
        told = imagegen._explain("black-forest-labs/FLUX.1-schnell", error)
        self.assertIn("hf auth login", told)
        self.assertIn("https://huggingface.co/black-forest-labs/FLUX.1-schnell", told)
        self.assertIn("ValueError: x", imagegen._explain("m", ValueError("x")))

    def test_runner_gets_consecutive_seeds_and_the_shape(self):
        calls = []
        made = imagegen.generate("a bench", count=3, seed=10, shape="portrait", runner=lambda *args: calls.append(args) or b"png")
        self.assertEqual(calls, [("a bench", 768, 1024, 10), ("a bench", 768, 1024, 11), ("a bench", 768, 1024, 12)])
        self.assertEqual([(one.seed, one.width, one.height) for one in made], [(10, 768, 1024), (11, 768, 1024), (12, 768, 1024)])

    def test_bad_input(self):
        for kwargs in ({"count": 0}, {"count": 5}, {"shape": "wide"}):
            with self.assertRaises(ValueError):
                imagegen.generate("a bench", runner=lambda *args: b"", **kwargs)
        with self.assertRaises(ValueError):
            imagegen.generate("  ", runner=lambda *args: b"")

    def test_tool_name_can_be_written_in_an_ai_line(self):
        from datetime import date

        from ncs_core.figures import ai_line

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NCS_IMAGEGEN_TOOL", None)
            os.environ.pop("NCS_IMAGEGEN_MODEL", None)
            self.assertEqual(ai_line(imagegen.tool_name(), "generated", date(2026, 11, 25)), "FLUX를 활용하여 생성함. 2026. 11. 25.")
        with mock.patch.dict(os.environ, {"NCS_IMAGEGEN_MODEL": "stabilityai/sdxl-turbo"}):
            ai_line(imagegen.tool_name(), "generated", date(2026, 11, 25))


if __name__ == "__main__":
    unittest.main()
