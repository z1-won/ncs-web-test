"""LLM 호출 계층(ncs_core.llm)과 수행 ②(상표·상품·제조사명 후보) 규칙 — 네트워크 없이 가짜 응답으로."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ncs_core import llm
from ncs_perform.rules.brands import CHECK, DICTIONARY, check_brands


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


class ProviderTests(unittest.TestCase):
    """제공자 고르기 — LLM_PROVIDER, 없으면 키·모델 이름. 어긋난 설정으로는 키를 보내지 않는다."""

    CLEAN = {"LLM_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "LLM_PROVIDER": "", "LLM_MODEL": "", "LLM_BASE_URL": "",
             "LLM_ALLOW_UPLOAD": "1", "LLM_EFFORT": "low"}

    def cfg(self, **env):
        with mock.patch.dict(os.environ, {**self.CLEAN, **env}, clear=False):
            return llm.settings()

    def test_openai_stays_the_default(self):
        cfg = self.cfg(LLM_API_KEY="sk-proj-x")
        self.assertEqual((cfg.provider, cfg.model, cfg.base_url), ("openai", "gpt-5.4-mini", "https://api.openai.com/v1"))
        self.assertTrue(cfg.ready)
        self.assertEqual(llm._headers(cfg)["Authorization"], "Bearer sk-proj-x")

    def test_claude_key_or_model_selects_anthropic(self):
        cfg = self.cfg(LLM_API_KEY="sk-ant-x", LLM_MODEL="sonnet-5.5")
        self.assertEqual((cfg.provider, cfg.model, cfg.base_url), ("anthropic", "claude-sonnet-5-5", "https://api.anthropic.com/v1"))
        headers = llm._headers(cfg)
        self.assertEqual((headers["x-api-key"], headers["anthropic-version"]), ("sk-ant-x", llm.ANTHROPIC_VERSION))
        self.assertNotIn("Authorization", headers)                       # Claude 키를 Bearer로 보내지 않는다
        self.assertEqual(self.cfg(LLM_API_KEY="sk-ant-x").model, "claude-opus-5-5")
        self.assertEqual(self.cfg(ANTHROPIC_API_KEY="sk-ant-y").provider, "anthropic")
        self.assertEqual(self.cfg(LLM_API_KEY="k", LLM_MODEL="claude-haiku-5-5", LLM_BASE_URL="http://proxy.test/v1").provider, "anthropic")

    def test_mismatched_key_and_destination_is_not_ready(self):
        forced = self.cfg(LLM_API_KEY="sk-ant-x", LLM_PROVIDER="openai")
        self.assertFalse(forced.ready)
        self.assertIn("Claude(Anthropic) 키", forced.why_not)
        wrong_url = self.cfg(LLM_API_KEY="sk-ant-x", LLM_BASE_URL="https://api.openai.com/v1")
        self.assertFalse(wrong_url.ready)
        with mock.patch.dict(os.environ, {**self.CLEAN, "LLM_API_KEY": "sk-ant-x", "LLM_PROVIDER": "openai"}, clear=False):
            with mock.patch.object(llm, "_post") as post, self.assertRaises(llm.LlmError):
                llm.ask_json("perform2_brands", "s", "u")
            post.assert_not_called()                                     # 키가 다른 회사 서버로 나가지 않는다
        self.assertFalse(self.cfg(LLM_API_KEY="sk-proj-x", LLM_PROVIDER="anthropic").ready)


class AnthropicAskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-ant-k", "OPENAI_API_KEY": "", "LLM_PROVIDER": "", "LLM_BASE_URL": "",
                                                "LLM_ALLOW_UPLOAD": "1", "LLM_CACHE_DIR": self.tmp.name, "LLM_MODEL": "claude-sonnet-5-5",
                                                "LLM_EFFORT": "low"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    @staticmethod
    def message(text, **extra):
        return {"model": "claude-sonnet-5-5", "stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}],
                "usage": {"input_tokens": 100, "cache_read_input_tokens": 20, "output_tokens": 30}, **extra}

    def test_request_shape_and_answer(self):
        with mock.patch.object(llm, "_post", return_value=self.message('{"findings": [{"line": 1}]}')) as post:
            answer = llm.ask_json("perform2_brands", "sys", "user")
            again = llm.ask_json("perform2_brands", "sys", "user")
        self.assertEqual(post.call_count, 1)                                # 두 번째는 캐시
        _, path, body = post.call_args.args
        self.assertEqual(path, "/messages")
        self.assertEqual((body["system"], body["messages"]), ("sys", [{"role": "user", "content": "user"}]))
        self.assertEqual((body["output_config"], body["fallbacks"]), ({"effort": "low"}, "default"))
        self.assertGreaterEqual(body["max_tokens"], 16000)                  # 추론 토큰까지 들어가는 한도
        for removed in ("temperature", "response_format", "max_completion_tokens"):
            self.assertNotIn(removed, body)
        self.assertEqual((answer.data, answer.model, answer.input_tokens, answer.output_tokens), ({"findings": [{"line": 1}]}, "claude-sonnet-5-5", 120, 30))
        self.assertTrue(again.cached)

    def test_json_inside_fence_or_prose_is_read(self):
        fenced = '```json\n{"findings": []}\n```'
        with mock.patch.object(llm, "_post", return_value=self.message(fenced)):
            self.assertEqual(llm.ask_json("perform2_brands", "s", "fenced").data, {"findings": []})
        with mock.patch.object(llm, "_post", return_value=self.message('결과입니다: {"findings": []} 이상입니다.')):
            self.assertEqual(llm.ask_json("perform2_brands", "s", "prose").data, {"findings": []})

    def test_refusal_truncation_and_non_json_are_errors(self):
        cases = [(self.message("", stop_reason="refusal", stop_details={"category": "cyber"}), "거절"),
                 (self.message('{"findings": [', stop_reason="max_tokens"), "잘림"),
                 (self.message("JSON이 아닙니다"), "JSON")]
        for no, (payload, word) in enumerate(cases):
            with mock.patch.object(llm, "_post", return_value=payload), self.assertRaises(llm.LlmError) as caught:
                llm.ask_json("perform2_brands", "s", f"case {no}")
            self.assertIn(word, str(caught.exception))
        self.assertEqual(llm.usage_summary()["calls"], 0)                   # 실패한 호출은 캐시·사용량에 남기지 않는다

    def test_unreadable_json_is_asked_once_more(self):
        with mock.patch.object(llm, "_post", side_effect=[self.message("JSON이 아닙니다"), self.message('{"findings": []}')]) as post:
            self.assertEqual(llm.ask_json("perform2_brands", "s", "retry").data, {"findings": []})
            self.assertEqual(post.call_count, 2)
        with mock.patch.object(llm, "_post", return_value=self.message("JSON이 아닙니다")) as post, self.assertRaises(llm.LlmError):
            llm.ask_json("perform2_brands", "s", "retry twice")
        self.assertEqual(post.call_count, 2)                                # 두 번까지만 묻는다

    def test_effort_and_fallbacks_are_optional(self):
        with mock.patch.dict(os.environ, {"LLM_EFFORT": "", "LLM_MODEL": "claude-haiku-5-5"}, clear=False):
            with mock.patch.object(llm, "_post", return_value=self.message("{}")) as post:
                llm.ask_json("perform2_brands", "s", "u")
            body = post.call_args.args[2]
            self.assertNotIn("output_config", body)
            self.assertNotIn("fallbacks", body)                             # 서버 측 fallback을 받는 모델에만 보낸다
            self.assertNotIn("anthropic-beta", llm._headers(llm.settings()))


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
            first = llm.ask_json("perform2_brands", "sys", "user")
            second = llm.ask_json("perform2_brands", "sys", "user")
            self.assertEqual(post.call_count, 1)  # 두 번째는 캐시
        self.assertEqual((first.data, first.cached, first.input_tokens, first.output_tokens), ({"findings": [{"line": 1}]}, False, 120, 30))
        self.assertTrue(second.cached)
        self.assertEqual(llm.usage_summary()["calls"], 1)
        self.assertTrue(list((Path(self.tmp.name) / "perform2_brands").glob("*.json")))

    def test_expired_cache_is_pruned_and_zero_ttl_disables_cache(self):
        payload = {"model": "m", "choices": [{"message": {"content": "{}"}}], "usage": {}}
        with mock.patch.object(llm, "_post", return_value=payload):
            llm.ask_json("perform2_brands", "sys", "old")
        cached = next((Path(self.tmp.name) / "perform2_brands").glob("*.json"))
        old = time.time() - 31 * 86400
        os.utime(cached, (old, old))
        self.assertEqual(llm.prune_cache(), 1, "기본 30일을 넘긴 캐시(원고 문장 포함)는 지운다")
        self.assertFalse(cached.exists())
        with mock.patch.dict(os.environ, {"LLM_CACHE_TTL_DAYS": "0"}), mock.patch.object(llm, "_post", return_value=payload) as post:
            llm.ask_json("perform2_brands", "sys", "new")
            llm.ask_json("perform2_brands", "sys", "new")
            self.assertEqual(post.call_count, 2, "TTL 0이면 캐시를 쓰지도 남기지도 않는다")
        self.assertFalse(list((Path(self.tmp.name) / "perform2_brands").glob("*.json")))

    def test_bad_json_is_an_error(self):
        payload = {"choices": [{"message": {"content": "not json"}}]}
        with mock.patch.object(llm, "_post", return_value=payload):
            with self.assertRaises(llm.LlmError):
                llm.ask_json("perform2_brands", "sys", "user2")

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
                    llm.ask_json("perform2_brands", "s", "u")
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
        self.assertEqual(row["체크"][CHECK], "△")  # LLM 후보는 사람 확인(△)
        self.assertEqual((row["체크"][DICTIONARY], row["판정"]), ("X", "부적합"))  # 사전에 있는 이름(삼성·갤럭시)은 자동 X
        self.assertIn("「삼성」", row["비고"][DICTIONARY])
        self.assertIn("후보 2건", row["비고"][CHECK])
        self.assertIn("「코카콜라」(상표, high) → 일반 명칭 「탄산음료」", row["비고"][CHECK])
        self.assertEqual(len(row["상세"]), 2)

    def test_llm_only_findings_stay_candidates(self):
        answer = {"data": {"findings": [{"line": 2, "text": "코카콜라", "kind": "상표", "generic": "탄산음료", "confidence": "high", "reason": "브랜드"}]}, "model": "m"}
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1"}, clear=False):
            [row] = check_brands([block(["생수", "코카콜라 1.5L"], ["태블릿"])], asker=lambda lines: answer)
        self.assertEqual((row["체크"][DICTIONARY], row["체크"][CHECK], row["판정"]), ("O", "△", "판단불가"))

    def test_dictionary_runs_without_llm(self):
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": "", "LLM_ALLOW_UPLOAD": ""}, clear=False):
            [hard] = check_brands([block(["엑셀 서식"], ["노트북"])])
            [soft] = check_brands([block(["한글 문서"], ["노트북"])])
        self.assertEqual((hard["체크"][DICTIONARY], hard["판정"]), ("X", "부적합"))
        self.assertIn("「엑셀」→스프레드시트 프로그램", hard["비고"][DICTIONARY])
        self.assertEqual((soft["체크"][DICTIONARY], soft["판정"]), ("△", "판단불가"))

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


class FieldPromptTests(unittest.TestCase):
    """수행 ② 프롬프트가 원고 분야(세분류)에 맞는 공용 명칭을 담는가 — 연회관리 예시가 다른 분야로 새지 않게."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        terms = Path(self.tmp.name) / "terms.tsv"
        terms.write_text("# 주석\n*\tSOP\n12\t여행 일정표\n1203\tPMS\n120302\tBEO\n12030204\t연회 계약서\n"
                         "2001\tMQTT\n99\t잘못된 코드도 대분류로 읽음\nabc\t무시\n", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"NCS_FIELD_TERMS_FILE": str(terms)}, clear=False)
        self.env.start()
        # 테스트 실행 중에는 NCS 목록이 꺼져 있으므로(golden_cases) 두 세분류만 가진 가짜 목록을 넣는다
        names = {"12030204": ("이용·숙박·여행·오락·스포츠", "관광·레저", "숙박서비스", "연회관리"),
                 "20010217": ("정보통신", "정보기술", "정보기술개발", "AIoT운영플랫폼구축")}

        class FakeCatalog:
            def subclass(self, code):
                found = names.get(code.replace("LM", "")[:8])
                return mock.Mock(names=dict(zip(("대분류", "중분류", "소분류", "세분류"), found))) if found else None

        self.catalog = mock.patch("ncs_core.field_terms.catalog", return_value=FakeCatalog())
        self.catalog.start()

    def tearDown(self):
        self.catalog.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_terms_follow_code_prefixes_from_broad_to_narrow(self):
        from ncs_core.field_terms import field_of
        self.assertEqual(field_of("LM1203020401_23v3").terms, ("SOP", "여행 일정표", "PMS", "BEO", "연회 계약서"))
        self.assertEqual(field_of("12030101").terms, ("SOP", "여행 일정표", "PMS"))  # 숙박서비스(120302) 밖의 관광·레저
        self.assertEqual(field_of("LM2001021701_25v1").terms, ("SOP", "MQTT"))
        self.assertEqual(field_of("").terms, ("SOP",))

    def test_prompt_names_the_field_and_keeps_other_fields_out(self):
        from ncs_perform.rules.brands import system_prompt
        banquet = system_prompt("LM1203020401_23v3")
        aiot = system_prompt("LM2001021701_25v1")
        self.assertIn("연회관리", banquet)
        self.assertIn("BEO", banquet)
        self.assertIn("AIoT운영플랫폼구축", aiot)
        self.assertIn("MQTT", aiot)
        self.assertNotIn("BEO", aiot)
        self.assertNotIn("MQTT", banquet)
        self.assertNotIn("원고 분야", system_prompt(""))  # 코드를 모르면 분야 줄 없음

    def test_prompt_without_catalog_still_uses_terms(self):
        from ncs_perform.rules.brands import system_prompt
        with mock.patch("ncs_core.field_terms.catalog", return_value=None):
            prompt = system_prompt("LM1203020401_23v3")
        self.assertNotIn("원고 분야", prompt)
        self.assertIn("BEO", prompt)

    def test_rule_sends_the_field_prompt(self):
        from ncs_perform.rules import brands
        seen = []
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1"}, clear=False), \
                mock.patch.object(brands, "ask_json", side_effect=lambda task, system, user: seen.append(system) or
                                  llm.LlmAnswer({"findings": []}, "m", False, 0, 0)):
            [row] = check_brands([block(["생수"], ["노트북"])], module_code="LM2001021701_25v1")
        self.assertEqual(row["판정"], "적합")
        self.assertIn("AIoT운영플랫폼구축", seen[0])
        self.assertIn("MQTT", seen[0])

    def test_real_terms_file_is_readable(self):
        from ncs_core.field_terms import _read
        rows = _read(str(Path(__file__).resolve().parents[2] / "src" / "ncs_core" / "data" / "field_terms.tsv"))
        self.assertTrue(rows)
        self.assertTrue(all(p == "*" or (p.isdigit() and len(p) in (2, 4, 6, 8)) for p, _ in rows))


if __name__ == "__main__":
    unittest.main()
