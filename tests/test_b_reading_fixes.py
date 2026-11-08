"""B 엔진 읽기 수정(2026-11-05) — SW제품기획 최종본 10종에서 사람이 통과시켰는데 엔진이 잘못 읽어 X·△가 나던 경우를 작게 재현한다.
각 수정마다 '진짜 위반은 여전히 잡는지'도 함께 본다."""

import unittest
from pathlib import Path
from types import SimpleNamespace

from ncs_evaluation.region import eval_head
from ncs_evaluation.rules.feedback import ENRICHMENT, REMEDIAL
from ncs_misc.config import CheckConfig
from ncs_misc.rules.page_starts import check_page_starts
from ncs_perform.blocks import split_perform_blocks
from ncs_references.entries import collect_entries, find_short_reference_run


class EvalHeadTests(unittest.TestCase):
    def test_picks_head_followed_by_criteria(self):
        """한 학습에 '평가' 문단이 둘(표 칸 등)이면 뒤에 '평가 준거'가 오는 쪽(0402·0407)."""
        paragraphs = ["평가", "표 칸", "", "", "", "평가", "평가 준거", "• 평가자는 …"]
        body = {"lines": [(0, "평가"), (5, "평가")]}
        self.assertEqual(eval_head({"eval": [0, 1]}, body, paragraphs), 1)
        self.assertEqual(eval_head({"eval": [0]}, body, paragraphs), 0)
        # 둘 다 '평가 준거'가 따르거나 아무도 안 따르면 정하지 않는다(△ 유지)
        self.assertIsNone(eval_head({"eval": [0, 1]}, body, ["평가", "평가 준거", "", "", "", "평가", "평가 준거"]))
        self.assertIsNone(eval_head({"eval": [0, 1]}, body, ["평가", "", "", "", "", "평가", ""]))


class MethodTableHeadTests(unittest.TestCase):
    def test_method_table_with_short_head_counts_but_is_flagged(self):
        """머리 칸이 '평가'인 평가 방법 표(0407 학습 5) — 표로 세어 '표 수 불일치'는 내지 않고, 머리 표기는 △(체크리스트 밖·최종본에 있음)."""
        from ncs_evaluation.region import table_kind
        from ncs_evaluation.rules.methods import check_methods
        short = {"paragraph": 30, "cells": {(0, 0): "학습 내용", (0, 1): "평가", (0, 2): "성취수준", (2, 0): "투입 자원 관리", (2, 1): "- 계획 수립 능력"}}
        self.assertEqual(table_kind(short)[0], "평가 방법(머리 '평가')")
        region = {"lesson": 5, "found": True, "methods": [{"name": "A"}, {"name": "B"}, {"name": "C"}], "method_tables": 3,
                  "odd_method_heads": [30], "notes": []}
        [row] = check_methods([region])
        self.assertEqual(row["판정"], "판단불가")
        self.assertEqual(row["체크"]["방법별 표 머리"], "△")
        self.assertNotIn("방법별 표 수", row["체크"])
        # 표가 실제로 모자라면 여전히 X
        [row] = check_methods([{**region, "method_tables": 2, "odd_method_heads": []}])
        self.assertEqual(row["판정"], "부적합")


class PerformHeadTests(unittest.TestCase):
    def test_table_column_head_is_not_a_block(self):
        """본문 표 열 제목 '수행 내용'(게시자/구독자 표)은 블록이 아니다(0408)."""
        paragraphs = ["1-1. 요구사항 분석", "수행 내용", "게시자", "지식의 등록", "구독자", "열람",
                      "수행 내용", "요구사항 분석하기", "재료·자료", "• 명세서", "기기(장비·공구)", "• 컴퓨터",
                      "안전·유의 사항", "• 보안 준수", "수행 순서", "\U000f02b1 요구사항을 분석한다."]
        blocks = split_perform_blocks(paragraphs, table_paragraphs=frozenset({1, 2, 3, 4, 5}))
        self.assertEqual([b["title"] for b in blocks], ["요구사항 분석하기"])
        self.assertEqual(blocks[0]["소제목 누락"], [])

    def test_real_head_inside_frame_is_kept(self):
        """진짜 머리가 틀(표) 안에 있어도 뒤에 소제목이 오면 블록이다 — 제목이 틀리면 ①이 여전히 잡는다."""
        paragraphs = ["1-1. 분석", "수행 내용", "/", "요구사항 분석", "재료·자료", "• 명세서", "수행 순서", "\U000f02b1 분석."]
        blocks = split_perform_blocks(paragraphs, table_paragraphs=frozenset({1, 2, 3}))
        self.assertEqual([b["title"] for b in blocks], ["요구사항 분석"])


