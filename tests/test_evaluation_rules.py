"""평가 ②(평가 준거 학습 목표)·③(평가 방법 수): 표 읽기와 규칙. 실데이터(호텔 예약 모듈) 평가 표 구조를 본뜬다."""

import unittest

from ncs_evaluation.region import criteria_units, table_kind
from ncs_evaluation.rules.feedback import check_feedback
from ncs_evaluation.rules.goals import check_criteria_goals
from ncs_evaluation.rules.methods import check_methods

A = "호텔의 객실 유형(위치, 면적, 객실 타입 등)에 따라 객실 및 부대시설 정보를 구분할 수 있다."
B = "객실 요금 종류(공표요금, 특별요금, 계약요금 등)에 따라 마켓별 요금을 구분하여 적용할 수 있다."
C = "객실 판매 촉진 전략에 따라 패키지나 프로모션 상품을 구분하여 판매할 수 있다."


def criteria_table():
    """학습 내용 | 학습 목표 | 성취수준(상·중·하). 학습 내용 셀은 병합되어 첫 행에만 있다."""
    cells = {(0, 0): "학습 내용", (0, 1): "학습 목표 > 개발계획서에 따라 일부 수정함 – 컨펌 要", (0, 2): "성취수준",
             (1, 2): "상", (1, 3): "중", (1, 4): "하",
             (2, 0): "호텔정보 구분", (2, 1): "- " + A, (2, 2): "", (3, 1): "- " + B, (3, 2): "",
             (4, 0): "상품 설명", (4, 1): "- " + C.replace("판매 촉진", "판매촉진")}
    return {"paragraph": 10, "rows": 5, "cols": 5, "cells": cells}


def method_table():
    return {"paragraph": 20, "rows": 3, "cols": 5, "cells": {(0, 0): "학습 내용", (0, 1): "평가 항목", (0, 2): "성취수준",
                                                              (2, 0): "호텔정보 구분", (2, 1): "- 구분하는지 여부"}}


class RegionTests(unittest.TestCase):
    def test_feedback_block_pattern_tolerates_leading_junk(self):
        from ncs_evaluation.region import FEEDBACK_BLOCK
        self.assertEqual(FEEDBACK_BLOCK.search("후, 성취 수준이 낮은 학습자에게는보충 1. 서술형 시험").groups(), ("1", "서술형 시험"))
        self.assertEqual(FEEDBACK_BLOCK.search("2. 평가자 질문").groups(), ("2", "평가자 질문"))
        self.assertIsNone(FEEDBACK_BLOCK.search("- 객실 요금을 평가한 후 1. 보충한다."))

    def test_table_kind_and_units(self):
        self.assertEqual(table_kind(criteria_table())[0], "평가 준거")
        self.assertEqual(table_kind(method_table())[0], "평가 방법")
        self.assertIsNone(table_kind({"cells": {(0, 0): "학습 1", (0, 1): "제목"}}))
        _, header_row, name_col, value_col = table_kind(criteria_table())
        units = criteria_units(criteria_table(), header_row, name_col, value_col)
        self.assertEqual([(u["name"], len(u["goals"])) for u in units], [("호텔정보 구분", 2), ("상품 설명", 1)])


def region(lesson=1, **override):
    base = {"lesson": lesson, "found": True, "start": 0, "end": 99, "criteria": [], "criteria_tables": 0,
            "methods": [], "method_tables": 0, "feedback_found": False, "feedback": [], "notes": []}
    base.update(override)
    return base


PLAN = {"내용": {(1, 1): {"text": "호텔정보 구분", "goals": ["1.1 " + A, "1.2 " + B]},
                (1, 2): {"text": "상품 설명", "goals": ["2.1 " + C]},
                (2, 1): {"text": "예약 현황 조회", "goals": ["1.1 x"]}}}


