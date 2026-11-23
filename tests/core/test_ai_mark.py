"""AI 활용 줄 읽기(ncs_core.ai_mark) — 두 자료형(figures.AiMark, source_line.AiMarker)이 같은 규칙으로 같은 줄을 읽는가."""

import unittest
from datetime import date

from ncs_core import ai_mark
from ncs_core.figures import parse_ai_mark
from ncs_core.source_line import parse_ai_marker

LINES = [
    "ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.",
    "Gemini를 활용하여 생성함.",
    "ChatGPT 6.0을 활용하여 생성함. 2026. 2. 30.",                       # 달력에 없는 날
    "출처: 집필진 제작(2026) Notebook LM을 활용하여 생성함",               # 출처 줄에 붙여 쓴 것
    "Claude를 활용하여 수정 보완함. 2026. 11. 3. [그림 1-2] 구성도",       # 캡션이 뒤에 붙은 것
    "Midjourney를 활용하여 생성 함. 2025. 12. 31.",                       # '함' 앞을 띈 것
]


class AiMarkTests(unittest.TestCase):
    def test_both_views_read_the_same_lines_the_same_way(self):
        for line in LINES:
            mark, marker, found = parse_ai_mark(line), parse_ai_marker(line), ai_mark.read(line)
            self.assertIsNotNone(found, line)
            self.assertEqual((mark.tool, mark.mode, mark.on), (found.tool, found.mode, found.on), line)
            self.assertEqual((marker.tool, marker.action, marker.date, marker.raw), (found.tool, found.action, found.date_text, line), line)

    def test_fields(self):
        found = ai_mark.read(LINES[0])
        self.assertEqual((found.tool, found.mode, found.action, found.on, found.date_text),
                         ("ChatGPT", "modified", "수정 보완", date(2026, 7, 20), "2026.7.20."))
        impossible = ai_mark.read(LINES[2])
        self.assertEqual((impossible.tool, impossible.on, impossible.date_text), ("ChatGPT 6.0", None, "2026.2.30."))   # 적힌 글은 남는다
        self.assertEqual(ai_mark.read(LINES[1]).date_text, None)

    def test_ordinary_sentences_are_not_marks(self):
        for line in ("생성형 AI를 활용하여 원고를 작성하는 방법을 설명한다.", "출처: 집필진 제작(2026)", ""):
            self.assertIsNone(ai_mark.read(line), line)
            self.assertIsNone(parse_ai_mark(line))
            self.assertIsNone(parse_ai_marker(line))


if __name__ == "__main__":
    unittest.main()
