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

    def test_protective_gear_is_not_a_face(self):
        for text in ("a worker wearing a welding face shield and leather gloves", "a dust face mask on the bench", "a full-face respirator hanging on the wall",
                     "face shields and gloves on a shelf", "보안면과 가죽 장갑을 착용한 작업자의 뒷모습"):
            self.assertTrue(prompt.check(text)["ok"], text)
        for text in ("a worker's face behind a face shield", "the face of a welder"):
            self.assertFalse(prompt.check(text)["ok"], text)

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
            self.assertEqual(ai_line(imagegen.tool_name(), "generated", date(2026, 11, 25)), "Stable Diffusion XL을 활용하여 생성함. 2026. 11. 25.")
        with mock.patch.dict(os.environ, {"NCS_IMAGEGEN_MODEL": "black-forest-labs/FLUX.1-schnell"}):
            self.assertEqual(ai_line(imagegen.tool_name(), "generated", date(2026, 11, 25)), "FLUX를 활용하여 생성함. 2026. 11. 25.")
        with mock.patch.dict(os.environ, {"NCS_IMAGEGEN_MODEL": "stabilityai/sdxl-turbo"}):
            ai_line(imagegen.tool_name(), "generated", date(2026, 11, 25))

    def fake_engine(self, seen, cancel_at=None):
        """모델 대신 쓰는 파이프라인 — 단계마다 diffusers처럼 callback_on_step_end를 부르고 _interrupt를 지킨다."""
        from PIL import Image

        class Generator:
            def __init__(self, _device):
                pass

            def manual_seed(self, seed):
                return seed

        class Torch:
            pass

        Torch.Generator = Generator

        class Pipe:
            device = "cpu"
            _interrupt = False

            def __call__(self, *, num_inference_steps, callback_on_step_end=None, **kwargs):
                self._interrupt = False
                for step in range(num_inference_steps):
                    if self._interrupt:
                        break
                    if callback_on_step_end is not None:
                        callback_on_step_end(self, step, 0, {})
                        seen.append(imagegen.progress("job-1"))
                        if cancel_at is not None and len(seen) == cancel_at:
                            self.cancelled = imagegen.cancel("job-1")

                class Out:
                    images = [Image.new("RGB", (kwargs["width"], kwargs["height"]), "white")]
                return Out()

        return mock.patch.multiple(imagegen, _pipeline=lambda: (Pipe(), Torch), _why_off=lambda: "")

    def test_progress_follows_images_and_steps(self):
        """만드는 동안 몇 번째 장의 몇 단계인지와 남은 시간(어림)을 알 수 있다."""
        seen = []
        imagegen._jobs.clear()
        self.assertIsNone(imagegen.progress("job-1"))
        with mock.patch.dict(os.environ, {"NCS_IMAGEGEN_STEPS": "5"}), self.fake_engine(seen):
            made = imagegen.generate("a bench", count=2, seed=3, job="job-1")
        self.assertEqual([(one.seed, one.png[:4]) for one in made], [(3, b"\x89PNG"), (4, b"\x89PNG")])
        self.assertEqual([(p["state"], p["image"], p["step"], p["percent"]) for p in seen],
                         [("running", 1, s, s * 10) for s in range(1, 6)] + [("running", 2, s, 50 + s * 10) for s in range(1, 6)])
        self.assertEqual((seen[0]["count"], seen[0]["steps"], seen[0]["상태"]), (2, 5, "그림을 만드는 중"))
        self.assertTrue(all(p["remaining"] is not None for p in seen[:-1]))
        self.assertIsNone(seen[-1]["remaining"], "마지막 단계가 끝나면 남은 시간은 없다")
        done = imagegen.progress("job-1")
        self.assertEqual((done["state"], done["percent"], done["remaining"]), ("done", 100, None))
        self.assertFalse(imagegen.cancel("job-1"), "끝난 작업은 취소할 것이 없다")
        self.assertFalse(imagegen.cancel("unknown"))

    def test_cancel_stops_at_the_next_step_and_keeps_nothing(self):
        seen = []
        imagegen._jobs.clear()
        with mock.patch.dict(os.environ, {"NCS_IMAGEGEN_STEPS": "6"}), self.fake_engine(seen, cancel_at=2):
            with self.assertRaises(imagegen.Cancelled):
                imagegen.generate("a bench", count=3, seed=1, job="job-1")
        self.assertLessEqual(len(seen), 3, "취소한 뒤 한 단계 안에 멈춘다")
        stopped = imagegen.progress("job-1")
        self.assertEqual((stopped["state"], stopped["image"], stopped["상태"]), ("cancelled", 1, "취소됨"))

    def test_progress_with_a_runner_and_errors(self):
        imagegen._jobs.clear()
        states = []
        made = imagegen.generate("a bench", count=2, job="job-2", runner=lambda *args: states.append(imagegen.progress("job-2")) or b"png")
        self.assertEqual([(p["state"], p["image"], p["count"], p["steps"], p["percent"]) for p in states], [("running", 1, 2, 0, 0), ("running", 2, 2, 0, 0)])
        self.assertEqual((len(made), imagegen.progress("job-2")["state"]), (2, "done"))

        def broken(*args):
            raise OSError("디스크가 가득 참")

        with self.assertRaises(OSError):
            imagegen.generate("a bench", count=1, job="job-3", runner=broken)
        failed = imagegen.progress("job-3")
        self.assertEqual((failed["state"], failed["error"]), ("error", "디스크가 가득 참"))
        for n in range(imagegen.MAX_JOBS + 5):
            imagegen.generate("a bench", count=1, job=f"many-{n}", runner=lambda *args: b"png")
        self.assertEqual(len(imagegen._jobs), imagegen.MAX_JOBS, "작업 기록은 정해진 수만 남긴다")
        self.assertIsNone(imagegen.progress("job-2"))

    def test_settings_follow_the_model_family(self):
        names = ("NCS_IMAGEGEN_MODEL", "NCS_IMAGEGEN_STEPS", "NCS_IMAGEGEN_GUIDANCE", "NCS_IMAGEGEN_VARIANT")
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in names:
                os.environ.pop(name, None)
            self.assertEqual(imagegen.model_name(), "stabilityai/stable-diffusion-xl-base-1.0")
            self.assertEqual(imagegen.settings(), {"family": "sdxl", "steps": 30, "guidance": 6.0, "variant": "fp16", "negative": True})
            self.assertEqual(imagegen.status()["설정"]["family"], "sdxl")
            for model in ("black-forest-labs/FLUX.1-schnell", "stabilityai/sdxl-turbo", "black-forest-labs/FLUX.2-klein-4B", "some/other-model"):
                self.assertEqual(imagegen.settings(model), {"family": "distilled", "steps": 4, "guidance": 0.0, "variant": "", "negative": False}, model)
            with mock.patch.dict(os.environ, {"NCS_IMAGEGEN_STEPS": "20", "NCS_IMAGEGEN_GUIDANCE": "7.5", "NCS_IMAGEGEN_VARIANT": "none"}):
                self.assertEqual(imagegen.settings(), {"family": "sdxl", "steps": 20, "guidance": 7.5, "variant": "", "negative": True})

    def test_restriction_goes_as_a_negative_prompt_for_stable_diffusion(self):
        """Stable Diffusion 계열은 글 속의 'No text'를 따르지 못하고 앞의 77토큰만 읽는다 — 화풍을 앞에, 제한은 부정 프롬프트로."""
        sent = prompt.compose("A welder seen from behind at a steel workbench", "photo")
        plain = prompt.for_model(sent, negative=False)
        self.assertEqual((plain["prompt"], plain["negative"], plain["note"]), (sent, "", ""))
        split = prompt.for_model(sent, negative=True)
        self.assertEqual(split["prompt"], prompt.STYLE["photo"] + " A welder seen from behind at a steel workbench.")
        self.assertNotIn("No text", split["prompt"])
        self.assertNotIn("No visible human faces", split["prompt"])
        for word in ("human face", "text", "logos", "watermark"):
            self.assertIn(word, split["negative"])
        self.assertEqual(split["note"], "")
        self.assertEqual(prompt.parts(prompt.compose("gloves on a bench", "illustration")), ("gloves on a bench.", prompt.STYLE["illustration"]))
        self.assertEqual(prompt.parts("free text"), ("free text", ""))
        long_scene = " ".join(["a worker tightens a bolt on the frame"] * 9)
        self.assertIn("77토큰", prompt.for_model(prompt.compose(long_scene, "photo"), negative=True)["note"])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NCS_IMAGEGEN_MODEL", None)
            self.assertEqual(imagegen.sent_to_model(sent), split)
        with mock.patch.dict(os.environ, {"NCS_IMAGEGEN_MODEL": "black-forest-labs/FLUX.1-schnell"}):
            self.assertEqual(imagegen.sent_to_model(sent)["prompt"], sent)


if __name__ == "__main__":
    unittest.main()