class CriteriaGoalsTests(unittest.TestCase):
    def units(self):
        _, h, n, v = table_kind(criteria_table())
        return criteria_units(criteria_table(), h, n, v)

    def test_match_and_spacing_difference(self):
        rows = check_criteria_goals([region(criteria=[self.units()], criteria_tables=1)], PLAN)
        self.assertEqual([(r["위치"], r["region_path"].split(" > ")[-1], r["판정"]) for r in rows],
                         [("학습 1", "호텔정보 구분", "적합"), ("학습 1", "상품 설명", "부적합")])
        self.assertEqual(rows[1]["비고"]["② 평가 준거 학습 목표 계획서 일치"], "1-2 1번째 평가 준거 「판매촉진」 / 개발계획서 「판매 촉진」 (띄어쓰기만 다름)")
        self.assertEqual(rows[1]["개발계획서"], ["2.1 " + C])

    def test_unknown_name_missing_table_no_plan_and_no_region(self):
        unknown = [{"name": "없는 이름", "goals": [A], "row": 2}]
        [row] = check_criteria_goals([region(criteria=[unknown], criteria_tables=1)], PLAN)
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("같은 이름의 학습 내용이 없음", row["비고"]["② 평가 준거 학습 목표 계획서 일치"])
        [row] = check_criteria_goals([region()], PLAN)
        self.assertEqual((row["판정"], row["비고"]["② 평가 준거 학습 목표 계획서 일치"]), ("부적합", "평가 준거 표(학습 내용 | 학습 목표)를 찾지 못함"))
        [row] = check_criteria_goals([region(criteria=[self.units()[:1]], criteria_tables=1)], None)
        self.assertEqual(row["체크"], {"② 평가 준거 학습 목표 계획서 일치": "-"})
        [row] = check_criteria_goals([region(found=False, notes=["평가 머리를 찾지 못함"])], PLAN)
        self.assertEqual(row["판정"], "판단불가")


class MethodsTests(unittest.TestCase):
    def test_counts_and_table_mismatch(self):
        three = region(methods=[{"idx": 1, "name": "서술형 시험"}, {"idx": 2, "name": "평가자 질문"}, {"idx": 3, "name": "역할 연기"}], method_tables=3)
        one = region(2, methods=[{"idx": 1, "name": "서술형 시험"}], method_tables=1)
        gap = region(3, methods=[{"idx": 1, "name": "서술형 시험"}, {"idx": 2, "name": "평가자 질문"}], method_tables=1)
        rows = check_methods([three, one, gap, region(4, found=False)])
        self.assertEqual([r["판정"] for r in rows], ["적합", "부적합", "부적합", "판단불가"])
        self.assertEqual(rows[1]["비고"]["③ 평가 방법 2개 이상"], "1개 — 2개 이상 제시해야 함: 서술형 시험")
        self.assertEqual(rows[2]["체크"], {"③ 평가 방법 2개 이상": "O", "방법별 표 수": "X"})
        self.assertEqual(rows[0]["위치"], "학습 1")

    def test_tables_without_bullets_is_undecided(self):
        [row] = check_methods([region(method_tables=2)])
        self.assertEqual(row["판정"], "판단불가")


class FeedbackTests(unittest.TestCase):
    METHODS = [{"idx": 1, "name": "서술형 시험"}, {"idx": 2, "name": "역할 연기"}]

    def block(self, no, name, text):
        return {"no": no, "name": name, "idx": 10 + no, "text": text}

    def test_matching_blocks_with_both_feedbacks_pass(self):
        fb = [self.block(1, "서술형 시험", "- 미흡한 부분을 보충 설명해준다. - 정확히 이해한 경우 심화 학습을 유도한다."),
              self.block(2, "역할 연기", "- 성취 수준이 낮은 학습자에게는 보충 지도하고, 높은 학습자에게는 심화 과제를 준다.")]
        [row] = check_feedback([region(methods=self.METHODS, feedback_found=True, feedback=fb)])
        self.assertEqual(row["판정"], "적합", row["비고"])
        self.assertEqual(row["원고"]["피드백"], ["서술형 시험", "역할 연기"])

    def test_count_mismatch_missing_head_and_keyword_gap(self):
        one = [self.block(1, "서술형 시험", "- 보충 설명해준다. - 심화 학습을 유도한다.")]
        [row] = check_feedback([region(methods=self.METHODS, feedback_found=True, feedback=one)])
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("피드백 없는 방법: 역할 연기", row["비고"]["⑤ 방법별 피드백 개수·이름 일치"])
        [row] = check_feedback([region(methods=self.METHODS)])
        self.assertEqual(row["비고"]["⑤ 방법별 피드백 개수·이름 일치"], "'피드백' 소제목을 찾지 못함")
        weak = [self.block(1, "서술형 시험", "- 보충 설명해준다."), self.block(2, "역할 연기", "- 심화 과제를 준다.")]
        [row] = check_feedback([region(methods=self.METHODS, feedback_found=True, feedback=weak)])
        self.assertEqual(row["판정"], "판단불가")
        self.assertIn("서술형 시험(심화 문구 없음)", row["비고"]["⑤ 심화·보충 학습 각각 제시"])
        self.assertIn("역할 연기(보충 문구 없음)", row["비고"]["⑤ 심화·보충 학습 각각 제시"])


if __name__ == "__main__":
    unittest.main()
