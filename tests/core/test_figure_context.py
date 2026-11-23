"""ncs_core.figure_context: 그림 자리마다 캡션·출처 줄·AI 활용 줄·참조 문장·앞뒤 문단·표 맥락·학습 번호."""

import unittest

from ncs_core.documents import Document
from ncs_core.figure_context import caption_index, figure_contexts


def record(section, para, **extra):
    base = {"section": section, "para": para, "bin_id": "BIN1", "format": "png", "px": (100, 50), "size_hwp": (7200, 3600),
            "mm": (25, 13), "dpi": 100, "caption": "", "data": b""}
    base.update(extra)
    return base


def document(body, tables=frozenset(), aside=frozenset()):
    return Document("x.hwpx", "hwpx", [["차례"], body], table_paragraphs=[frozenset(), frozenset(tables)],
                    aside_paragraphs=[frozenset(), frozenset(aside)])


class FigureContextTests(unittest.TestCase):
    BODY = [
        "1-1. 비즈니스 전략 분석",                       # 0
        "경영 전략은 <그림 1-1>과 같이 정리한다.",        # 1
        "앞 문단",                                       # 2
        "",                                              # 3 그림 자리
        "출처: 집필진 제작(2026)",                       # 4
        "ChatGPT를 활용하여 생성함. 2026. 7. 20.",       # 5
        "[그림 1-1] 경영 전략 체계",                     # 6
        "뒤 문단 하나",                                  # 7
        "뒤 문단 둘",                                    # 8
        "뒤 문단 셋",                                    # 9
    ]

    def test_caption_source_ai_and_context(self):
        [ctx] = figure_contexts(document(self.BODY), structure=None, records=[record(1, 3)])
        self.assertEqual((ctx.caption_para, ctx.figure_label, ctx.figure_title), (6, "그림 1-1", "경영 전략 체계"))
        self.assertEqual((ctx.source_para, ctx.source_line), (4, "출처: 집필진 제작(2026)"))
        self.assertEqual(ctx.ai_marker_para, 5)
        self.assertEqual(ctx.references, ("경영 전략은 <그림 1-1>과 같이 정리한다.",))
        self.assertEqual(ctx.before, ("1-1. 비즈니스 전략 분석", "경영 전략은 <그림 1-1>과 같이 정리한다.", "앞 문단"))
        self.assertEqual(ctx.after, ("뒤 문단 하나", "뒤 문단 둘"))
        self.assertEqual(ctx.lesson, 1)                       # 캡션 번호에서
        self.assertEqual(ctx.region_path, "section1 > 학습 1 > [그림 1-1]")

    def test_no_caption_in_table(self):
        body = ["표 머리 A", "표 칸 B", "", "표 칸 C", "본문"]
        [ctx] = figure_contexts(document(body, tables={0, 1, 2, 3}), structure=None, records=[record(1, 2)])
        self.assertIsNone(ctx.caption_para)
        self.assertIsNone(ctx.figure_label)
        self.assertTrue(ctx.in_table)
        self.assertEqual(ctx.table_context, ("표 머리 A", "표 칸 B", "표 칸 C"))
        self.assertEqual(ctx.region_path, "section1 > p2")

    def test_caption_index_prefers_below_then_above(self):
        self.assertEqual(caption_index(["[그림 1-1] 위", "", "[그림 1-2] 아래"], 1), 2)
        self.assertEqual(caption_index(["[그림 1-1] 위", "", "본문"], 1), 0)

    def test_aside_paragraphs_are_not_context(self):
        body = ["메모", "", "[그림 2-1] 가"]
        [ctx] = figure_contexts(document(body, aside={0}), structure=None, records=[record(1, 1)])
        self.assertEqual(ctx.before, ())


if __name__ == "__main__":
    unittest.main()
