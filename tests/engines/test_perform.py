"""F02 수행 내용 ①·④: 블록 분할과 두 규칙. 실데이터(호텔 예약 모듈) 구조를 본뜬 문단 목록으로 검사한다."""

import unittest

from ncs_core import visible
from ncs_perform.blocks import split_perform_blocks
from ncs_perform.rules.sentences import check_perform_sentences, judge_sentence
from ncs_perform.rules.title import check_perform_title

BOX = "\U000F02B1"  # 󰊱


def manuscript():
    """두 학습 내용, 세 수행 내용 블록. 반환: (문단, 스타일, 표 안 인덱스, 메모 인덱스)"""
    rows = [
        # (텍스트, 스타일, 표안?, 메모?)
        ("1-1.", "1-1-숫자", True, False), ("전화 예약 접수", "작은학습-내용제목", True, False),
        ("학습 목표", "학습목표-내용", True, False),
        ("필요 지식", "필요지식 수행내용-제목", True, False),
        (BOX + " 전화 응대의 기본", BOX + "제목", False, False),  # 필요 지식의 네모 제목 — 명사형이 정상, ④ 대상 아님
        ("수행 내용 1", "필요지식 수행내용-제목", True, False), ("/", "바탕글", True, False),
        ("객실 전화 예약 접수하기", "필요지식 수행내용-부제목", True, False),
        ("재료‧자료", "재료,기기,안전", False, False), ("• 객실 요금표", "•불릿기호-내용", False, False),
        ("기기(장비‧공구)", "재료,기기,안전", False, False), ("• 전화기", "•불릿기호-내용", False, False),
        ("안전‧유의 사항", "재료,기기,안전", False, False), ("• 전화를 세 번 안에 받는다.", "•불릿기호-내용", False, False),
        ("수행 순서", "재료,기기,안전", False, False),
        (BOX + " 전화 수신 시 기본 응대 절차를 숙지한다.", BOX + "제목", False, False),
        ("수행 문장은 “~한다”로 종결 원칙", "바탕글", False, True),  # 에디터 메모 — 제외
        ("1. 전화벨이 2~3회 울릴 때 수신한다.", "1.제목", False, False),
        ("2. 매뉴얼에 따라 응대한다,", "1.제목", False, False),  # 하위 번호 쉼표 종결 — 범위 밖(Q5)
        (BOX + " 예약 정보를 기록한다", BOX + "제목", False, False),  # 마침표 없음 → X
        ("수행 tip", "수행팁-제목", True, False), ("상자 안 문장은 보지 않는다", "수행팁-내용", True, False),
        ("수행 내용 2", "필요지식 수행내용-제목", True, False), ("/", "바탕글", True, False),
        ("객실 상품 파악", "필요지식 수행내용-부제목", True, False),  # '~하기' 아님 → ① X
        ("재료‧자료", "재료,기기,안전", False, False), ("• 요금표", "•불릿기호-내용", False, False),
        ("기기(장비‧공구)", "재료,기기,안전", False, False), ("• PMS", "•불릿기호-내용", False, False),
        ("안전‧유의 사항", "재료,기기,안전", False, False), ("• 유의한다.", "•불릿기호-내용", False, False),
        ("수행 순서", "재료,기기,안전", False, False),
        (BOX + " 상품 종류를 확인한다).", BOX + "제목", False, False),  # 괄호 뒤 마침표 → O + 비고
        (BOX + " 요금 제도를 정리하기", BOX + "제목", False, False),  # 명사형 종결 → X ('안다.' 같은 -ㄴ다 동사는 O)
        ("1-2.", "1-1-숫자", True, False), ("상품 판매", "작은학습-내용제목", True, False),
        ("수행 내용", "필요지식 수행내용-제목", True, False), ("/", "바탕글", True, False),
        ("패키지 상품 판매하기", "필요지식 수행내용-부제목", True, False),
        ("재료‧자료", "재료,기기,안전", False, False), ("• 안내문", "•불릿기호-내용", False, False),
        ("기기(장비‧공구)", "재료,기기,안전", False, False), ("• 단말기", "•불릿기호-내용", False, False),
        ("수행 순서", "재료,기기,안전", False, False),  # 안전 소제목 누락
        (BOX + " 패키지 구성을 설명한다.", BOX + "제목", False, False),
        (BOX + " 가격은 정책에 따라 결정된다.", BOX + "제목", False, False),
        (BOX + " 이것은 참고 사항이다.", BOX + "제목", False, False),  # '~이다.' → △
        ("교수·학습 방법", "큰학습-네비게이터", False, False),
    ]
    texts = [r[0] for r in rows]
    styles = [r[1] for r in rows]
    tables = frozenset(i for i, r in enumerate(rows) if r[2])
    aside = frozenset(i for i, r in enumerate(rows) if r[3])
    return texts, styles, tables, aside


