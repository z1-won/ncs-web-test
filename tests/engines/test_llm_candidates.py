"""LLM 후보 규칙 — 수행 내용 ③(안전·유의 사항 추상성)과 평가 ④(평가 항목 구체성·목표 연관). 모델은 asker 대역으로 바꿔 네트워크를 쓰지 않는다."""

import os
import unittest
from unittest import mock

from ncs_core import llm
from ncs_evaluation.rules.item_content import CONTENT, check_item_content
from ncs_perform.rules.safety import ABSTRACT, WRITTEN, check_safety

NO_LLM = {"LLM_API_KEY": "", "OPENAI_API_KEY": "", "LLM_ALLOW_UPLOAD": ""}
ON = {"LLM_API_KEY": "k", "LLM_ALLOW_UPLOAD": "1"}


def block(safety, missing=()):
    return {"block_id": "학습 내용 1-1 > 수행 내용 1", "unit": "1-1", "perform_no": 1, "소제목 누락": list(missing),
            "안전": [{"idx": 10 + i, "text": text} for i, text in enumerate(safety)]}


def answer(*findings):
    return lambda lines: {"data": {"findings": list(findings)}, "model": "m"}


class SafetyTests(unittest.TestCase):
    def test_missing_or_empty_or_none_fails_without_llm(self):
        """필수 작성 — 소제목 없음·내용 없음·'해당 사항 없음'은 LLM과 무관하게 부적합."""
        with mock.patch.dict(os.environ, NO_LLM, clear=False):
            rows = check_safety([block([], missing=["안전"]), block(["안전‧유의 사항(필수작성)"]), block(["• 해당 사항 없음"])])
        self.assertEqual([(r["체크"][WRITTEN], r["체크"][ABSTRACT], r["판정"]) for r in rows], [("X", "-", "부적합")] * 3)
        self.assertIn("소제목을 찾지 못함", rows[0]["비고"][WRITTEN])
        self.assertIn("내용이 없음", rows[1]["비고"][WRITTEN])
        self.assertIn("해당 사항 없음", rows[2]["비고"][WRITTEN])

    def test_without_key_abstractness_is_undecided(self):
        with mock.patch.dict(os.environ, NO_LLM, clear=False):
            [row] = check_safety([block(["전원 케이블을 뽑은 뒤 덮개를 연다."])])
        self.assertEqual((row["체크"], row["판정"]), ({WRITTEN: "O", ABSTRACT: "△"}, "판단불가"))
        self.assertIn("LLM 미설정", row["비고"][ABSTRACT])

    def test_abstract_lines_are_candidates_and_bad_line_numbers_are_dropped(self):
        found = answer({"line": 2, "reason": "무엇을 조심하는지 없음", "suggestion": "대상과 상황을 적기"},
                       {"line": 9, "reason": "없는 줄"}, {"line": "x", "reason": "번호 아님"}, {"line": 2, "reason": "같은 줄 두 번"})
        with mock.patch.dict(os.environ, ON, clear=False):
            [row] = check_safety([block(["전원 케이블을 뽑은 뒤 덮개를 연다.", "안전에 유의한다."])], asker=found)
        self.assertEqual((row["체크"], row["판정"]), ({WRITTEN: "O", ABSTRACT: "△"}, "판단불가"))   # 후보까지만 — 부적합 아님
        self.assertIn("후보 2줄 중 1줄", row["비고"][ABSTRACT])
        self.assertIn("「안전에 유의한다.」 — 무엇을 조심하는지 없음 → 대상과 상황을 적기", row["비고"][ABSTRACT])
        self.assertEqual(len(row["상세"]), 1)

    def test_no_findings_pass_and_failure_is_undecided(self):
        with mock.patch.dict(os.environ, ON, clear=False):
            [ok] = check_safety([block(["전원 케이블을 뽑은 뒤 덮개를 연다."])], asker=answer())

            def boom(lines):
                raise llm.LlmError("HTTP 500")
            [failed] = check_safety([block(["전원 케이블을 뽑은 뒤 덮개를 연다."])], asker=boom)
        self.assertEqual((ok["판정"], ok["비고"]["참고"]), ("적합", "LLM(m) 추상적 표현 탐지 없음"))
        self.assertEqual((failed["판정"], failed["비고"][ABSTRACT]), ("판단불가", "LLM 호출 실패: HTTP 500"))

    def test_no_blocks_is_undecided(self):
        self.assertEqual([r["판정"] for r in check_safety([])], ["판단불가"])

    def test_only_safety_lines_are_sent(self):
        seen = []
        with mock.patch.dict(os.environ, ON, clear=False), \
                mock.patch.object(llm, "ask_json", side_effect=lambda task, system, user: seen.append((task, user)) or
                                  llm.LlmAnswer({"findings": []}, "m", False, 1, 1)):
            check_safety([block(["안전‧유의 사항(필수작성)", "장갑을 낀다."])])
        self.assertEqual(seen, [("perform3_safety", "1. 장갑을 낀다.")])   # 소제목은 빼고, 다른 구역 글은 보내지 않는다


