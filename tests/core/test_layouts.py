"""여러 기관 원고(연회관리 40건)로 드러난 네 가지 — 구역 배치 정규화, 표지의 큰학습 스타일, 변경승인 계획서의 비고 열, 본문 메모 제외."""

import unittest
from pathlib import Path

from ncs_core.documents import Document, body_start, normalize_sections
from ncs_core.manuscript import parse_body, parse_plan, parse_plan_goals, parse_plan_toc
from ncs_core.manuscript.plan_table import read_module_table

FRONT = ["표지", "차 례", "학습 1. 가", "학습모듈의 개요", "핵심 용어", "용어1"]
BODY = ["학습 1", "가", "본문", "참고 자료"]
BODY_STYLES = ["큰학습-숫자", "큰학습-네비게이터", "바탕글", "바탕글"]


def doc(sections, styles=None, **extra):
    return Document(Path("x.hwpx"), "hwpx", sections, styles=styles, **extra)


class LayoutTests(unittest.TestCase):
    def test_cover_then_toc_and_body_in_one_section(self):
        """(c) 표지 / 차례+개요+본문 → 표지와 앞부분을 합치고 본문에서 나눈다."""
        cover = ["LM1203020408_19v2", "연회 행사 정산", "대분류/12"]
        d = doc([cover, FRONT + BODY], styles=[["큰학습-제목", "바탕글", "바탕글"], ["바탕글"] * 6 + BODY_STYLES],
                tables=[{"section": 1, "paragraph": 8, "rows": 1, "cols": 1, "cells": {}}], page_breaks=[frozenset(), frozenset({6})])
        n = normalize_sections(d)
        self.assertEqual([len(s) for s in n.sections], [9, 4])
        self.assertEqual(n.sections[0][:4], cover + ["표지"])
        self.assertEqual(n.sections[1][0], "학습 1")
        self.assertEqual([(t["section"], t["paragraph"]) for t in n.tables], [(1, 2)])
        self.assertEqual(n.page_breaks, [frozenset(), frozenset({0})])
        self.assertEqual(n.styles[1][0], "큰학습-숫자")

    def test_cover_then_front_then_body(self):
        """(d) 표지 / 차례+개요 / 본문 → 표지와 앞부분만 합친다."""
        d = doc([["표지"], FRONT, BODY], styles=[["바탕글"], ["바탕글"] * 6, BODY_STYLES])
        n = normalize_sections(d)
        self.assertEqual([len(s) for s in n.sections], [7, 4])
        self.assertEqual(n.sections[1], BODY)

    def test_usual_two_sections_untouched(self):
        d = doc([FRONT, BODY], styles=[["바탕글"] * 6, BODY_STYLES])
        self.assertIs(normalize_sections(d), d)

    def test_body_start_skips_cover_navigator_style(self):
        """표지의 큰학습 스타일 문단은 본문 시작이 아니다 — 차례·개요 뒤의 첫 큰학습을 찾는다."""
        d = doc([["표지 제목"] + FRONT + BODY], styles=[["큰학습-제목"] + ["바탕글"] * 6 + BODY_STYLES])
        self.assertEqual(body_start(d), 7)


