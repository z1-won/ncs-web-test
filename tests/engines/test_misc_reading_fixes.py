"""B 엔진 읽기 수정(2026-11-05) — SW제품기획 최종본 10종에서 사람이 통과시켰는데 엔진이 잘못 읽어 X·△가 나던 경우를 작게 재현한다.
각 수정마다 '진짜 위반은 여전히 잡는지'도 함께 본다."""

import unittest
from pathlib import Path
from types import SimpleNamespace

from ncs_misc.config import CheckConfig
from ncs_misc.rules.page_starts import check_page_starts


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


if __name__ == "__main__":
    unittest.main()
