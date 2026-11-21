"""원고 분량 산정(ncs_volume, REQ-02-013): 줄 배치 읽기(hwpx·hwp 레코드), 구성 나누기, ½쪽 규칙, 변경 행, 추정 경로, CLI.

hwpx는 줄 배치(linesegarray)를 넣은 합성 원고를 만들어 쓰고, hwp는 레코드 바이트를 직접 만들어 해석기만 검사한다.
실제 원고(samples/, git 제외)로 돌린 결과는 README의 원고 분량 단락에 적는다.
"""

import contextlib
import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from ncs_volume import DEFAULT_CONFIG, VolumeConfig, manual_check, measure, round_half_up, tally
from ncs_volume.__main__ import main
from ncs_volume.diff import changed_lines
from ncs_volume.layout import Layout, Line, Unit, hwp_paragraphs, read_layout
from ncs_volume.segments import assign

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
PITCH = 1980        # 본문 줄 간격(1,100 + 880)
BODY = DEFAULT_CONFIG.body_height


def seg(vertpos, textpos=0, vertsize=1100, spacing=880):
    return f'<hp:lineseg textpos="{textpos}" vertpos="{vertpos}" vertsize="{vertsize}" spacing="{spacing}"/>'


def para(text, segs, inner=""):
    return f'<hp:p><hp:run><hp:t>{escape(text)}</hp:t>{inner}</hp:run><hp:linesegarray>{"".join(segs)}</hp:linesegarray></hp:p>'