def plan_document():
    """변경승인 계획서 꼴: 학습명/학습내용명/학습 목표 옆에 '비고' 열, 그 안에 '1-1. 학습내용명 변경(…)' 같은 문장."""
    cells = {
        (1, 0): "능력단위 코드번호", (1, 1): "1203020402_23v3", (1, 2): "능력단위명", (1, 3): "연회 예약 상담", (1, 5): "학습모듈명", (1, 6): "연회 예약 상담",
        (2, 0): "능력단위 정의", (2, 1): "연회 예약 상담이란 …이다.", (2, 5): "학습모듈의 목표", (2, 6): "…할 수 있다.",
        (3, 0): "코드번호 능력단위요소명", (3, 1): "수 행 준 거", (3, 5): "학습명", (3, 6): "학습내용명", (3, 7): "학 습 목 표", (3, 8): "비고",
        (4, 0): "1203020402_23v3.1 연회 고객 문의 응대하기", (4, 1): "1.1 응대할 수 있다. 1.2 전달할 수 있다.",
        (4, 5): "1. 연회 고객 문의 응대하기", (4, 6): "1-1. 고객 문의 정보 전달", (4, 7): "1.1 응대할 수 있다. 1.2 전달할 수 있다.",
        (4, 8): "변경사유: 학습 목표수 변경 1-1. 학습내용명 변경(기존 연회 상품 정보파악-> 고객문의 정보 전달) 1.1 학습목표 수 변경",
        (5, 6): "1-2. 고객 문의 응대", (5, 7): "1.3 확인 할 수 있다.", (5, 8): "학습목표 수 변경(기존1.3~1.5-> 1.4~1.5)",
    }
    # 문단 흐름(줄 단위 파서가 보는 것): 셀 문단이 순서대로 늘어선다
    lines = ["개발계획서", "능력단위 코드번호", "1203020402_23v3", "능력단위명", "연회 예약 상담", "학습모듈명", "연회 예약 상담",
             "능력단위 정의", "연회 예약 상담이란 …이다.", "학습모듈의 목표", "…할 수 있다.",
             "코드번호 능력단위요소명", "수 행 준 거", "학습명", "학습내용명", "학 습 목 표", "비고",
             "1203020402_23v3.1", "연회 고객 문의 응대하기", "1.1 응대할 수 있다.", "1.2 전달할 수 있다.",
             "1. 연회 고객 문의 응대하기", "1-1. 고객 문의 정보 전달", "1.1 응대할 수 있다.", "1.2 전달할 수 있다.",
             "변경사유: 학습 목표수 변경", "1-1. 학습내용명 변경(기존 연회 상품 정보파악-> 고객문의 정보 전달)", "1.1 학습목표 수 변경",
             "1-2. 고객 문의 응대", "1.3 확인 할 수 있다.", "학습목표 수 변경(기존1.3~1.5-> 1.4~1.5)", "NCS (수정 금지)"]
    return Document(Path("plan.hwpx"), "hwpx", [lines], tables=[{"section": 0, "paragraph": 1, "rows": 6, "cols": 9, "cells": cells}])


class PlanTableTests(unittest.TestCase):
    def test_table_reader_ignores_remarks_column(self):
        table = read_module_table(plan_document(), "LM1203020402_23v3")
        self.assertEqual(table["학습명"], ["연회 고객 문의 응대하기"])
        self.assertEqual([c["text"] for c in table["내용명"]], ["고객 문의 정보 전달", "고객 문의 응대"])
        self.assertEqual(table["내용"][(1, 1)]["goals"], ["1.1 응대할 수 있다.", "1.2 전달할 수 있다."])
        self.assertEqual(table["내용"][(1, 2)]["goals"], ["1.3 확인 할 수 있다."])
        self.assertEqual(table["요소"], [{"code": "1203020402_23v3.1", "name": "연회 고객 문의 응대하기"}])
        self.assertEqual((table["정의"], table["목표"]), ("연회 예약 상담이란 …이다.", "…할 수 있다."))

    def test_parsers_prefer_the_table(self):
        d = plan_document()
        self.assertEqual([c["text"] for c in parse_plan(d, "LM1203020402_23v3")["내용명"]], ["고객 문의 정보 전달", "고객 문의 응대"])
        self.assertEqual(parse_plan_toc(d, "LM1203020402_23v3")["학습명"], ["1. 연회 고객 문의 응대하기"])
        self.assertEqual(parse_plan_goals(d, "LM1203020402_23v3")["내용"][(1, 2)]["goals"], ["1.3 확인 할 수 있다."])
        # 줄 단위 읽기(문단 목록만 줄 때)는 비고의 문장을 내용명으로 잘못 읽는다 — 그래서 표를 먼저 본다
        self.assertEqual(len(parse_plan_toc(d.sections, "LM1203020402_23v3")["내용명"]), 3)

    def test_without_module_table_falls_back_to_lines(self):
        d = Document(Path("p.hwpx"), "hwpx", [["능력단위 코드번호", "2001021701_25v1", "1. 수집하기", "1-1 요구사항 수집", "1.1 할 수 있다.", "NCS (수정 금지)"]])
        self.assertEqual(parse_plan(d, "LM2001021701_25v1")["학습명"], ["수집하기"])