def region(items, goals=("객실 유형에 따라 정보를 구분할 수 있다.",), found=True):
    return {"lesson": 1, "found": found, "criteria": [[{"name": "호텔정보 구분", "goals": list(goals)}]] if goals else [],
            "method_items": [[{"name": "호텔정보 구분", "item": item, "row": i} for i, item in enumerate(items)]]}


class ItemContentTests(unittest.TestCase):
    def test_candidates_stay_undecided(self):
        found = answer({"line": 2, "kind": "추상적", "reason": "무엇을 평가하는지 없음", "suggestion": "평가 대상을 적기"})
        with mock.patch.dict(os.environ, ON, clear=False):
            [row] = check_item_content([region(["객실 유형별 부대시설 구분 여부", "내용 이해 여부"])], asker=found)
        self.assertEqual((row["item_id"], row["체크"], row["판정"]), ("F02-평가-④", {CONTENT: "△"}, "판단불가"))
        self.assertIn("후보 2개 중 1개", row["비고"][CONTENT])
        self.assertIn("「[호텔정보 구분] 내용 이해 여부」(추상적) — 무엇을 평가하는지 없음", row["비고"][CONTENT])

    def test_pass_without_findings_and_undecided_without_key_or_goals(self):
        with mock.patch.dict(os.environ, ON, clear=False):
            [ok] = check_item_content([region(["객실 유형별 부대시설 구분 여부"])], asker=answer())
            [no_goals] = check_item_content([region(["객실 유형별 부대시설 구분 여부"], goals=())], asker=answer())
        with mock.patch.dict(os.environ, NO_LLM, clear=False):
            [no_key] = check_item_content([region(["객실 유형별 부대시설 구분 여부"])])
        self.assertEqual(ok["판정"], "적합")
        self.assertEqual((no_goals["판정"], no_key["판정"]), ("판단불가", "판단불가"))
        self.assertIn("학습 목표를 읽지 못해", no_goals["비고"][CONTENT])
        self.assertIn("LLM 미설정", no_key["비고"][CONTENT])

    def test_unread_items_are_left_to_the_ending_check(self):
        rows = check_item_content([region([], found=False), region([])])
        self.assertEqual([r["체크"][CONTENT] for r in rows], ["-", "-"])

    def test_prompt_carries_goals_and_numbered_items_only(self):
        seen = []
        with mock.patch.dict(os.environ, ON, clear=False), \
                mock.patch.object(llm, "ask_json", side_effect=lambda task, system, user: seen.append((task, user)) or
                                  llm.LlmAnswer({"findings": []}, "m", False, 1, 1)):
            check_item_content([region(["객실 유형별 부대시설 구분 여부"])])
        self.assertEqual(seen, [("evaluation4_items",
                                 "[학습 목표]\n- 객실 유형에 따라 정보를 구분할 수 있다.\n\n[평가 항목]\n1. [호텔정보 구분] 객실 유형별 부대시설 구분 여부")])

    def test_tasks_are_on_the_allow_list(self):
        self.assertTrue(llm.task_allowed("perform3_safety") and llm.task_allowed("evaluation4_items"))


if __name__ == "__main__":
    unittest.main()
