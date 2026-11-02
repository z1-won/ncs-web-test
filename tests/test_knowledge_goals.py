"""필요 지식 ⑤: 학습 목표 동일 비교(compare_lists·normalize·check_goals)."""

import unittest

from ncs_knowledge.rules.goals import check_goals, compare_lists, difference, normalize

A = "호텔의 객실 유형(위치, 면적, 객실 타입 등)에 따라 객실 및 부대시설 정보를 구분할 수 있다."
B = "객실 요금 종류(공표요금, 특별요금, 계약요금 등)에 따라 마켓별 요금을 구분하여 적용할 수 있다."
C = "취소율과 노쇼(No-Show)율의 결정에 따라 초과 예약을 받을 수 있다."


class NormalizeTests(unittest.TestCase):
    def test_strips_markers_only(self):
        self.assertEqual(normalize("1.2 " + B), B)
        self.assertEqual(normalize("•" + B), B)
        self.assertEqual(normalize("- " + B), B)
        self.assertEqual(normalize("  " + B + " "), B)

    def test_keeps_spacing_case_and_punctuation(self):
        self.assertNotEqual(normalize("공표 요금"), normalize("공표요금"))
        self.assertNotEqual(normalize("Check-in"), normalize("Check-In"))
        self.assertNotEqual(normalize(B), normalize(B.rstrip(".")))


class CompareListsTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(compare_lists([A, B], [A, B]), [])

    def test_order_only_is_same(self):
        self.assertEqual(compare_lists([A, B, C], [B, A, C]), [])

    def test_spacing_difference_is_reported_by_word(self):
        actual = B.replace("공표요금", "공표 요금")
        self.assertEqual(compare_lists([A, B], [A, actual]), ["2번째 본문 「종류(공표 요금,」, 계획서 「종류(공표요금,」 (띄어쓰기만 다름)"])

    def test_case_difference(self):
        self.assertEqual(compare_lists(["Early Check-In 가능"], ["Early Check-in 가능"]), ["1번째 본문 「Check-in」, 계획서 「Check-In」"])

    def test_missing_and_count(self):
        self.assertEqual(compare_lists([A, B], [A]), ["개수: 본문 1개, 계획서 2개", f"2번째 누락: 계획서에는 「{B}」가 있는데 본문에 없음"])

    def test_extra_sentence_in_manuscript(self):
        self.assertEqual(compare_lists([A], [A, C]), ["개수: 본문 2개, 계획서 1개", f"본문에만 있음 「{C}」 (계획서에 없음)"])

    def test_word_change_pairs_with_closest_sentence(self):
        actual = A.replace("구분할", "설명할")
        self.assertEqual(compare_lists([A, B], [B, actual]), ["1번째 본문 「설명할」, 계획서 「구분할」"])

    def test_difference_marks_omitted_words(self):
        self.assertEqual(difference("SNS, 모바일 등으로", "SNS 등으로"), "본문 「SNS」, 계획서 「SNS, 모바일」")


class CheckGoalsTests(unittest.TestCase):
    def unit(self, goals, goal_k=5):
        return {"no": 1, "sub": 1, "text": "호텔정보 구분", "lesson": 1, "goal": goals, "goal_k": goal_k}

    def test_no_plan_is_not_applicable(self):
        [row] = check_goals(None, [self.unit(["•" + A])])
        self.assertEqual(row["체크"], {"개발계획서 학습 목표 일치": "-"})

    def test_pass_and_fail_with_unit_key_in_note(self):
        plan = {"내용": {(1, 1): {"text": "호텔정보 구분", "goals": ["1.1 " + A, "1.2 " + B]}}}
        [ok] = check_goals(plan, [self.unit(["•" + B, "•" + A])])  # 순서만 다름
        self.assertEqual(ok["판정"], "적합")
        self.assertEqual(ok["비고"], {})
        [bad] = check_goals(plan, [self.unit(["•" + A, "•" + B.replace("공표요금", "공표 요금")])])
        self.assertEqual(bad["판정"], "부적합")
        self.assertTrue(bad["비고"]["개발계획서 학습 목표 일치"].startswith("1-1 2번째 본문 학습 목표 「종류(공표 요금,」, 개발계획서 「종류(공표요금,」"))
        self.assertEqual(bad["개발계획서"], ["1.1 " + A, "1.2 " + B])

    def test_missing_goal_block_and_unknown_unit(self):
        plan = {"내용": {(2, 1): {"text": "x", "goals": [A]}}}
        [row] = check_goals(plan, [self.unit([], goal_k=None)])
        self.assertEqual(row["체크"]["학습 목표 블록"], "X")
        self.assertIn("1-1 개발계획서에 없음", row["비고"]["개발계획서 학습 목표 일치"])


if __name__ == "__main__":
    unittest.main()
