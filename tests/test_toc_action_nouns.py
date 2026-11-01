"""F02 차례 ② 행동명사 종결 규칙의 3단 판정. 목록은 테스트 안에서 직접 준다(패키지 목록 변화에 흔들리지 않게)."""

import unittest

from ncs_core import O, TRI, X
from ncs_core.lexicon import action_nouns, non_action_nouns
from ncs_toc.rules.action_nouns import check_toc2, classify, last_word

LEXICON = frozenset({"분석", "정의", "확인", "관리", "포함"})
REJECTED = frozenset({"역할", "환경"})


class LastWordTests(unittest.TestCase):
    def test_last_word_strips_parenthetical_and_punctuation(self):
        self.assertEqual(last_word("현행 시스템 분석"), "분석")
        self.assertEqual(last_word("데이터베이스 설계(실습)"), "설계")
        self.assertEqual(last_word("요구사항 정의."), "정의")
        self.assertEqual(last_word("안전관리"), "안전관리")


class ClassifyTests(unittest.TestCase):
    def test_lexicon_word_is_pass(self):
        self.assertEqual(classify("분석", LEXICON, REJECTED)[0], O)

    def test_compound_falls_back_to_tail(self):
        value, note, used = classify("안전관리", LEXICON, REJECTED)
        self.assertEqual((value, used), (O, "관리"))
        self.assertIn("복합어", note)

    def test_rejected_word_is_fail(self):
        self.assertEqual(classify("역할", LEXICON, REJECTED)[0], X)

    def test_clear_verb_ending_is_fail(self):
        for word in ("정의하기", "분석한다", "확인하는", "처리되는", "작성되기"):
            with self.subTest(word=word):
                self.assertEqual(classify(word, LEXICON, REJECTED)[0], X)

    def test_ambiguous_ending_is_undecided_not_fail(self):
        """함·됨·것·다는 정상 명사(포함·결함)와 겹치므로 X가 아니라 △."""
        for word in ("작성함", "완료됨", "하는것", "사다리"):
            with self.subTest(word=word):
                self.assertEqual(classify(word, LEXICON, REJECTED)[0], TRI)

    def test_lexicon_beats_ambiguous_ending(self):
        self.assertEqual(classify("포함", LEXICON, REJECTED)[0], O)

    def test_unknown_word_is_undecided_with_guidance(self):
        value, note, _ = classify("구성", LEXICON, REJECTED)
        self.assertEqual(value, TRI)
        self.assertIn("build_action_nouns", note)


class RuleRowTests(unittest.TestCase):
    def test_one_row_per_content_name_with_item_id(self):
        toc = {"내용": [
            {"no": 1, "sub": 1, "text": "현행 시스템 분석", "page": "3"},
            {"no": 1, "sub": 2, "text": "요구사항 정의하기", "page": "7"},
            {"no": 2, "sub": 1, "text": "환경 구성", "page": "9"},
        ]}
        rows = check_toc2(toc, LEXICON, REJECTED)
        self.assertEqual([r["판정"] for r in rows], ["적합", "부적합", "판단불가"])
        self.assertTrue(all(r["item_id"] == "F02-차례-②" for r in rows))
        self.assertEqual(rows[1]["region_path"], "section0 > 차례 > 1-2")
        self.assertEqual(rows[1]["마지막 어절"], "정의하기")
        self.assertIsNotNone(rows[1]["수정 제안"])

    def test_no_content_names_gives_single_undecided_row(self):
        rows = check_toc2({"내용": []}, LEXICON, REJECTED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["판정"], "판단불가")


class PackagedLexiconTests(unittest.TestCase):
    def test_packaged_lists_load_and_do_not_overlap(self):
        yes, no = action_nouns(), non_action_nouns()
        self.assertTrue(yes, "행동명사 목록이 비어 있습니다")
        self.assertFalse(yes & no, f"두 목록에 같은 단어가 있습니다: {sorted(yes & no)}")
        self.assertTrue(all(" " not in w and "\t" not in w for w in yes | no))


if __name__ == "__main__":
    unittest.main()
