"""개요 파서 — 앞부분에 안내 쪽('NCS학습모듈의 이해': 개요 설명 그림의 제목 나열, 다른 모듈의 예시 개요)이 있어도 그 모듈의 개요를 읽는다."""

import unittest
from pathlib import Path

from ncs_core.documents import Document
from ncs_core.manuscript.overview import parse_overview


def doc(lines):
    return Document(path=Path("x.hwpx"), format="hwpx", sections=[lines, []])


GUIDE = ["2. NCS학습모듈의 개요", "3. NCS학습모듈의 내용 체계", "",
         "2. NCS학습모듈의 개요", "학습모듈의 목표", "선수학습", "학습모듈의 내용 체계", "핵심 용어",   # 설명 그림의 제목 나열
         "제작계획 학습모듈의 개요", "학습모듈의 목표", "촬영 대본을 확정할 수 있다.", "선수학습", "영상 기획"]    # 다른 모듈의 예시
OWN = ["SW제품 명세 작성 학습모듈의 개요", "학습모듈의 목표", "사용자의 요구사항을 이해하여 명세를 수립할 수 있다.",
       "선수학습", "요구사항 확인(LM2001020201_19v4), 소프트웨어 공학", "핵심 용어", "요구공학"]


class OverviewHeadTests(unittest.TestCase):
    def test_guide_pages_before_the_module_overview(self):
        got = parse_overview(doc(GUIDE + OWN), 0)
        self.assertEqual(got["개요 제목 p"], len(GUIDE))
        self.assertEqual(got["목표"]["text"], "사용자의 요구사항을 이해하여 명세를 수립할 수 있다.")
        self.assertEqual(got["선수학습"]["items"], ["요구사항 확인(LM2001020201_19v4)", "소프트웨어 공학"])

    def test_single_overview_unchanged(self):
        got = parse_overview(doc(OWN), 0)
        self.assertEqual(got["개요 제목 p"], 0)
        self.assertTrue(got["목표"])

    def test_no_goal_anywhere_falls_back_to_first_head(self):
        got = parse_overview(doc(["가 학습모듈의 개요", "학습모듈의 목표", "선수학습", "나 학습모듈의 개요", "핵심 용어"]), 0)
        self.assertEqual(got["개요 제목 p"], 0)
        self.assertIsNone(got["목표"])


class StructureTableTests(unittest.TestCase):
    def test_values_in_other_columns_than_headers(self):
        """병합 셀 때문에 코드·요소 명칭 값이 머리칸과 한 칸씩 어긋난 표."""
        from ncs_core.manuscript.overview import _structure_from_table
        cells = {(0, 0): "학습", (0, 1): "학습 내용", (0, 3): "NCS 능력단위 요소", (1, 3): "코드번호", (1, 4): "요소 명칭",
                 (2, 0): "1. SW제품 인증 기획하기", (2, 1): "1-1. 국내외 인증 조사", (2, 2): "2001010409_19v4.1", (2, 5): "SW제품 인증 기획하기"}
        got = _structure_from_table({"cells": cells, "paragraph": 9})
        self.assertEqual(got["요소"], [{"code": "2001010409_19v4.1", "name": "SW제품 인증 기획하기", "row": 2}])


if __name__ == "__main__":
    unittest.main()
