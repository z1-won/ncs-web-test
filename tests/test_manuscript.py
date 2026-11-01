"""ncs_core.manuscript 구조 파서의 경계 사례. hwpx 없이 문단 목록으로 직접 검사한다."""

import unittest

from ncs_core.manuscript import parse_body, parse_toc

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


if __name__ == "__main__":
    unittest.main()