class NavigatorLessonTests(unittest.TestCase):
    """학습 1 본문이 없는 원고(연회 행사 진행): 첫 내비게이터 묶음은 학습 2다. 순서로 매기면 전부 한 칸 어긋난다."""

    NAV = ["학습 1", "청결도", "학습 2", "교육", "학습 3", "배치"]

    def body(self, first_lesson, styles):
        def block(current):
            return self.NAV + [f"{current}-1.", "내용", "학습 목표", "• 할 수 있다.", "필요 지식", "평가"]
        paragraphs = [p for current in range(first_lesson, 4) for p in block(current)]
        names = None
        if styles:
            names = []
            for current in range(first_lesson, 4):
                for i, _ in enumerate(self.NAV):
                    names.append(("큰학습-숫자" if i % 2 == 0 else "큰학습-제목") if i // 2 + 1 == current else "큰학습-네비게이터")
                names += ["바탕글"] * 6
        return paragraphs, names

    def test_hwpx_reads_the_highlighted_item(self):
        paragraphs, names = self.body(2, styles=True)
        body = parse_body([FRONT, paragraphs], 3, styles=names)
        self.assertEqual([no for no, _, _ in body["spans"]], [2, 3])
        self.assertEqual([[s["no"] for s in L["subs"]] for L in body["lessons"]], [[2], [3]])

    def test_hwp_falls_back_to_first_heading_number(self):
        paragraphs, _ = self.body(2, styles=False)
        self.assertEqual([no for no, _, _ in parse_body([FRONT, paragraphs], 3)["spans"]], [2, 3])

    def test_complete_manuscript_is_ordinal(self):
        paragraphs, names = self.body(1, styles=True)
        self.assertEqual([no for no, _, _ in parse_body([FRONT, paragraphs], 3, styles=names)["spans"]], [1, 2, 3])


class AsideTests(unittest.TestCase):
    def test_parse_body_skips_memo_paragraphs(self):
        body = ["학습 1", "가", "1-1.", "고객 문의 정보 전달", "학습 목표", "(개발계획서에 따라)", "학습 목표 수정 要", "• 응대할 수 있다.", "필요 지식"]
        with_memo = parse_body([FRONT, body], 1, aside_paragraphs=frozenset({5, 6}))
        self.assertEqual([t for _, t in with_memo["lines"]][4:6], ["학습 목표", "• 응대할 수 있다."])
        without = parse_body([FRONT, body], 1)
        self.assertEqual(len(without["lines"]), len(with_memo["lines"]) + 2)


if __name__ == "__main__":
    unittest.main()


class FakeTocTests(unittest.TestCase):
    """'차례' 제목이 두 번 나오는 원고(앞에 깨진 자동 차례가 남아 '차 례' 뒤에 쪽수 숫자만 있음) — 학습 줄이 따르는 차례를 골라야 한다."""

    def test_toc_title_index_prefers_the_one_followed_by_lessons(self):
        from ncs_core.documents import toc_title_index

        paragraphs = ["[NCS-학습모듈의 위치]", "차 례", "ㆍ222222", "232323", "", "차 례", "학습모듈의 개요 1",
                      "학습 1. 요구사항 수집하기", "1-1. 수집 3"]
        self.assertEqual(toc_title_index(paragraphs), 5)
        self.assertEqual(toc_title_index(["차례", "학습 1. 가"]), 0)
        self.assertEqual(toc_title_index(["차례", "숫자만"]), 0, "학습 줄이 따르는 차례가 없으면 첫 차례")
        self.assertIsNone(toc_title_index(["본문"]))

    def test_parse_toc_skips_the_broken_first_toc(self):
        from ncs_core.manuscript.toc import parse_toc

        front = ["차 례", "ㆍ222222", "232323", "차 례", "학습 1. 요구사항 수집하기", "1-1. 요구사항 수집 3", "• 평가 5",
                 "참고 자료 46", "AIoT 학습모듈의 개요"]
        toc = parse_toc([front, []])
        self.assertEqual([l["text"] for l in toc["학습"]], ["요구사항 수집하기"])
