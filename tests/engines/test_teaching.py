"""F02 교수·학습 방법 ①~④: 블록 분할과 네 규칙. 실데이터(호텔 예약 모듈) 구조를 본뜬 문단 목록으로 검사한다."""

import unittest

from ncs_teaching.blocks import split_teaching_blocks
from ncs_teaching.rules.counts import check_counts
from ncs_teaching.rules.sentences import check_sentences


def manuscript():
    """학습 1(정상), 학습 2(교수 2개·학습 방법 종결 위반), 학습 3(소제목 없음). 반환 (문단, 스타일, 자동 글머리, 표 안, 메모)"""
    rows = [  # (텍스트, 스타일, 자동 글머리, 표안?, 메모?)
        ("학습 1", "작은학습-숫자", None, False, False),
        ("1-1.", "1-1-숫자", None, True, False), ("호텔정보 구분", "작은학습-내용제목", None, True, False),
        ("수행 순서", "재료,기기,안전", None, False, False), ("• 수행 문장은 세지 않는다.", "•불릿기호-내용", None, False, False),
        ("교수⋅학습 방법", "작은학습-제목", None, False, False),
        ("교수 방법", "작은학습-내용제목", None, False, False),
        ("• 객실 종류를 설명한다.", "•불릿기호-내용", None, False, False),
        ("응대 기법을 지도한다.", "•불릿기호-내용", "•", False, False),          # 자동 글머리(텍스트에 • 없음)
        ("• 자료를 제시한다.", "•불릿기호-내용", None, False, False),
        ("1:1 매칭 제시 원칙 / 보완 or 컨펌 要", "바탕글", None, False, False),  # 에디터 메모 — 제외
        ("학습 방법", "작은학습-내용제목", None, False, False),
        ("• 용어를 숙지한다.", "•불릿기호-내용", None, False, False),
        ("• 매뉴얼로 훈련한다.", "•불릿기호-내용", None, False, False),
        ("• 제안하는 법을 배운다.", "•불릿기호-내용", None, False, False),       # -ㄴ다 동사 → O
        ("• 표 안 문장은 세지 않는다.", "•불릿기호-내용", None, True, False),
        ("평가", "작은학습-제목", None, False, False),
        ("학습 2", "작은학습-숫자", None, False, False),
        ("교수·학습 방법", "작은학습-제목", None, False, False),
        ("교수 방법", "작은학습-내용제목", None, False, False),
        ("• 약어를 설명한다.", "•불릿기호-내용", None, False, False),
        ("• 실습을 지도한다", "•불릿기호-내용", None, False, False),             # 마침표 없음
        ("글머리 없는 보충 설명 문단", "바탕글", None, False, False),           # 기타 문단
        ("학습 방법", "작은학습-내용제목", None, False, False),
        ("• 약어 숙지", "•불릿기호-내용", None, False, False),                   # 명사형
        ("• 기능을 학습한다.", "•불릿기호-내용", None, False, False),
        ("• 용어를 이해한다.", "•불릿기호-내용", None, False, False),
        ("평가", "작은학습-제목", None, False, False),
        ("학습 3", "작은학습-숫자", None, False, False),
        ("교수･학습 방법", "작은학습-제목", None, False, False),
        ("• 소제목 없이 바로 쓴 항목", "•불릿기호-내용", None, False, False),
        ("평가", "작은학습-제목", None, False, False),
    ]
    texts = [r[0] for r in rows]
    styles = [r[1] for r in rows]
    numbers = [r[2] for r in rows]
    tables = frozenset(i for i, r in enumerate(rows) if r[3])
    aside = frozenset(i for i, r in enumerate(rows) if r[4])
    return texts, styles, numbers, tables, aside


class BlockTests(unittest.TestCase):
    def test_blocks_per_lesson_with_items(self):
        texts, styles, numbers, tables, aside = manuscript()
        blocks = split_teaching_blocks(texts, styles=styles, numbers=numbers, table_paragraphs=tables, aside_paragraphs=aside)
        self.assertEqual([b["block_id"] for b in blocks], ["학습 1 교수·학습 방법", "학습 2 교수·학습 방법", "학습 3 교수·학습 방법"])
        self.assertEqual([len(b["교수"]) for b in blocks], [3, 2, 0])
        self.assertEqual([len(b["학습"]) for b in blocks], [3, 3, 0])
        self.assertEqual([p["text"] for p in blocks[1]["기타 문단"]], ["글머리 없는 보충 설명 문단"])
        self.assertEqual(blocks[2]["소제목 누락"], ["교수", "학습"])

    def test_without_styles_or_numbers_text_bullets_still_count(self):
        texts, _, _, tables, aside = manuscript()
        blocks = split_teaching_blocks(texts, table_paragraphs=tables, aside_paragraphs=aside)
        self.assertEqual(len(blocks[0]["교수"]), 2, "자동 글머리 문단은 hwp에서 보이지 않는다")

    def test_no_head_gives_no_blocks(self):
        self.assertEqual(split_teaching_blocks(["학습 1", "필요 지식", "• 아무 것"]), [])


class RuleTests(unittest.TestCase):
    def setUp(self):
        texts, styles, numbers, tables, aside = manuscript()
        self.blocks = split_teaching_blocks(texts, styles=styles, numbers=numbers, table_paragraphs=tables, aside_paragraphs=aside)

    def test_counts(self):
        rows = check_counts(self.blocks, "교수")
        self.assertEqual([r["판정"] for r in rows], ["적합", "부적합", "부적합"])
        self.assertEqual([r["위치"] for r in rows], ["학습 1", "학습 2", "학습 3"])
        self.assertIn("2개 — 3개 이상", rows[1]["비고"]["① 교수 방법 3개 이상"])
        self.assertIn("글머리 없는 문단", "".join(rows[1]["비고"]))
        self.assertIn("찾지 못함", rows[2]["비고"]["① 교수 방법 3개 이상"])
        self.assertEqual([r["판정"] for r in check_counts(self.blocks, "학습")], ["적합", "적합", "부적합"])
        self.assertTrue(all(r["item_id"] == "F02-교수학습-③" for r in check_counts(self.blocks, "학습")))

    def test_sentences(self):
        teach = check_sentences(self.blocks, "교수")
        self.assertEqual([r["판정"] for r in teach], ["적합", "부적합", "부적합"])
        self.assertEqual([v["사유"] for v in teach[1]["위반_문단"]], ["마침표 없음"])
        learn = check_sentences(self.blocks, "학습")
        self.assertEqual([r["판정"] for r in learn], ["적합", "부적합", "부적합"])
        self.assertEqual(learn[1]["위반_문단"][0]["문장"], "• 약어 숙지")
        self.assertEqual(learn[0]["item_id"], "F02-교수학습-④")

    def test_no_blocks_are_undecided(self):
        for rows in (check_counts([], "교수"), check_sentences([], "학습")):
            self.assertEqual([r["판정"] for r in rows], ["판단불가"])


if __name__ == "__main__":
    unittest.main()
