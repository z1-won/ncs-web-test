"""위치 ②③④: 목록 비교 요약(summarize_diff)과 체크별 비고·방향 문장."""

import unittest

from ncs_position.compare import list_diff, summarize_diff
from ncs_position.rules.position import check_position

PLAN = {"세분류": [f"세분류{i}" for i in range(1, 19)], "능력단위": ["가", "나", "다"], "학습모듈명": ["가", "나", "다"],
        "행쌍": [("가", "가"), ("나", "나"), ("다", "다")]}


class DiffTests(unittest.TestCase):
    def test_summary_counts_missing_and_changed(self):
        content, order, notes, info = list_diff("세분류", PLAN["세분류"], PLAN["세분류"][:8])
        self.assertEqual((content, order, len(info["missing"])), ("X", "O", 10))
        self.assertEqual(summarize_diff("세분류", info), "세분류 원고 8 / 개발계획서 18 · 누락 10(개발계획서에만: 세분류9, 세분류10, 세분류11 외 7)")
        content, order, notes, info = list_diff("능력단위", ["가", "나", "다"], ["가", "라", "다"])
        self.assertEqual(summarize_diff("능력단위", info), "능력단위 다름 1: 원고 「라」 / 개발계획서 「나」 — 글자가 다름")
        # 띄어쓰기 하나 차이도 어느 문서의 어떤 문구인지 각각 보인다
        _, _, notes, info = list_diff("능력단위", ["AIoT 운영플랫폼요구사항분석"], ["AIoT 운영 플랫폼 요구사항 분석"])
        self.assertEqual(summarize_diff("능력단위", info), "능력단위 다름 1: 원고 「AIoT 운영 플랫폼 요구사항 분석」 / 개발계획서 「AIoT 운영플랫폼요구사항분석」 — 띄어쓰기만 다름")
        self.assertEqual(notes, ["능력단위 1번째 다름: 원고 「AIoT 운영 플랫폼 요구사항 분석」 / 개발계획서 「AIoT 운영플랫폼요구사항분석」 — 띄어쓰기만 다름"])
        _, _, notes, _ = list_diff("능력단위", ["가", "나"], ["가", "다", "라"])
        self.assertEqual(notes[1:], ["능력단위 누락: 개발계획서에는 「나」가 있는데 원고에 없음", "능력단위 원고에만 있음: 「다」 (개발계획서에 없음)", "능력단위 원고에만 있음: 「라」 (개발계획서에 없음)"])
        self.assertEqual(summarize_diff("능력단위", list_diff("능력단위", ["가", "나"], ["나", "가"])[3]), "능력단위 순서 다름")


class PositionRuleTests(unittest.TestCase):
    def test_notes_per_check_and_direction_suggestion(self):
        manuscript = {"세분류": PLAN["세분류"][:8], "능력단위": ["가", "나", "다"], "학습모듈명": ["가", "나", "다"], "행쌍": PLAN["행쌍"]}
        [row] = check_position(PLAN, manuscript)
        self.assertEqual(row["판정"], "부적합")
        self.assertEqual(set(row["비고"]), {"② 세분류 목록·순서 일치"})
        self.assertTrue(row["비고"]["② 세분류 목록·순서 일치"].startswith("세분류 원고 8 / 개발계획서 18 · 누락 10("))
        self.assertEqual(row["수정 제안"], "개발계획서의 세분류 18개를 순서대로 모두 나열")
        self.assertEqual(len(row["상세"]), 11)  # 개수 1 + 누락 10
        [ok] = check_position(PLAN, {**manuscript, "세분류": PLAN["세분류"]})
        self.assertEqual((ok["판정"], ok["비고"], ok["수정 제안"]), ("적합", {}, None))


if __name__ == "__main__":
    unittest.main()
