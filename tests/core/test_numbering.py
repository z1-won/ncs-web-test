"""hwpx 자동 번호 복원(ncs_core.numbering)과 필요 지식 ⑥의 자동·타이핑 번호 혼용 처리."""

import unittest
import xml.etree.ElementTree as ET

from ncs_core.hwpx import para_text
from ncs_core.numbering import format_number, read_definitions, render_numbers
from ncs_knowledge.rules.numbering import check_numbering

HEADER = """<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
  <hh:refList>
    <hh:numberings>
      <hh:numbering id="1" start="0">
        <hh:paraHead start="1" level="1" numFormat="DIGIT">^1.</hh:paraHead>
        <hh:paraHead start="1" level="2" numFormat="DIGIT">(^2)</hh:paraHead>
        <hh:paraHead start="1" level="3" numFormat="HANGUL_SYLLABLE">(^3)</hh:paraHead>
      </hh:numbering>
      <hh:numbering id="2" start="0">
        <hh:paraHead start="3" level="1" numFormat="CIRCLED_DIGIT">^1</hh:paraHead>
      </hh:numbering>
    </hh:numberings>
    <hh:bullets><hh:bullet id="1" char="•"/></hh:bullets>
    <hh:paraProperties>
      <hh:paraPr id="10"><hh:heading type="NUMBER" idRef="1" level="0"/></hh:paraPr>
      <hh:paraPr id="11"><hh:heading type="NUMBER" idRef="1" level="1"/></hh:paraPr>
      <hh:paraPr id="12"><hh:heading type="NUMBER" idRef="1" level="2"/></hh:paraPr>
      <hh:paraPr id="20"><hh:heading type="NUMBER" idRef="2" level="0"/></hh:paraPr>
      <hh:paraPr id="30"><hh:heading type="BULLET" idRef="1" level="0"/></hh:paraPr>
      <hh:paraPr id="40"><hh:heading type="NONE" idRef="0" level="0"/></hh:paraPr>
    </hh:paraProperties>
  </hh:refList>
</hh:head>"""


class FormatNumberTests(unittest.TestCase):
    def test_known_formats(self):
        self.assertEqual([format_number("DIGIT", 3), format_number("HANGUL_SYLLABLE", 2), format_number("CIRCLED_DIGIT", 1),
                          format_number("CIRCLED_HANGUL_JAMO", 1), format_number("CIRCLED_LATIN_SMALL", 2), format_number("ROMAN_SMALL", 4)],
                         ["3", "나", "①", "㉠", "ⓑ", "iv"])

    def test_unknown_or_overflow_falls_back_to_digits(self):
        self.assertEqual(format_number("WHATEVER", 2), "2?")
        self.assertEqual(format_number("HANGUL_SYLLABLE", 15), "15")


class RenderNumbersTests(unittest.TestCase):
    def setUp(self):
        self.defs = read_definitions(ET.fromstring(HEADER))

    def test_counts_resets_and_restarts(self):
        #  1. / (1) / (2) / (가) / 2. / (1)  — 2.가 나오면 하위 카운터는 초기화
        labels = render_numbers(["10", "11", "11", "12", "10", "11"], self.defs)
        self.assertEqual(labels, ["1.", "(1)", "(2)", "(가)", "2.", "(1)"])

    def test_separate_numbering_id_has_its_own_counter_and_start(self):
        self.assertEqual(render_numbers(["10", "20", "10", "20"], self.defs), ["1.", "③", "2.", "④"])

    def test_bullet_none_and_deleted_paragraphs(self):
        # None(변경추적으로 지워진 문단)은 번호도 없고 카운터도 올리지 않는다
        self.assertEqual(render_numbers(["30", "40", None, "10", None, "10"], self.defs), ["•", None, None, "1.", None, "2."])


class ParaTextTrackedChangesTests(unittest.TestCase):
    def test_insert_nested_inside_delete(self):
        hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
        xml = (f'<hp:p xmlns:hp="{hp}"><hp:run><hp:t>'
               '<hp:deleteBegin/>지운 글<hp:insertBegin/>새 글<hp:insertEnd/> 지운 꼬리<hp:deleteEnd/>남은 글'
               '</hp:t></hp:run></hp:p>')
        self.assertEqual(para_text(ET.fromstring(xml)), "새 글남은 글")


