"""LLM 호출 계층(ncs_core.llm)과 수행 ②(상표·상품·제조사명 후보) 규칙 — 네트워크 없이 가짜 응답으로."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ncs_core import llm
from ncs_perform.rules.brands import CHECK, check_brands


def block(materials, tools, unit="1-1", no=1):
    return {"lesson": 1, "unit": unit, "perform_no": no, "재료": [{"idx": i, "text": t} for i, t in enumerate(materials)],
            "기기": [{"idx": 10 + i, "text": t} for i, t in enumerate(tools)]}


class SettingsTests(unittest.TestCase):
    def test_not_ready_reasons(self):
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": "", "LLM_ALLOW_UPLOAD": ""}, clear=False):
            cfg = llm.settings()
            self.assertFalse(cfg.ready)
            self.assertIn("LLM 미설정", cfg.why_not)
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": ""}, clear=False):
            self.assertIn("미승인", llm.settings().why_not)
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1", "LLM_MODEL": "x-model"}, clear=False):
            cfg = llm.settings()
            self.assertTrue(cfg.ready)
            self.assertEqual(cfg.model, "x-model")


class AskJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1", "LLM_CACHE_DIR": self.tmp.name, "LLM_MODEL": "m"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_json_parsed_cached_and_usage_logged(self):
        payload = {"model": "m-2026", "choices": [{"message": {"content": json.dumps({"findings": [{"line": 1}]})}}],
                   "usage": {"prompt_tokens": 120, "completion_tokens": 30}}
        with mock.patch.object(llm, "_post", return_value=payload) as post:
            first = llm.ask_json("t", "sys", "user")
            second = llm.ask_json("t", "sys", "user")
            self.assertEqual(post.call_count, 1)  # 두 번째는 캐시
        self.assertEqual((first.data, first.cached, first.input_tokens, first.output_tokens), ({"findings": [{"line": 1}]}, False, 120, 30))
        self.assertTrue(second.cached)
        self.assertEqual(llm.usage_summary()["calls"], 1)
        self.assertTrue(list((Path(self.tmp.name) / "t").glob("*.json")))

    def test_bad_json_is_an_error(self):
        payload = {"choices": [{"message": {"content": "not json"}}]}
        with mock.patch.object(llm, "_post", return_value=payload):
            with self.assertRaises(llm.LlmError):
                llm.ask_json("t", "sys", "user2")

    def test_only_allowlisted_tasks_can_call(self):
        with mock.patch.object(llm, "_post") as post:
            with self.assertRaises(llm.LlmError) as caught:
                llm.ask_json("something_else", "s", "u")
            post.assert_not_called()
        self.assertIn("허용되지 않은 작업", str(caught.exception))
        self.assertTrue(llm.task_allowed("perform2_brands"))
        with mock.patch.dict(os.environ, {"LLM_ALLOWED_TASKS": "other"}, clear=False):
            self.assertFalse(llm.task_allowed("perform2_brands"))  # 환경 변수로 더 좁힐 수는 있어도
            self.assertFalse(llm.task_allowed("other"))            # 코드 목록 밖을 열 수는 없다

    def test_not_ready_raises_before_network(self):
        with mock.patch.dict(os.environ, {"LLM_ALLOW_UPLOAD": ""}, clear=False):
            with mock.patch.object(llm, "_post") as post:
                with self.assertRaises(llm.LlmError):
                    llm.ask_json("t", "s", "u")
                post.assert_not_called()


class BrandRuleTests(unittest.TestCase):
    def test_without_key_everything_is_undecided_not_failed(self):
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": "", "LLM_ALLOW_UPLOAD": ""}, clear=False):
            [row] = check_brands([block(["생수"], ["노트북"])])
        self.assertEqual(row["판정"], "판단불가")
        self.assertIn("LLM 미설정", row["비고"][CHECK])

    def test_findings_become_candidates_and_hallucinations_are_dropped(self):
        answer = {"data": {"findings": [
            {"line": 2, "text": "코카콜라", "kind": "상표", "generic": "탄산음료", "confidence": "high", "reason": "브랜드"},
            {"line": 3, "text": "갤럭시 탭", "kind": "모델명", "generic": "태블릿", "confidence": "high", "reason": "제품"},
            {"line": 9, "text": "없는 줄", "kind": "상표", "generic": "", "confidence": "low", "reason": ""},
            {"line": 1, "text": "맥주", "kind": "상품명", "generic": "", "confidence": "low", "reason": "입력에 없는 표현"},
        ]}, "model": "m"}
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1"}, clear=False):
            [row] = check_brands([block(["생수", "코카콜라 1.5L"], ["삼성 갤럭시 탭 S9"])], asker=lambda lines: answer)
        self.assertEqual(row["판정"], "판단불가")  # 후보는 사람 확인(△), 자동 X 없음
        self.assertIn("후보 2건", row["비고"][CHECK])
        self.assertIn("「코카콜라」(상표, high) → 일반 명칭 「탄산음료」", row["비고"][CHECK])
        self.assertEqual(len(row["상세"]), 2)

    def test_low_confidence_is_reference_only(self):
        answer = {"data": {"findings": [{"line": 1, "text": "BEO", "kind": "상품명", "generic": "", "confidence": "low", "reason": "약어"}]}, "model": "m"}
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1"}, clear=False):
            [row] = check_brands([block(["연회 행사 지시서(BEO)"], [])], asker=lambda lines: answer)
        self.assertEqual(row["판정"], "적합")
        self.assertIn("확신 낮은 표현 1건", row["비고"]["참고"])
        self.assertIn("후보에서 제외", row["상세"][0])

    def test_no_findings_is_pass_with_model_note(self):
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1"}, clear=False):
            [row] = check_brands([block(["생수"], ["노트북"])], asker=lambda lines: {"data": {"findings": []}, "model": "m"})
        self.assertEqual(row["판정"], "적합")
        self.assertIn("탐지 없음", row["비고"]["참고"])

    def test_call_failure_is_undecided(self):
        def boom(lines):
            raise llm.LlmError("HTTP 429")
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1"}, clear=False):
            [row] = check_brands([block(["생수"], [])], asker=boom)
        self.assertEqual(row["판정"], "판단불가")
        self.assertIn("429", row["비고"][CHECK])


if __name__ == "__main__":
    unittest.main()
