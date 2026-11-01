"""개발 이력 및 판권 ①: 표 읽기, 양식(신규/개선) 선택, 코드·명칭·자리표시, 판권 표."""

import unittest

from ncs_colophon.config import CheckConfig
from ncs_colophon.rules.colophon import check_colophon, expected_form
from ncs_colophon.tables import read_colophons, read_histories


def history_table(paragraph, blocks):
    """blocks: [(발행일, 라벨2('세분류명'|'학습모듈명'), 값2, 개발기관)] → 실데이터 모양의 표"""
    cells, r = {(0, 0): "NCS학습모듈 개발이력"}, 1
    for date, label2, value2, agency in blocks:
        cells[(r, 0)], cells[(r, 1)] = "발행일", date
        cells[(r + 1, 0)], cells[(r + 1, 1)] = label2, value2
        cells[(r + 2, 0)], cells[(r + 2, 1)] = "개발기관", agency
        cells[(r + 3, 0)], cells[(r + 3, 1)], cells[(r + 3, 2)], cells[(r + 3, 3)] = "집필진", "김철수(대학교)*", "검토진", "이영희(고등학교)"
        cells[(r + 4, 1)], cells[(r + 4, 3)] = "박순희(기업)", "*표시는 대표집필자임"
        r += 5
    return {"paragraph": paragraph, "rows": r, "cols": 4, "cells": cells}


def colophon_table(paragraph, head="객실 예약 관리(LM1203020201_24v3)", agency="한국직업능력연구원", date="2026. 12. 31.", isbn=True):
    cells = {(0, 0): head, (1, 0): "저작권자", (1, 1): "교육부", (2, 0): "연구사업기관", (2, 1): agency, (3, 0): "발행일", (3, 1): date}
    if isbn:
        cells[(4, 0)] = "ISBN"
    return {"paragraph": paragraph, "rows": 5, "cols": 2, "cells": cells}


IMPROVED = [("2021년 1월 1일", "세분류명", "숙박기획·개발(12030202)", "○○협회, 한국직업능력개발원"),
            ("2026년 12월 31일", "학습모듈명", "객실 예약 관리(LM1203020201_24v3)", "한국호텔협회(개발책임자: 홍길동), 한국직업능력연구원")]
NEW = [("2026년 12월 31일", "세분류명", "숙박기획·개발(12030202)", "한국호텔협회(개발책임자: 홍길동), 한국직업능력연구원")]


class TableTests(unittest.TestCase):
    def test_read_histories_and_colophons(self):
        [h] = read_histories([history_table(10, IMPROVED), colophon_table(20)])
        self.assertEqual(len(h["blocks"]), 2)
        self.assertEqual(h["blocks"][1]["학습모듈명"], "객실 예약 관리(LM1203020201_24v3)")
        self.assertEqual((h["blocks"][1]["집필진"], h["blocks"][1]["검토진"]), (["김철수(대학교)*", "박순희(기업)"], ["이영희(고등학교)"]))
        [c] = read_colophons([history_table(10, IMPROVED), colophon_table(20)])
        self.assertEqual((c["code"], c["저작권자"], c["ISBN"], c["isbn_value"]), ("LM1203020201_24v3", "교육부", True, ""))

    def test_expected_form(self):
        self.assertEqual((expected_form("LM1203020201_24v3"), expected_form("LM1203020201_26v1"), expected_form("x")), ("개선", "신규", None))


class RuleTests(unittest.TestCase):
    def judge(self, tables, code="LM1203020201_24v3"):
        return check_colophon(read_histories(tables), read_colophons(tables), code, CheckConfig())

    def test_improved_module_with_improved_form_passes(self):
        rows = self.judge([history_table(10, IMPROVED), colophon_table(20)])
        self.assertEqual([(r["region_path"].split(" > ")[-1], r["판정"]) for r in rows], [("양식", "적합"), ("개발 이력", "적합"), ("판권", "적합")])

    def test_new_module_with_new_form_and_subclass_code(self):
        rows = self.judge([history_table(10, NEW), colophon_table(20, head="객실 예약 관리(LM1203020201_26v1)")], code="LM1203020201_26v1")
        self.assertEqual([r["판정"] for r in rows], ["적합", "적합", "적합"])
        wrong = [("2026년 12월 31일", "세분류명", "숙박기획·개발(99999999)", "한국호텔협회, 한국직업능력연구원")]
        rows = self.judge([history_table(10, wrong), colophon_table(20, head="객실 예약 관리(LM1203020201_26v1)")], code="LM1203020201_26v1")
        self.assertEqual(rows[1]["체크"]["세분류 코드 8자리"], "X")

    def test_both_forms_left_placeholders_and_colophon_errors(self):
        template = [("2026년 12월 31일", "세분류명", "세분류명(세분류 코드번호)", "○○○협회(개발책임자: ○○○), 한국직업능력연구원")]
        rows = self.judge([history_table(10, template), history_table(30, IMPROVED), colophon_table(50), colophon_table(60, agency="한국직업능력개발원", date="20XX. XX. XX.", isbn=False)])
        by = {r["region_path"].split(" > ")[-1]: r for r in rows}
        self.assertIn("2개", by["양식"]["비고"]["양식"])
        self.assertEqual(by["개발 이력"]["판정"], "적합", "개선 양식 표(기대 양식)를 골라 검사한다")
        self.assertEqual({k for k, v in by["판권"]["체크"].items() if v == "X"}, {"판권 표", "연구사업기관", "발행일", "ISBN 행"})
        rows = self.judge([history_table(10, template), colophon_table(50)], code="LM1203020201_26v1")
        self.assertIn("세분류명", rows[1]["비고"]["자리표시 제거"])

    def test_missing_tables(self):
        rows = self.judge([])
        self.assertEqual([r["판정"] for r in rows], ["부적합", "부적합"])


if __name__ == "__main__":
    unittest.main()