class BlockSplitTests(unittest.TestCase):
    def setUp(self):
        texts, styles, tables, aside = manuscript()
        self.blocks = split_perform_blocks(texts, styles=styles, table_paragraphs=tables, aside_paragraphs=aside)

    def test_blocks_units_titles_and_numbers(self):
        self.assertEqual([b["block_id"] for b in self.blocks],
                         ["학습 내용 1-1 > 수행 내용 1", "학습 내용 1-1 > 수행 내용 2", "학습 내용 1-2 > 수행 내용"])
        self.assertEqual([b["title"] for b in self.blocks], ["객실 전화 예약 접수하기", "객실 상품 파악", "패키지 상품 판매하기"])
        self.assertEqual([b["unit_title"] for b in self.blocks], ["전화 예약 접수", "전화 예약 접수", "상품 판매"])
        self.assertEqual([b["perform_no"] for b in self.blocks], [1, 2, None])

    def test_subheads_and_exclusions(self):
        first = self.blocks[0]
        self.assertEqual([x["text"] for x in first["재료"]], ["객실 요금표"])
        self.assertEqual(first["소제목 누락"], [])
        texts = [s["text"] for s in first["수행순서"]]
        self.assertNotIn("수행 문장은 “~한다”로 종결 원칙", texts, "메모 문단은 제외")
        self.assertNotIn("상자 안 문장은 보지 않는다", texts, "표 안(수행 tip) 문단은 제외")
        self.assertEqual([s["text"] for s in first["수행순서"] if s["level1"]],
                         [BOX + " 전화 수신 시 기본 응대 절차를 숙지한다.", BOX + " 예약 정보를 기록한다"])
        self.assertEqual(self.blocks[2]["소제목 누락"], ["안전"])

    def test_knowledge_section_box_heading_is_not_a_perform_line(self):
        for block in self.blocks:
            self.assertNotIn("전화 응대의 기본", [s["text"] for s in block["수행순서"]])

    def test_level1_by_first_glyph_when_styles_missing(self):
        texts, _, tables, aside = manuscript()
        blocks = split_perform_blocks(texts, styles=None, table_paragraphs=tables, aside_paragraphs=aside)
        self.assertEqual(sum(1 for s in blocks[0]["수행순서"] if s["level1"]), 2)


class TitleRuleTests(unittest.TestCase):
    def test_hagi_ending_and_numbering(self):
        texts, styles, tables, aside = manuscript()
        rows = check_perform_title(split_perform_blocks(texts, styles=styles, table_paragraphs=tables, aside_paragraphs=aside))
        self.assertEqual([r["판정"] for r in rows], ["적합", "부적합", "적합"])
        self.assertEqual(rows[1]["체크"]["① 제목 '~하기' 종결"], "X")
        self.assertEqual(rows[0]["체크"]["수행 내용 번호 연번"], "O")
        self.assertEqual(rows[2]["체크"]["수행 내용 번호 연번"], "-", "수행 내용이 하나면 연번은 해당 없음")

    def test_no_blocks_gives_undecided(self):
        self.assertEqual([r["판정"] for r in check_perform_title([])], ["판단불가"])


