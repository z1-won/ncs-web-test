"""그림 판독·캡션 일치(가짜 그림 모델): 프롬프트에 맥락이 들어가는가, 답 검증, 외부 전송 금지 그림은 보내지 않음, 점검 ③ 값."""

import os
import unittest
from unittest import mock

from ncs_figures.checks import run_checks
from ncs_figures.config import DEFAULT_CONFIG
from ncs_figures.models import Resources
from ncs_figures.pipeline import review_figures
from ncs_figures.prompts import build
from ncs_figures.reading import context_values, judge_caption, read_and_judge, read_figure
from ncs_figures.vision import FakeVision, VisionError, load_model, why_not_send

from .test_review_rules import ctx, item as _item


def item(c):
    return _item(c, transfer="허용")          # 보내도 되는 그림으로 시험(전송 규칙은 test_review_rules)


def reader(kind="도표", verdict="match", reason="상자와 화살표로 '전략 체계'가 보임", words=("전략 체계",)):
    def answer(task, text):
        return {"판독": {"유형": kind, "설명": "상자 세 개가 화살표로 이어져 있다.", "그림 속 글자": ["전략 체계"],
                         "키워드": ["전략", "체계"], "맥락 요약": "경영 전략의 구성을 설명", "확신도": 0.8},
                "캡션": {"판정": verdict, "근거": reason, "읽은 글자": list(words)}}
    return FakeVision(answer)


class PromptTests(unittest.TestCase):
    def test_context_comes_from_document_not_model(self):
        c = ctx(caption="[그림 1-1] 경영 전략 체계")
        values = context_values(item(c), module_name="SW제품기업 내부환경 분석")
        system, user = build("fig_read", values)
        self.assertIn("[그림 1-1] 경영 전략 체계", user)
        self.assertIn("SW제품기업 내부환경 분석", user)
        self.assertNotIn("본문에서 이 그림을 가리키는 문장", user)      # 빈 맥락 줄은 빠진다(모델이 채우지 않게)
        self.assertIn("화면 캡처", system)                               # 유형 정의는 system에
        self.assertIn("uncertain", system)                               # 캡션 판정 기준도 같은 system에


class ReadingTests(unittest.TestCase):
    def test_read_and_caption_ok(self):
        it = item(ctx())
        model = reader()
        reading = read_figure(it, model)
        self.assertEqual((reading["status"], reading["유형"]), ("완료", "도표"))
        self.assertEqual(model.calls[0][0], "fig_read")
        judged = judge_caption(it, model)
        self.assertEqual((judged["판정"], judged["검증"]), ("match", "통과"))
        both = reader()
        reading, judged = read_and_judge(it, both)
        self.assertEqual((reading["유형"], judged["판정"], len(both.calls)), ("도표", "match", 1))   # 그림 한 번만 보냄

    def test_invented_quote_is_rejected(self):
        judged = judge_caption(item(ctx()), reader(reason="그림에 '고객 만족도 조사'라고 적혀 있음", words=("전략 체계",)))
        self.assertNotEqual(judged["검증"], "통과")

    def test_wrong_type_is_failure(self):
        self.assertEqual(read_figure(item(ctx()), reader(kind="만화"))["status"], "실패")

    def test_blocked_image_is_not_sent(self):
        model = reader()                                                                   # 사람이 막은 그림·FIG_TRANSFER_OTHERS로 막은 그림
        self.assertEqual(read_figure(_item(ctx(), transfer="금지"), model)["status"], "미실행")
        self.assertEqual(read_figure(_item(ctx(source=None), transfer="확인 전"), model)["status"], "미실행")
        self.assertEqual(model.calls, [])


class CheckTests(unittest.TestCase):
    def outcome(self, model):
        checks, _ = run_checks(item(ctx()), Resources(asker=model), DEFAULT_CONFIG)
        return next(c for c in checks if c.name == "③캡션 일치")

    def test_caption_values(self):
        self.assertEqual(self.outcome(reader()).value, "O")
        self.assertEqual(self.outcome(reader(verdict="mismatch")).value, "△")       # 모델 결과로 X를 내지 않음
        self.assertEqual(self.outcome(reader(verdict="uncertain")).value, "△")
        invented = self.outcome(reader(reason="그림에 '고객 만족도 조사'라고 적혀 있음"))
        self.assertEqual(invented.value, "△")                                      # 검증 실패한 match는 O로 올리지 않음

    def test_no_model_means_skipped(self):
        checks, _ = run_checks(item(ctx()), Resources(), DEFAULT_CONFIG)
        caption = next(c for c in checks if c.name == "③캡션 일치")
        self.assertIsNone(caption.value)

    def test_review_with_reading(self):
        [review] = review_figures([item(ctx())], Resources(asker=reader()), read=True)
        self.assertEqual(review.reading["유형"], "도표")
        self.assertEqual(len(review.model_calls), 1)


class VisionSettingTests(unittest.TestCase):
    def test_send_requires_both_approvals(self):
        with mock.patch.dict(os.environ, {"LLM_ALLOW_UPLOAD": "1", "LLM_ALLOW_IMAGE_UPLOAD": "", "LLM_LOCAL_ONLY": ""}):
            self.assertIn("그림 외부 전송", why_not_send())
        with mock.patch.dict(os.environ, {"LLM_ALLOW_UPLOAD": "1", "LLM_ALLOW_IMAGE_UPLOAD": "1", "LLM_LOCAL_ONLY": "1"}):
            self.assertIn("로컬 전용", why_not_send())

    def test_model_spec(self):
        self.assertEqual(load_model("anthropic:claude-sonnet-5-5").name, "anthropic:claude-sonnet-5-5")
        with self.assertRaises(ValueError):
            load_model("nope:model")

    def test_cached_model_refuses_without_approval(self):
        model = load_model("anthropic:claude-sonnet-5-5")
        with mock.patch.dict(os.environ, {"LLM_ALLOW_UPLOAD": "", "LLM_CACHE_DIR": os.devnull + "_none"}):
            with self.assertRaises(VisionError):
                model.ask(task="t", system="s", text="x", image_png=b"png", schema={})


if __name__ == "__main__":
    unittest.main()
