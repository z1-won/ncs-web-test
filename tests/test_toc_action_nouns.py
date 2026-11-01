"""F02 차례 ② 행동명사 종결: 머리어 추출과 O/△ 판정. 목록은 테스트 안에서 직접 준다."""

import unittest

from ncs_core import O, TRI
from ncs_core.lexicon import action_nouns
from ncs_toc.rules.action_nouns import check_toc2, classify, head_word, unknown_words

LEXICON = frozenset({"분석", "정의", "확인", "관리", "설계"})


class HeadWordTests(unittest.TestCase):
    def test_last_token_after_space(self):
        self.assertEqual(head_word("현행 시스템 분석"), "분석")

    def test_strips_trailing_note_and_punctuation(self):
        self.assertEqual(head_word("데이터베이스 설계(실습)"), "설계")
        self.assertEqual(head_word("요구사항 정의."), "정의")

    def test_list_markers_split_and_last_piece_is_head(self):
        self.assertEqual(head_word("데이터 수집·정리"), "정리")
        self.assertEqual(head_word("분석 및 설계"), "설계")
        self.assertEqual(head_word("설치/구성"), "구성")
        self.assertEqual(head_word("하드웨어와 소프트웨어 구성"), "구성")

    def test_single_token_is_itself(self):
        self.assertEqual(head_word("안전관리"), "안전관리")


class ClassifyTests(unittest.TestCase):
    def test_listed_word_is_pass(self):
        self.assertEqual(classify("분석", LEXICON), (O, None))

    def test_unlisted_word_is_undecided_with_reviewer_note(self):
        value, note = classify("구성", LEXICON)
        self.assertEqual(value, TRI)
        self.assertIn("구성", note)
        self.assertNotIn("scripts", note, "확인서 비고는 검수자용 문장이어야 한다")

    def test_verb_form_and_compound_are_undecided_not_pass(self):
        """정책: 목록에 없으면 모두 △. 동사형('정의하기')도 복합어('안전관리')도 사람이 본다."""
        for word in ("정의하기", "안전관리", "작성함", "기초"):
            with self.subTest(word=word):
                self.assertEqual(classify(word, LEXICON)[0], TRI)

    def test_empty_word(self):
        self.assertEqual(classify("", LEXICON)[0], TRI)


class RuleRowTests(unittest.TestCase):
    TOC = {"내용": [
        {"no": 1, "sub": 1, "text": "현행 시스템 분석", "page": "3"},
        {"no": 1, "sub": 2, "text": "요구사항 정의하기", "page": "7"},
        {"no": 2, "sub": 1, "text": "환경 구성", "page": "9"},
    ]}

    def test_one_row_per_content_name(self):
        rows = check_toc2(self.TOC, LEXICON)
        self.assertEqual([r["판정"] for r in rows], ["적합", "판단불가", "판단불가"])
        self.assertTrue(all(r["item_id"] == "F02-차례-②" for r in rows))
        self.assertEqual(rows[1]["region_path"], "section0 > 차례 > 1-2")
        self.assertEqual(rows[1]["머리어"], "정의하기")

    def test_unknown_words_collected_for_diagnostics(self):
        self.assertEqual(unknown_words(check_toc2(self.TOC, LEXICON)), ["구성", "정의하기"])

    def test_no_content_names_gives_single_undecided_row(self):
        rows = check_toc2({"내용": []}, LEXICON)
        self.assertEqual([r["판정"] for r in rows], ["판단불가"])
        self.assertEqual(unknown_words(rows), [])


class PackagedLexiconTests(unittest.TestCase):
    def test_packaged_list_loads(self):
        words = action_nouns()
        self.assertGreaterEqual(len(words), 100)
        self.assertTrue(all(" " not in w and "\t" not in w for w in words))


if __name__ == "__main__":
    unittest.main()
