"""ncs_core.manuscript 구조 파서의 경계 사례. hwpx 없이 문단 목록으로 직접 검사한다."""

import unittest

from ncs_core.manuscript import parse_body, parse_toc, section_presence
from ncs_toc.rules.tail import check_toc6

FRONT = [
    "차례",
    "학습 1. 요구사항 분석하기", "1-1. 현행 시스템 분석 3", "1-2. 요구사항 정의 7",
    "• 교수·학습 방법 10", "• 평가 11",
    "학습 2. 설계하기", "2-1. UI 요구사항 확인 13", "• 교수·학습 방법 15", "• 평가 16",
    "참고 자료 18",
    "학습모듈의 개요",
]


def body_lines(*, table_copy_first: bool):
    heading = "1-1. 현행 시스템 분석"
    table_copy = "1-1. 현행 시스탬 분석"  # 평가 표 셀에 오타가 있는 사본
    lesson1 = ["학습 1", "요구사항 분석하기", "학습 2", "설계하기"]  # 내비게이터
    if table_copy_first:
        lesson1 += [table_copy, heading]
    else:
        lesson1 += [heading, table_copy]
    lesson1 += ["학습 목표", "교수·학습 방법", "평가", "평가 준거"]
    lesson2 = ["학습 1", "요구사항 분석하기", "학습 2", "설계하기", "2-1. UI 요구사항 확인", "교수·학습 방법", "평가"]
    return lesson1 + lesson2 + ["참고 자료"]


class BodyHeadingTests(unittest.TestCase):
    def heading_text(self, lines, table_paragraphs):
        body = parse_body([FRONT, lines], 2, table_paragraphs=table_paragraphs)
        return [s["text"] for s in body["subs"] if (s["no"], s["sub"]) == (1, 1)]

    def test_same_number_appears_once_and_prefers_paragraph_outside_tables(self):
        lines = body_lines(table_copy_first=False)
        table_index = frozenset({lines.index("1-1. 현행 시스탬 분석")})
        self.assertEqual(self.heading_text(lines, table_index), ["현행 시스템 분석"])
        # 표 사본이 먼저 나와도 표 밖 문단을 고른다
        lines = body_lines(table_copy_first=True)
        table_index = frozenset({lines.index("1-1. 현행 시스탬 분석")})
        self.assertEqual(self.heading_text(lines, table_index), ["현행 시스템 분석"])

    def test_without_table_information_first_occurrence_wins(self):
        lines = body_lines(table_copy_first=False)
        self.assertEqual(self.heading_text(lines, None), ["현행 시스템 분석"])
        lines = body_lines(table_copy_first=True)
        self.assertEqual(self.heading_text(lines, None), ["현행 시스탬 분석"], "표 정보가 없으면(hwp) 먼저 나온 것")

    def test_last_heading_position_ignores_table_copy_after_evaluation(self):
        """④ '끝부분' 판정에 쓰는 마지막 N-M. 제목이 평가 표 안의 사본 때문에 뒤로 밀리지 않는다."""
        lines = body_lines(table_copy_first=False)
        copy_at = lines.index("1-1. 현행 시스탬 분석")
        body = parse_body([FRONT, lines], 2, table_paragraphs=frozenset({copy_at}))
        lesson1 = body["lessons"][0]
        self.assertEqual([s["k"] for s in lesson1["subs"]], [lines.index("1-1. 현행 시스템 분석")])


class TocSkippedLessonTests(unittest.TestCase):
    def test_non_consecutive_lesson_line_is_recorded_not_silently_dropped(self):
        front = ["차례", "학습 1. 분석하기", "1-1. 가 3", "학습 3. 구현하기", "3-1. 나 9", "학습모듈의 개요"]
        toc = parse_toc([front, []])
        self.assertEqual([L["no"] for L in toc["학습"]], [1])
        self.assertEqual(toc["건너뜀"], [{"no": 3, "text": "구현하기", "기대": 2}])

    def test_consecutive_lessons_have_no_skips(self):
        toc = parse_toc([FRONT, []])
        self.assertEqual([L["no"] for L in toc["학습"]], [1, 2])
        self.assertEqual(toc["건너뜀"], [])