class FeedbackWordsTests(unittest.TestCase):
    def test_remedial_and_enrichment_phrases_from_finals(self):
        for text in ("학습 내용 중 이해가 어려운 부분에 대해서는 구체적인 사례를 제시하고",
                     "개발비용 분석에 어려움을 느낄 경우 직접비를 조사하게 한다",
                     "평가 결과 일정 점수 이하인 학생들은 추가 학습 후 재시험"):
            self.assertTrue(REMEDIAL.search(text), text)
        self.assertTrue(ENRICHMENT.search("브랜드명 기획을 잘 수행하는 경우 평판을 조사하여 발표하도록 지도한다"))
        # 심화 내용이 없는 피드백은 여전히 못 찾는다(△ 유지 — 체크리스트가 심화를 직접 요구)
        self.assertIsNone(ENRICHMENT.search("성취도가 낮은 학생에게는 핵심 사항을 구체적으로 설명해 준다."))


class MiscEvalHeadTests(unittest.TestCase):
    def test_only_real_eval_head_is_checked(self):
        """기타 ①: '평가' 표 칸은 머리가 아니다(0407)."""
        body = ["학습 1", "글", "평가", "칸", "", "평가", "평가 준거", "• …"]
        manuscript = SimpleNamespace(format="hwpx", sections=[["학습모듈의 개요"], body],
                                     section_page_breaks=lambda i: frozenset({0}) if i == 0 else frozenset({0, 5}),
                                     section_table_paragraphs=lambda i: frozenset())
        context = SimpleNamespace(manuscript=manuscript, config=CheckConfig(), body={"lessons": [{"no": 1, "raw_span": (0, 8)}]},
                                  presence={})
        heads = [(r["원고"]["머리"], r["원고"]["문단"], r["판정"]) for r in check_page_starts(context)]
        self.assertIn(("평가", 5, "적합"), heads)
        self.assertNotIn(("평가", 2, "부적합"), heads)


class ShortReferenceRunTests(unittest.TestCase):
    def test_two_entries_without_title_are_found(self):
        """제목이 이미지이고 항목이 2개뿐(0404) — 코어 기준(3개)에 못 미쳐도 엔진 보조 탐색으로 찾는다."""
        body = ["4. 평가자 체크리스트", "- 부족한 부분을 설명해 준다.", "", "∙이강만(2012). 『소프트웨어 제품 마케팅』. 삼보아트.",
                "∙프로그램심의조정위원회(2005). 『알기 쉬운 소프트웨어 라이선스』.", "비용 분석표"]
        found = find_short_reference_run(body, in_table=frozenset({0, 1, 5}))
        self.assertEqual((found["k"], found["end"]), (3, 4))
        self.assertEqual(len(collect_entries(body, {"참고 자료": found})), 2)
        # 서지처럼 생긴 줄이 하나뿐이면 찾지 않는다
        self.assertIsNone(find_short_reference_run(["글", "∙이강만(2012). 『책』. 삼보아트.", "글"]))


class OverviewAfterTocTests(unittest.TestCase):
    def test_example_overview_before_toc_is_ignored(self):
        """'NCS학습모듈의 이해' 쪽의 예시 개요(촬영 구성안…)가 아니라 차례 뒤 실제 개요를 읽는다."""
        from ncs_core.documents import load_document
        from ncs_evaluation.pipeline import _after_toc
        fixture = next((Path(__file__).resolve().parent / "fixtures").glob("원고_ok_*.hwpx"))
        document = load_document(fixture)
        trimmed = _after_toc(document, 0)
        self.assertEqual(len(trimmed.sections[0]), len(document.sections[0]))  # 문단 번호는 그대로
        toc = next(i for i, t in enumerate(document.sections[0]) if t.replace(" ", "") == "차례")
        self.assertTrue(all(t == "" for t in trimmed.sections[0][:toc]))


if __name__ == "__main__":
    unittest.main()