class CheckNumberingWithAutoNumbersTests(unittest.TestCase):
    """본문 줄: (문단 인덱스, 텍스트). 자동 번호는 numbers[문단 인덱스]로 들어온다."""

    def run_unit(self, lines, numbers, styles=None):
        body = {"lines": [(0, "학습 1"), (1, "1-1. 제목")] + lines, "spans": [(1, 0, len(lines) + 2)], "subs": []}
        unit = {"no": 1, "sub": 1, "text": "제목", "k0": 1, "k1": len(lines) + 2, "lesson": 1, "goal": [], "goal_k": None}
        [row] = check_numbering(body, [unit], frozenset(), numbers, styles)
        return row

    def test_style_only_first_level_heading_restarts_numbering_and_is_flagged(self):
        """연회관리 원고: 두 번째 󰊱 제목이 스타일만 있고 기호가 없다 → 아래 '1.'은 새 목록(연번 X 아님), 기호 누락만 지적."""
        lines = [(2, "\U000F02B1 첫 제목"), (3, "1. 가"), (4, "2. 나"), (5, "둘째 제목"), (6, "1. 다"), (7, "2. 라")]
        styles = ["바탕글"] * 5 + ["\U000F02B1제목", "1.제목", "1.제목"]
        without = self.run_unit(lines, None)
        self.assertEqual(without["체크"]["같은 수준 연번"], "X")  # 스타일을 모르면 '1. 다'가 3이어야 한다고 본다
        row = self.run_unit(lines, None, styles)
        self.assertEqual(row["체크"]["같은 수준 연번"], "O")
        self.assertEqual(row["체크"]["\U000F02B1 기호 표시"], "X")
        self.assertIn("둘째 제목", row["비고"]["\U000F02B1 기호 표시"])

    def test_mixed_auto_and_typed_numbers_pass_together(self):
        lines = [(2, "\U000F02B1 큰 제목"), (3, "자동 1."), (4, "자동 (1)"), (5, "(2) 타이핑"), (6, "자동 2.")]
        numbers = [None, None, None, "1.", "(1)", None, "2."]
        row = self.run_unit(lines, numbers)
        self.assertEqual(row["판정"], "적합", row["비고"])
        self.assertEqual(row["원고"], "번호 문단 5개")

    def test_typed_only_view_would_fail_but_auto_fixes_it(self):
        lines = [(2, "\U000F02B1 큰 제목"), (3, "자동 1."), (4, "(2) 타이핑")]
        self.assertEqual(self.run_unit(lines, None)["판정"], "부적합")  # hwp처럼 자동 번호가 안 보이면 (2)만 보여 X
        self.assertIn("자동 번호", self.run_unit(lines, None)["비고"])
        self.assertEqual(self.run_unit(lines, [None, None, None, "1.", None])["판정"], "부적합")  # 자동 번호를 봐도 (1) 없이 (2)

    def test_hwp_without_any_first_level_symbol_is_undecided(self):
        """AIoT 원본(hwp): 󰊱 제목이 자동 번호라 텍스트에 안 보이고 '1.'부터 보인다 → 시작·건너뜀·연번을 판정하지 않는다(△)."""
        lines = [(2, "1. 가"), (3, "2. 나"), (4, "(1) 다"), (5, "1. 라")]
        row = self.run_unit(lines, None)
        self.assertEqual(row["판정"], "판단불가", row["비고"])
        self.assertIn("󰊱 기호도 없음", row["비고"]["자동 번호"])
        # hwpx(자동 번호를 봄)면 같은 줄이 그대로 X
        self.assertEqual(self.run_unit(lines, [None, None, None, None, None, None])["판정"], "부적합")

    def test_empty_auto_numbered_paragraph_is_reported(self):
        # 문단 3은 본문 줄 목록에 없음(빈 문단)인데 자동 번호 (2)가 달려 있다
        lines = [(2, "\U000F02B1 큰 제목"), (4, "(3) 셋째")]
        numbers = [None, None, None, "(2)", None]
        row = self.run_unit(lines, numbers)
        self.assertEqual(row["체크"]["빈 번호 문단"], "X")
        self.assertIn("p3 (2)", row["비고"]["빈 번호 문단"])


if __name__ == "__main__":
    unittest.main()