class TailPresenceTests(unittest.TestCase):
    def presence(self, body, *, figures=(), tables=(), complete=True):
        return section_presence([[], body], [], figures=figures, tables=tables, media_complete=complete)

    def verdicts(self, presence, tail):
        return {r["region_path"].split(" > ")[-1]: r for r in check_toc6(presence, {"꼬리": tail})}

    def test_short_real_content_is_not_empty(self):
        p = self.presence(["참고 자료", "활용 서식", "예약 신청서", "성명: ___", "개발 이력"])
        self.assertIs(p["활용 서식"]["있음"], True)
        self.assertFalse(p["활용 서식"].get("배너만"))
        self.assertEqual(self.verdicts(p, {})["활용 서식"]["판정"], "부적합")

    def test_empty_banner_checks_deletion(self):
        p = self.presence(["참고 자료", "부록", "※ 안내", "개발 이력"])
        self.assertIs(p["부록"]["있음"], False)
        self.assertTrue(p["부록"]["배너만"])
        self.assertEqual(self.verdicts(p, {})["부록"]["판정"], "적합")
        row = self.verdicts(p, {"부록": "10"})["부록"]
        self.assertEqual(row["판정"], "부적합")
        self.assertEqual(row["수정 제안"], "차례에서 삭제")

    def test_image_only_content_and_blank_table_are_not_empty(self):
        body = ["참고 자료", "부록", "", "개발 이력"]
        for kwargs in ({"figures": [(2, "", 30000, 40000)]}, {"tables": [{"paragraph": 2, "cells": {}}]}):
            with self.subTest(kwargs=kwargs):
                p = self.presence(body, **kwargs)
                self.assertIs(p["부록"]["있음"], True)
                self.assertFalse(p["부록"].get("배너만"))

    def test_unknown_banner_never_assigns_a_name(self):
        body = ["참고 자료", "", "내용1", "내용2", "내용3", "개발 이력"]
        p = self.presence(body, figures=[(1, "", 45370, 3763)])
        for name in ("활용 서식", "부록"):
            self.assertIsNone(p[name]["있음"])
            self.assertIsNone(p[name]["k"])

    def test_unclassified_content_keeps_both_names_uncertain(self):
        for count in (1, 12):
            p = self.presence(["참고 자료"] + [f"내용{i}" for i in range(count)] + ["개발 이력"])
            for row in self.verdicts(p, {"부록": "10"}).values():
                self.assertEqual(row["판정"], "판단불가")
                self.assertNotEqual(row["수정 제안"], "차례에서 삭제")

    def test_content_before_appendix_is_identified_as_forms(self):
        p = self.presence(["참고 자료"] + [f"내용{i}" for i in range(12)] + ["부록", "개발 이력"])
        self.assertIs(p["활용 서식"]["있음"], True)
        self.assertIs(p["부록"]["있음"], False)

    def test_missing_media_information_prevents_absence_confirmation(self):
        p = self.presence(["참고 자료", "부록", "개발 이력"], complete=False)
        self.assertIsNone(p["부록"]["있음"])
        self.assertIsNone(p["활용 서식"]["있음"])

    def test_missing_reference_prevents_absence_confirmation(self):
        p = self.presence(["일반 본문"])
        self.assertIsNone(p["부록"]["있음"])

    def test_known_content_and_known_absence(self):
        p = self.presence(["참고 자료", "활용 서식", "내용1", "내용2", "내용3", "개발 이력"])
        self.assertIs(p["활용 서식"]["있음"], True)
        self.assertIs(p["부록"]["있음"], False)
        self.assertEqual(self.verdicts(p, {"활용 서식": "10"})["활용 서식"]["판정"], "적합")
        self.assertEqual(self.verdicts(p, {})["활용 서식"]["판정"], "부적합")

    def test_unknown_banner_after_known_forms_identifies_appendix(self):
        p = self.presence(["참고 자료", "활용 서식", "내용1", "내용2", "내용3", "", "추가 내용", "개발 이력"],
                          figures=[(5, "", 45370, 3763)])
        self.assertIs(p["활용 서식"]["있음"], True)
        self.assertIs(p["부록"]["있음"], True)

    def test_adjacent_identified_banners_without_content_are_empty(self):
        p = self.presence(["참고 자료", "활용 서식", "", "개발 이력"], figures=[(2, "", 45370, 3763)])
        self.assertIs(p["활용 서식"]["있음"], False)
        self.assertIs(p["부록"]["있음"], False)

    def test_unnamed_forms_before_named_appendix(self):
        p = self.presence(["참고 자료", "", "서식 한 문단", "부록", "부록 한 문단", "개발 이력"],
                          figures=[(1, "", 45370, 3763)])
        for name in ("활용 서식", "부록"):
            self.assertIs(p[name]["있음"], True)
            self.assertEqual(self.verdicts(p, {"활용 서식": "10", "부록": "11"})[name]["판정"], "적합")

    def test_two_unnamed_banners_follow_tail_order(self):
        p = self.presence(["참고 자료", "", "서식", "", "부록 내용", "개발 이력"],
                          figures=[(1, "", 45370, 3763), (3, "", 45370, 3763)])
        self.assertEqual(p["활용 서식"]["k"], 1)
        self.assertEqual(p["부록"]["k"], 3)
        self.assertIs(p["활용 서식"]["있음"], True)
        self.assertIs(p["부록"]["있음"], True)

    def test_extra_banner_does_not_force_assignment(self):
        p = self.presence(["참고 자료", "", "", "", "내용", "개발 이력"],
                          figures=[(i, "", 45370, 3763) for i in (1, 2, 3)])
        self.assertIsNone(p["활용 서식"]["있음"])
        self.assertIsNone(p["부록"]["있음"])

    def test_development_template_marker_is_not_appendix_content(self):
        p = self.presence(["참고 자료", "부록", "※ 안내", "<신규 개발 학습모듈 양식>", "개발 이력"])
        self.assertIs(p["부록"]["있음"], False)

    def test_development_table_is_not_appendix_content(self):
        p = self.presence(["참고 자료", "부록", "", "NCS학습모듈 개발이력", "발행일"],
                          tables=[{"paragraph": 2, "cells": {(0, 0): "NCS학습모듈 개발이력", (1, 0): "발행일"}}])
        self.assertIs(p["부록"]["있음"], False)
        self.assertEqual(self.verdicts(p, {})["부록"]["판정"], "적합")

    def test_toc_leaders(self):
        for leader in ("", "……", "···", ". . .", "⋯", "‥"):
            toc = parse_toc([["차례", f"활용 서식 {leader} 98", f"부록 {leader} 100", "학습모듈의 개요"], []])
            self.assertEqual(toc["꼬리"], {"활용 서식": "98", "부록": "100"})


