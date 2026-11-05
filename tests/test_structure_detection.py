"""양식 의존 경계를 줄이는 합성 원고 회귀 검사. 실제 기관 원고 성능 평가는 별도로 필요하다."""

import unittest
from pathlib import Path

from ncs_core.documents import Document, body_start, normalize_sections
from ncs_core.manuscript import parse_body
from ncs_core.manuscript.structure import detect_body_boundary


def document(sections, **kwargs):
    return Document(Path("variant.hwpx"), "hwpx", sections, **kwargs)


FRONT = ["차례", "학습 1. 고객 응대", "1-1. 문의 확인 3", "학습모듈의 개요"]
BODY = ["학습 1", "고객 응대", "1-1. 문의 확인", "학습 목표", "문의 내용을 확인할 수 있다.", "필요 지식"]


class StructureDetectionTests(unittest.TestCase):
    def test_no_known_style_or_front_end_marker(self):
        source = document([FRONT + BODY])
        self.assertEqual(body_start(source), len(FRONT))
        normalized = normalize_sections(source)
        self.assertEqual(normalized.sections, [FRONT, BODY])
        parsed = parse_body(normalized.sections, 1)
        self.assertEqual(parsed["lessons"][0]["subs"][0]["text"], "문의 확인")

    def test_goal_in_table_supplies_context(self):
        lines = FRONT + ["학습 1", "고객 응대", "1-1. 문의 확인", "목표 표"]
        source = document([lines], tables=[{
            "section": 0, "paragraph": 7, "rows": 1, "cols": 2,
            "cells": {(0, 0): "학 습 목 표", (0, 1): "문의 내용을 확인할 수 있다."},
        }])
        self.assertEqual(body_start(source), 4)

    def test_searches_beyond_section_after_toc_and_merges_body(self):
        source = document([["표지"], FRONT, ["추가 개요"], BODY, ["평가", "평가 내용"]],
                          images=[(4, 1, "evaluation.png")],
                          page_breaks=[frozenset(), frozenset(), frozenset(), frozenset({0}), frozenset({0})])
        normalized = normalize_sections(source)
        self.assertEqual(normalized.sections, [["표지"] + FRONT + ["추가 개요"], BODY + ["평가", "평가 내용"]])
        self.assertEqual(normalized.images, [(1, len(BODY) + 1, "evaluation.png")])
        self.assertEqual(normalized.page_breaks, [frozenset(), frozenset({0, len(BODY)})])
        self.assertIs(normalize_sections(normalized), normalized)

    def test_toc_name_mismatch_does_not_prevent_detection(self):
        source = document([["차례", "학습 1. 다른 이름", "학습모듈의 개요"] + BODY])
        self.assertEqual(body_start(source), 3)

    def test_toc_and_plan_like_table_are_not_body(self):
        source = document([FRONT + BODY], table_paragraphs=[frozenset(range(4, 10))])
        self.assertIsNone(body_start(source))
        self.assertIs(normalize_sections(source), source)

    def test_aside_is_not_body(self):
        source = document([FRONT + BODY], aside_paragraphs=[frozenset(range(4, 10))])
        self.assertIsNone(body_start(source))

    def test_weak_candidate_stays_unresolved(self):
        source = document([FRONT + ["학습 1", "고객 응대", "일반 문장"]])
        self.assertIsNone(body_start(source))
        self.assertIs(normalize_sections(source), source)

    def test_does_not_borrow_goal_from_evaluation(self):
        source = document([FRONT + ["학습 1", "고객 응대", "1-1. 문의 확인", "평가", "학습 목표"]])
        self.assertIsNone(detect_body_boundary(source))

    def test_mismatched_sub_number_stays_unresolved(self):
        source = document([FRONT + ["학습 1", "고객 응대", "2-1. 문의 확인", "학습 목표"]])
        self.assertIsNone(detect_body_boundary(source))

    def test_reports_original_boundary_and_evidence(self):
        source = document([["표지"], FRONT + BODY])
        boundary = detect_body_boundary(source)
        self.assertEqual((boundary.section, boundary.paragraph), (1, 4))
        self.assertIn("학습 목표", boundary.evidence)

    def test_style_and_front_marker_do_not_turn_aside_into_body(self):
        source = document([FRONT + ["핵심 용어"] + BODY],
                          styles=[[""] * 5 + ["큰학습-숫자"] + [""] * 5],
                          aside_paragraphs=[frozenset(range(5, 11))])
        self.assertIsNone(detect_body_boundary(source))

    def test_empty_document_is_unchanged(self):
        source = document([])
        self.assertIs(normalize_sections(source), source)


if __name__ == "__main__":
    unittest.main()