class VisibleGlyphTests(unittest.TestCase):
    def test_box_numbers_and_other_supplementary_pua_are_readable(self):
        """한컴 기호 글꼴의 보조 평면 글자는 글꼴 없는 화면에서 □로 깨지므로 결과에는 읽을 수 있는 표기로 적는다."""
        self.assertEqual(visible(BOX + " 절차를 숙지한다."), "[1] 절차를 숙지한다.")
        self.assertEqual(visible("\U000F02B5"), "[5]")
        self.assertEqual(visible("\U000F0400"), "⟨U+F0400⟩")
        self.assertEqual(visible("객실\uf09e부대시설"), "객실⟨U+F09E⟩부대시설", "기본 평면 PUA 표기는 그대로")

    def test_sheet_item_text_has_no_raw_box_glyph(self):
        """확인서 원문(f02_items)의 󰊱도 표로 나갈 때는 읽을 수 있는 표기로 바뀐다."""
        from ncs_perform.sheet import sheet
        text = next(row["체크 항목"] for row in sheet([]) if row["번호"] == "④")
        self.assertNotIn(BOX, text)
        self.assertIn("네모 번호([1])", text)

    def test_rule_output_contains_no_raw_box_glyph(self):
        texts, styles, tables, aside = manuscript()
        rows = check_perform_sentences(split_perform_blocks(texts, styles=styles, table_paragraphs=tables, aside_paragraphs=aside))
        dumped = str(rows)
        self.assertNotIn(BOX, dumped)
        self.assertIn("[1]", dumped)


class SentenceRuleTests(unittest.TestCase):
    def test_judge_sentence_cases(self):
        self.assertEqual(judge_sentence(BOX + " 절차를 숙지한다.")[0], "O")
        self.assertEqual(judge_sentence(BOX + " 서비스가 제공된다.")[0], "O")
        self.assertEqual(judge_sentence(BOX + " 종류를 확인한다).")[0], "O")
        self.assertEqual(judge_sentence(BOX + " 요금 제도가 무엇인지 안다.")[0], "O")  # -ㄴ다 현재형 동사
        self.assertEqual(judge_sentence(BOX + " 사용법을 가르친다.")[0], "O")
        self.assertEqual(judge_sentence(BOX + " 객실이 크다.")[0], "X")  # 형용사
        self.assertEqual(judge_sentence(BOX + " 참고 사항이다.")[0], "△")
        self.assertEqual(judge_sentence(BOX + " 기록한다")[0], "X")
        self.assertEqual(judge_sentence(BOX + " 응대한다,")[0], "X")
        self.assertEqual(judge_sentence(BOX + " 예약 접수")[0], "X")
        self.assertEqual(judge_sentence(BOX)[0], "X")

    def test_block_rows_and_violations(self):
        texts, styles, tables, aside = manuscript()
        rows = check_perform_sentences(split_perform_blocks(texts, styles=styles, table_paragraphs=tables, aside_paragraphs=aside))
        self.assertEqual([r["판정"] for r in rows], ["부적합", "부적합", "판단불가"])
        self.assertEqual([v["사유"] for v in rows[0]["위반 문단"]], ["마침표 없음"])
        self.assertEqual([v["체크"] for v in rows[2]["위반 문단"]], ["△"])
        self.assertTrue(all(r["item_id"] == "F02-수행-④" for r in rows))

    def test_hwp_without_styles_is_flagged(self):
        texts, _, tables, aside = manuscript()
        rows = check_perform_sentences(split_perform_blocks(texts, styles=None, table_paragraphs=tables, aside_paragraphs=aside), has_styles=False)
        self.assertEqual(rows[0]["체크"]["번호 수준 추정"], "△")


if __name__ == "__main__":
    unittest.main()