class TocBrokenPageTests(unittest.TestCase):
    """쪽 칸이 숫자 대신 '?'(갱신 안 된 상호 참조)인 차례 줄. '?'는 쪽 칸이지 내용명이 아니다."""

    def toc(self, *lines):
        return parse_toc([["차례", *lines, "학습모듈의 개요"], []])

    def test_question_page_is_not_part_of_content_name(self):
        toc = self.toc("학습 1. ○○하기 1", "1-1. ○○ ○○ ○○ ?", "1-2. ○○ ○○?", "1-3. ○○ ○○ 7")
        self.assertEqual([s["text"] for s in toc["내용"]], ["○○ ○○ ○○", "○○ ○○", "○○ ○○"])
        self.assertEqual([s["page"] for s in toc["내용"]], [None, None, "7"])
        self.assertEqual(toc["쪽 깨짐"], ["1-1", "1-2"])

    def test_question_mark_before_numeric_page_stays_in_name(self):
        toc = self.toc("학습 1. ○○하기 1", "1-1. ○○인가? 12")
        self.assertEqual(toc["내용"][0]["text"], "○○인가?")
        self.assertEqual(toc["내용"][0]["page"], "12")
        self.assertEqual(toc["쪽 깨짐"], [])

    def test_numeric_and_missing_pages_unchanged(self):
        toc = self.toc("학습 1. ○○하기 1", "1-1. ○○ ○○ 3", "1-2. ○○ ○○··········9", "1-3. ○○ ○○", "• 평가52")
        self.assertEqual([(s["text"], s["page"]) for s in toc["내용"]],
                         [("○○ ○○", "3"), ("○○ ○○··········", "9"), ("○○ ○○", None)])
        self.assertEqual(toc["줄"][0]["page"], "52")
        self.assertEqual(toc["쪽 깨짐"], [])

    def test_trailing_question_without_page_is_read_as_broken_page(self):
        # 감수한 한계(사양 '달라지면 안 되는 것'): 쪽 번호 없이 내용명이 '?'로 끝나면 그 '?'는 쪽 칸으로 읽힌다.
        toc = self.toc("학습 1. ○○하기 1", "1-1. 무엇을 ○○하는가?")
        self.assertEqual(toc["내용"][0]["text"], "무엇을 ○○하는가")
        self.assertIsNone(toc["내용"][0]["page"])
        self.assertEqual(toc["쪽 깨짐"], ["1-1"])

    def test_doubled_question_mark_is_not_a_page(self):
        toc = self.toc("학습 1. ○○하기 1", "1-1. ○○??")
        self.assertEqual(toc["내용"][0]["text"], "○○??")
        self.assertEqual(toc["쪽 깨짐"], [])

    def test_lesson_line_and_tail_question_pages(self):
        toc = self.toc("학습 1. ○○하기 ?", "1-1. ○○ 3", "• 교수·학습 방법 ?", "• 평가?", "참고 자료 ?", "부록 ……?")
        self.assertEqual(toc["학습"], [{"no": 1, "text": "○○하기"}])
        self.assertEqual([(l["kind"], l["page"]) for l in toc["줄"]], [("교수·학습 방법", None), ("평가", None)])
        self.assertEqual(toc["꼬리"], {"참고 자료": None, "부록": None})
        self.assertEqual(toc["쪽 깨짐"], ["학습 1", "학습 1 교수·학습 방법", "학습 1 평가", "참고 자료", "부록"])

    def test_tail_question_page_does_not_leak_into_notes(self):
        toc = self.toc("학습 1. ○○하기 1", "1-1. ○○ 3", "참고 자료 ?", "부록 ?")
        presence = section_presence([[], ["참고 자료", "• ○○(2020). ○○."]], [], media_complete=True)
        rows = {r["region_path"].split(" > ")[-1]: r for r in check_toc6(presence, toc)}
        self.assertEqual(rows["부록"]["판정"], "부적합")
        self.assertNotIn("?", str(rows["부록"]["비고"]))
        self.assertIsNone(rows["부록"]["원고"]["차례"])

    def test_broken_pages_are_reported_in_toc_diagnostics(self):
        from types import SimpleNamespace

        from ncs_toc.config import DEFAULT_CONFIG
        from ncs_toc.pipeline import _diagnostics

        def diagnostics(toc):
            manuscript = SimpleNamespace(path="m.hwpx", format="hwpx", sections=[[], []])
            context = SimpleNamespace(manuscript=manuscript, plan=None, config=DEFAULT_CONFIG, toc=toc, plan_toc=None,
                                      body={"lessons": [1], "nav_runs": []}, eval_tables=[1], module_code="LM0")
            return [w for w in _diagnostics(context, [])["warnings"] if "쪽 번호" in w]

        broken = self.toc("학습 1. ○○하기 1", "1-1. ○○ ?", "1-2. ○○?", "1-3. ○○ 7")
        self.assertEqual(len(warnings := diagnostics(broken)), 1)
        self.assertIn("2개(1-1, 1-2)", warnings[0])
        self.assertEqual(diagnostics(self.toc("학습 1. ○○하기 1", "1-1. ○○ 3")), [])

    def test_hwpx_crossref_question_result(self):
        # 문단 = [t "1-1. 명"] [점선 탭] [CROSSREF 필드 시작] [t "?"] [필드 끝] — 한글이 상호 참조를 못 찾은 차례 줄
        from xml.etree import ElementTree as ET

        from ncs_core.hwpx import para_text

        xml = (
            '<hp:p xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:run><hp:t>1-1. ○○ ○○</hp:t>'
            '<hp:t><hp:tab leader="2"/></hp:t>'
            '<hp:ctrl><hp:fieldBegin type="CROSSREF" name="r"/></hp:ctrl><hp:t>?</hp:t>'
            '<hp:ctrl><hp:fieldEnd/></hp:ctrl></hp:run></hp:p>'
        )
        line = para_text(ET.fromstring(xml))
        toc = self.toc("학습 1. ○○하기 1", line)
        self.assertEqual(toc["내용"][0]["text"], "○○ ○○")
        self.assertEqual(toc["쪽 깨짐"], ["1-1"])


if __name__ == "__main__":
    unittest.main()