class Page:
    """쪽 하나를 위에서부터 채우는 도우미 — 줄마다 vertpos를 PITCH씩 내린다."""

    def __init__(self):
        self.v, self.parts = 0, []

    def text(self, text, lines=1):
        per = max(1, len(text) // lines)
        self.parts.append(para(text, [seg(self.v + k * PITCH, k * per) for k in range(lines)]))
        self.v += lines * PITCH
        return self

    def table(self, rows, height):
        cells = "".join(
            "<hp:tr>" + "".join(f'<hp:tc><hp:subList>{para(t, [seg(0)])}</hp:subList><hp:cellAddr rowAddr="{r}" colAddr="{c}"/></hp:tc>'
                                for c, t in enumerate(row)) + "</hp:tr>"
            for r, row in enumerate(rows))
        self.parts.append(para("", [seg(self.v, vertsize=height - 880)], f"<hp:tbl>{cells}</hp:tbl>"))
        self.v += height
        return self

    def picture(self, height, caption=None):
        inner = f"<hp:caption><hp:subList>{para(caption, [seg(0)])}</hp:subList></hp:caption>" if caption else ""
        self.parts.append(para("", [seg(self.v, vertsize=height - 880)], f"<hp:pic>{inner}</hp:pic>"))
        self.v += height
        return self


def hwpx(path: Path, pages: list[Page]) -> Path:
    body = "".join(part for page in pages for part in page.parts)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", f'<?xml version="1.0" encoding="UTF-8"?><hp:sec xmlns:hp="{HP}">{body}</hp:sec>')
    return path


def manuscript(body_lines=20, extra_body="", tail_change=False) -> list[Page]:
    """표지 → 위치 → 차례 → 개요 → 학습 1(필요 지식·수행 내용) → 교수·학습 방법 → 평가 → 참고 자료(배너 그림) → 개발 이력."""
    cover = Page().text("2026 NCS학습모듈 표지").text("교육부")
    position = Page().table([["[NCS-학습모듈의 위치]"]], 4 * PITCH).text("대분류 정보통신", 3)
    toc = Page().table([["차  례"]], 3 * PITCH).text("학습모듈의 개요 1").text("학습 1. 요구사항 확인하기 2").text("참고 자료 30").text("", 1)
    overview = Page().table([["요구사항 확인 학습모듈의 개요"]], 3 * PITCH).text("학습모듈의 목표", 1).text("요구사항을 확인할 수 있다.", 2)
    lesson = Page().table([["학습 1", "요구사항 확인하기", "학습 2", "화면 구현하기"]], 5 * PITCH).table([["필요 지식", "/"]], 2 * PITCH)
    lesson.text("현행 시스템 분석의 개념" + extra_body, body_lines)
    lesson.picture(8 * PITCH, caption="[그림 1-1] 시스템 구성도")
    perform = Page().table([["수행 내용", "/", "현행 시스템 분석하기"]], 2 * PITCH).text("현행 시스템을 분석한다.", 26)
    teaching = Page().table([["학습 1", "교수·학습 방법"]], 3 * PITCH).text("교수 방법", 10)
    evaluation = Page().table([["학습 1", "평  가"]], 3 * PITCH).table([["학습 내용", "평가 항목"], ["현행 시스템 분석", "분석할 수 있다"]], 4 * PITCH)
    references = Page().picture(4 * PITCH).text("교육부(2024). 「안내서」." + (" 개정" if tail_change else ""), 2)
    colophon = Page().table([["NCS학습모듈 개발이력", "발행일"], ["ISBN", "979-11"]], 10 * PITCH)
    return [cover, position, toc, overview, lesson, perform, teaching, evaluation, references, colophon]


class Tally(unittest.TestCase):
    def test_round_half_up_is_contract_half_page_rule(self):
        self.assertEqual([round_half_up(v) for v in (0.49, 0.5, 1.5, 2.49)], [0, 1, 2, 2])

    def layout(self, measured=True):
        return Layout(Path("x"), "hwpx", measured, [], 0, 34, PITCH)

    def test_half_page_rule_applies_to_the_remainder_only(self):
        """끝수에만 본다(2026-11-21 결정): 전체 행 ÷ 쪽당 행 수. 쪽마다 본 값은 '쪽마다 기준'에 비교용으로 남는다."""
        half = [Line(1, PITCH, 0, k * PITCH, 0, 0) for k in range(18)]          # 18 × 1980 = 35,640 ≥ ½쪽
        less = [Line(1, PITCH, 1, k * PITCH, 0, 0) for k in range(10)]
        out = tally(half + less, self.layout(), DEFAULT_CONFIG)
        self.assertEqual((out["쪽"], out["행"], out["행 합계"]), (0, 28, 28))
        self.assertEqual(out["기입 분량"], 1)                                    # 28/34 = 0.82 → 1
        self.assertEqual(out["쪽마다 기준"], {"쪽": 1, "행": 10})
        few = tally(less, self.layout(), DEFAULT_CONFIG)                         # 10/34 = 0.29 → 0
        self.assertEqual((few["쪽"], few["행"], few["기입 분량"]), (0, 10, 0))

    def test_readings_show_how_the_half_page_rule_changes_the_count(self):
        from ncs_volume.pipeline import readings
        half = [Line(1, PITCH, 0, k * PITCH, 0, 0) for k in range(18)]
        less = [Line(1, PITCH, p, k * PITCH, 0, 0) for p in (1, 2, 3) for k in range(16)]     # ½ 미만인 쪽 셋(16행씩)
        out = tally(half + less, self.layout(), DEFAULT_CONFIG)
        spread = readings(out, self.layout())
        # 전체 행 66 ÷ 34 = 1.94 → 2(산정), 높이 환산, 쪽마다 기준 1쪽 + 48행 환산(1.41 → 1) = 2, ½ 미만 쪽 버림 1
        self.assertEqual([row["기입 분량"] for row in spread["행"]], [2, 2, 2, 1])
        self.assertIn("지금 산정", spread["행"][0]["해석"])
        self.assertEqual(spread["행"][0]["기입 분량"], out["기입 분량"])
        self.assertEqual((spread["최소"], spread["최대"], spread["차이"]), (1, 2, 1))
        self.assertIsNone(readings(out, self.layout(measured=False)))

    def test_tall_table_spills_onto_next_pages(self):
        table = Line(40, BODY * 2, 3, 0, 0, 0)                                   # 두 쪽짜리 표
        out = tally([table], self.layout(), DEFAULT_CONFIG)
        self.assertEqual(out["쪽마다 기준"]["쪽"], 2)
        self.assertEqual(out["쪽 환산"], 2.0)

    def test_estimate_divides_lines_by_lines_per_page(self):
        lines = [Line(1, PITCH, -1, 0, 0, 0)] * 85
        out = tally(lines, self.layout(measured=False), DEFAULT_CONFIG)
        self.assertEqual((out["쪽"], out["행"], out["기입 분량"]), (2, 17, 3))   # 85/34 = 2.5 → ½ 이상 올림

    def test_manual_check_reports_error_rate(self):
        self.assertEqual(manual_check(80, 80, DEFAULT_CONFIG)["결과"], "기준 충족")
        result = manual_check(81, 80, DEFAULT_CONFIG)
        self.assertEqual((result["오차율"], result["결과"]), ("1.25%", "기준 초과"))
        with self.assertRaises(ValueError):
            manual_check(80, 0, DEFAULT_CONFIG)


class HwpxLayout(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = hwpx(Path(self.folder.name) / "원고.hwpx", manuscript())

    def test_reads_pages_lines_and_segments(self):
        layout = read_layout(self.path)
        self.assertTrue(layout.measured)
        self.assertEqual(layout.pages, 10)
        self.assertEqual(layout.lines_per_page, BODY // PITCH)
        _, found = assign(layout.blocks)
        self.assertEqual(found, ["NCS-학습모듈의 위치", "차례", "학습모듈의 개요", "학습 — 필요 지식", "학습 — 수행 내용",
                                 "교수·학습 방법", "평가", "참고 자료", "개발진(개발 이력·판권)"])

    def test_picture_is_excluded_but_caption_counts(self):
        layout = read_layout(self.path)
        picture = next(b for b in layout.blocks if b.kind == "picture" and b.has_caption)
        self.assertEqual(sum(line.count for unit in picture.units for line in unit.lines), 1)
        self.assertAlmostEqual(picture.visual, 7 * PITCH)

    def test_table_rows_and_text_lines(self):
        layout = read_layout(self.path)
        evaluation_table = [b for b in layout.blocks if b.kind == "table" and b.head.startswith("학습 내용")][0]
        self.assertEqual([u.text for u in evaluation_table.units], ["학습 내용 | 평가 항목", "현행 시스템 분석 | 분석할 수 있다"])
        body = next(b for b in layout.blocks if b.head.startswith("현행 시스템 분석의 개념"))
        self.assertEqual(len(body.units[0].lines), 20)

    def test_measure_counts_only_contract_segments(self):
        result = measure(self.path)
        rows = {row["구성"]: row for row in result["구성"]}
        self.assertFalse(rows["표지"]["반영"])
        self.assertFalse(rows["개발진(개발 이력·판권)"]["반영"])
        counted = sum(row["행"] for row in result["구성"] if row["반영"])
        self.assertEqual(result["합계"]["행 합계"], counted)
        # 쪽: 위치(5행)·차례·개요는 ½쪽 미만, 학습 1(필요 지식 20행+표+그림)·수행 내용(28행)은 ½쪽 이상
        self.assertEqual(result["합계"]["쪽"], 2)
        self.assertFalse(result["추정"])
        self.assertEqual(result["권고 분량"]["상태"], "권고보다 적음")
        self.assertIn("찾지 못한 구성(원고에 없거나 제목을 읽지 못함): 활용 서식, 부록", result["알림"])

    def test_banner_picture_starts_tail_in_toc_order(self):
        layout = read_layout(self.path)
        names, _ = assign(layout.blocks)
        banner = next(i for i, b in enumerate(layout.blocks) if b.kind == "picture" and not b.has_caption)
        self.assertEqual(names[banner], "참고 자료")
        self.assertEqual(names[banner - 1], "평가")

    def test_exclude_appendix_option(self):
        self.assertFalse(VolumeConfig(include_appendix=False).counted("부록"))
        self.assertTrue(DEFAULT_CONFIG.counted("부록"))
        result = measure(self.path, config=VolumeConfig(include_appendix=False))
        self.assertTrue(any("부록을 산정에서 뺐습니다" in note for note in result["알림"]))

    def test_compare_with_previous_counts_changed_lines_only(self):
        same = measure(self.path, previous=self.path)["변경"]
        self.assertEqual(same["변경 행"], 0)
        edited = hwpx(Path(self.folder.name) / "새 원고.hwpx", manuscript(extra_body="와 범위", tail_change=True))
        change = measure(edited, previous=self.path)["변경"]
        by = {row["구성"]: row["변경 행"] for row in change["구성별 변경 행"]}
        self.assertEqual(by.get("참고 자료"), 1)        # 둘째 줄 끝에 ' 개정'을 붙임 → 그 줄 하나
        self.assertGreaterEqual(by.get("학습 — 필요 지식", 0), 1)   # 문단 글이 바뀐 줄만(줄 위치만 밀린 줄은 아님)
        self.assertLess(by.get("학습 — 필요 지식", 0), 20)
        self.assertNotIn("평가", by)


class UnderstandingSection(unittest.TestCase):
    """'NCS학습모듈의 이해'의 양식 설명('1. NCS학습모듈의 위치', 위치 예시, '2. NCS학습모듈의 개요')을 구성 시작으로 보지 않는다."""

    @staticmethod
    def block(head, page_top=False):
        from ncs_volume.layout import Block
        return Block("text", head, head, [], 0.0, 0, page_top)

    def test_examples_inside_understanding_are_not_headings(self):
        blocks = [self.block("표지"), self.block("NCS학습모듈의 이해", True), self.block("1. NCS학습모듈의 위치"),
                  self.block("[NCS-학습모듈의 위치]"), self.block("2. NCS학습모듈의 개요"), self.block("학습2 평 가"),
                  self.block("[NCS-학습모듈의 위치]", True), self.block("차 례", True)]
        names, found = assign(blocks)
        self.assertEqual(names[2:6], ["NCS학습모듈의 이해"] * 4)
        self.assertEqual(names[6:], ["NCS-학습모듈의 위치", "차례"])
        self.assertEqual(found, ["NCS학습모듈의 이해", "NCS-학습모듈의 위치", "차례"])


class HwpRecords(unittest.TestCase):
    """hwp 본문 레코드 → 최상위 문단. 레코드 머리(태그 10비트·수준 10비트·크기 12비트)를 직접 만든다."""

    @staticmethod
    def record(tag, level, payload):
        return struct.pack("<I", tag | (level << 10) | (len(payload) << 20)) + payload

    @staticmethod
    def text(chars):
        return "".join(chars).encode("utf-16-le")

    def segs(self, *rows):
        return b"".join(struct.pack("<Ii4iiiI", textpos, vertpos, 1100, 880, 0, 880, 0, 0, 0) for textpos, vertpos in rows)

    def test_line_text_follows_textpos_with_extended_controls(self):
        # 확장 제어 문자(코드 11, 8 WCHAR) 하나 뒤에 글. 둘째 줄은 textpos 13 = 8 + 5글자부터
        control = struct.pack("<H", 11) + b"\x00" * 14
        stream = (self.record(0x42, 0, b"\x00" * 12)
                  + self.record(0x43, 1, control + self.text("가나다라마바사"))
                  + self.record(0x45, 1, self.segs((0, 0), (13, 1980))))
        paras = hwp_paragraphs(stream)
        self.assertEqual(paras[0].text, "가나다라마바사")
        self.assertEqual([s.textpos for s in paras[0].segs], [0, 5])

    def test_table_cells_become_rows(self):
        ctrl = b" lbt" + b"\x00" * 8          # 'tbl '를 뒤집어 저장
        cell = lambda col, row: self.record(0x48, 2, b"\x00" * 8 + struct.pack("<HH", col, row))
        cell_para = lambda text, lines: (self.record(0x42, 2, b"\x00" * 12) + self.record(0x43, 3, self.text(text))
                                         + self.record(0x45, 3, self.segs(*[(0, k * 1980) for k in range(lines)])))
        stream = (self.record(0x42, 0, b"\x00" * 12) + self.record(0x45, 1, self.segs((0, 0)))
                  + self.record(0x47, 1, ctrl)
                  + cell(0, 0) + cell_para("학습 내용", 1) + cell(1, 0) + cell_para("평가 항목", 1)
                  + cell(0, 1) + cell_para("분석", 1) + cell(1, 1) + cell_para("길게 쓴 칸", 3)
                  + self.record(0x42, 0, b"\x00" * 12) + self.record(0x43, 1, self.text("다음 문단")) + self.record(0x45, 1, self.segs((0, 9000))))
        paras = hwp_paragraphs(stream)
        self.assertEqual([p.kind for p in paras], ["table", "text"])
        self.assertEqual(paras[0].rows, [[("학습 내용", 1), ("평가 항목", 1)], [("분석", 1), ("길게 쓴 칸", 3)]])
        self.assertEqual(paras[1].text, "다음 문단")


class ChangedLines(unittest.TestCase):
    def unit(self, text, per):
        spans = [(k, min(k + per, len(text))) for k in range(0, len(text), per)] or [(0, 0)]
        return Unit(text, [Line(1, PITCH, 0, 0, a, b) for a, b in spans])

    def test_one_inserted_word_changes_only_its_line(self):
        old = [self.unit("가" * 30, 10)]
        new = [self.unit("가" * 15 + "나" + "가" * 15, 10)]
        changed = changed_lines(old, new)
        self.assertEqual([(line.start, line.end) for _, line in changed], [(10, 20)])

    def test_new_paragraph_counts_all_lines_and_equal_counts_none(self):
        old = [self.unit("같은 문단", 10)]
        new = [self.unit("같은 문단", 10), self.unit("완전히 새로 쓴 문단입니다 " * 3, 10)]
        changed = changed_lines(old, new)
        self.assertEqual({index for index, _ in changed}, {1})
        self.assertEqual(len(changed), len(new[1].lines))

    def test_deletion_marks_the_line_where_text_was_removed(self):
        old = [self.unit("가나다라마바사아자차카타파하", 5)]
        new = [self.unit("가나다라마사아자차카타파하", 5)]       # '바' 삭제
        changed = changed_lines(old, new)
        self.assertEqual(len(changed), 1)


class EstimatePath(unittest.TestCase):
    def test_fixture_without_layout_is_estimate_and_range_is_undecided(self):
        result = measure(FIXTURES / "원고_ok_LM1203020201_24v3.hwpx", previous=FIXTURES / "원고_name_LM1203020201_24v3.hwpx")
        self.assertTrue(result["추정"])
        self.assertEqual(result["권고 분량"]["상태"], "판단불가")
        self.assertIsNone(result["물리 쪽 수"])
        self.assertGreater(result["변경"]["변경 행"], 0)

    def test_pdf_is_rejected(self):
        with self.assertRaises(ValueError):
            measure(FIXTURES / "출력본_ok_LM1203020201_24v3.pdf")


class Cli(unittest.TestCase):
    def test_prints_table_and_saves_json(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "결과.json"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main([str(FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"), "--manual", "2", "--json", str(target)])
            self.assertEqual(code, 0)
            self.assertIn("기입 분량", buffer.getvalue())
            self.assertIn("수작업 대조", buffer.getvalue())
            self.assertTrue(target.exists())

    def test_bad_file_returns_error_code(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "x.hwp"
            bad.write_bytes(b"not a document")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
