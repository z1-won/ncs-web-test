"""구역이 하나뿐인 원고(AIoT 심의본 꼴)를 앞부분/본문 두 구역으로 나누기, 계획서 '1-1 명'(마침표 없음), 차례 '부 록'."""

import unittest
from pathlib import Path

from ncs_core.documents import Document, body_start, split_single_section
from ncs_core.manuscript import parse_plan_toc
from ncs_core.manuscript.patterns import PLAN_SUB, TOC_TAIL


def single_section(styles=True):
    paragraphs = ["[NCS-학습모듈의 위치]", "차 례", "학습 1. 가", "학습모듈의 개요", "핵심 용어", "용어1", "학습 1", "가", "본문", "[그림 1-1] 그림", "참고 자료"]
    names = ["바탕글"] * 6 + ["큰학습-숫자", "큰학습-네비게이터", "바탕글", "바탕글", "바탕글"]
    return Document(Path("x.hwpx"), "hwpx", [paragraphs],
                    tables=[{"section": 0, "paragraph": 1, "rows": 1, "cols": 1, "cells": {}}, {"section": 0, "paragraph": 9, "rows": 1, "cols": 1, "cells": {}}],
                    images=[(0, 9, "그림.png")], table_paragraphs=[frozenset({1, 9})], figures=[(0, 9, "그림.png", 10, 10)],
                    styles=[names] if styles else None, aside_paragraphs=[frozenset({8})], numbers=[[None] * 11],
                    page_breaks=[frozenset({6, 10})], pictures=[(0, 9, "image1")], binaries={"image1": {"bytes": 1}})


class SplitTests(unittest.TestCase):
    def test_body_start_by_style_or_text(self):
        self.assertEqual(body_start(single_section()), 6)
        self.assertEqual(body_start(single_section(styles=False)), 6)  # '핵심 용어' 뒤 첫 '학습 1'

    def test_everything_is_reindexed(self):
        d = split_single_section(single_section())
        self.assertEqual([len(s) for s in d.sections], [6, 5])
        self.assertEqual(d.sections[1][0], "학습 1")
        self.assertEqual([(t["section"], t["paragraph"]) for t in d.tables], [(0, 1), (1, 3)])
        self.assertEqual((d.images, d.figures, d.pictures), ([(1, 3, "그림.png")], [(1, 3, "그림.png", 10, 10)], [(1, 3, "image1")]))
        self.assertEqual((d.table_paragraphs, d.aside_paragraphs, d.page_breaks), ([frozenset({1}), frozenset({3})], [frozenset(), frozenset({2})], [frozenset(), frozenset({0, 4})]))
        self.assertEqual(d.styles[1][:2], ["큰학습-숫자", "큰학습-네비게이터"])

    def test_two_section_document_is_untouched(self):
        d = Document(Path("x.hwpx"), "hwpx", [["앞"], ["뒤"]])
        self.assertIs(split_single_section(d), d)


class PatternTests(unittest.TestCase):
    def test_plan_sub_accepts_missing_period(self):
        self.assertEqual(PLAN_SUB.match("1-1 AIoT 요구사항 수집").groups(), ("1", "1", "AIoT 요구사항 수집"))
        self.assertEqual(PLAN_SUB.match("1-1. 호텔정보 구분").groups(), ("1", "1", "호텔정보 구분"))
        self.assertEqual(PLAN_SUB.match("1-1.").group(3), None)
        self.assertIsNone(PLAN_SUB.match("1-1AIoT"))
        plan = parse_plan_toc([["능력단위 코드번호", "2001021701_25v1", "1. 수집하기", "1-1 요구사항 수집", "1.1 할 수 있다.", "NCS (수정 금지)"]], "LM2001021701_25v1")
        self.assertEqual(plan["내용명"], [{"no": 1, "sub": 1, "text": "요구사항 수집"}])

    def test_toc_tail_allows_spaced_appendix(self):
        self.assertEqual(TOC_TAIL.match("부 록 67").group(2), "67")
        self.assertEqual(TOC_TAIL.match("참고 자료 57").group(1), "참고 자료")


if __name__ == "__main__":
    unittest.main()
