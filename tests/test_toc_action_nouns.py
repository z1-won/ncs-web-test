"""F02 차례 ②: 머리어 추출과 (2)~(5) 판정. 사전 API는 가짜 resolver로 대신해 네트워크를 쓰지 않는다."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ncs_core.lexicon import ACTION_NOUNS_FILE, REJECTED_FILE, ActionNounLexicon, default_lexicon
from ncs_toc.rules.action_nouns import check_toc2, head_word, unknown_words

DATA = Path(__file__).resolve().parents[1] / "src" / "ncs_core" / "data"


def fake_resolver(answers: dict):
    calls = []

    def resolve(word):
        calls.append(word)
        return answers.get(word, (None, "조회 실패(테스트)"))

    resolve.calls = calls
    return resolve


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


class LexiconJudgeTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="ncs_lexicon_"))
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / ACTION_NOUNS_FILE).write_text("# 테스트\n분석\tmanual\t2026-11-01\t초기\n", encoding="utf-8")

    def test_listed_word_is_pass_without_lookup(self):
        resolver = fake_resolver({})
        lexicon = ActionNounLexicon(self.dir, resolver)
        self.assertEqual(lexicon.judge("분석"), ("O", None))
        self.assertEqual(resolver.calls, [])

    def test_dictionary_hit_is_recorded_and_pass(self):
        resolver = fake_resolver({"구분": (True, "'구분-하다' 동사 표제어(target_code 1)")})
        lexicon = ActionNounLexicon(self.dir, resolver)
        self.assertEqual(lexicon.judge("구분")[0], "O")
        self.assertEqual(lexicon.judge("구분")[0], "O")
        self.assertEqual(resolver.calls, ["구분"], "두 번째는 목록에서 바로 답한다")
        self.assertIn("구분\tstdict", (self.dir / ACTION_NOUNS_FILE).read_text(encoding="utf-8"))
        self.assertIn("구분", ActionNounLexicon(self.dir).words, "다른 프로세스가 다시 읽어도 남아 있다")

    def test_dictionary_miss_is_fail_and_recorded(self):
        resolver = fake_resolver({"기초": (False, "표준국어대사전에 '기초하다' 동사 표제어 없음")})
        lexicon = ActionNounLexicon(self.dir, resolver)
        value, note = lexicon.judge("기초")
        self.assertEqual(value, "X")
        self.assertIn("기초", note)
        self.assertEqual(lexicon.judge("기초")[0], "X")
        self.assertEqual(resolver.calls, ["기초"])
        self.assertIn("기초\tstdict", (self.dir / REJECTED_FILE).read_text(encoding="utf-8"))

    def test_lookup_failure_is_undecided_not_fail_and_not_recorded(self):
        resolver = fake_resolver({})
        lexicon = ActionNounLexicon(self.dir, resolver)
        value, note = lexicon.judge("구성")
        self.assertEqual(value, "△")
        self.assertIn("구성", note)
        self.assertFalse((self.dir / REJECTED_FILE).exists())
        self.assertEqual(lexicon.judge("구성")[0], "△", "실패는 기록하지 않으므로 다음에 다시 묻는다")

    def test_no_resolver_means_undecided(self):
        lexicon = ActionNounLexicon(self.dir, None)
        value, note = lexicon.judge("구성")
        self.assertEqual(value, "△")
        self.assertIn("인증키", note)

    def test_manual_add_overrides_rejection(self):
        lexicon = ActionNounLexicon(self.dir, fake_resolver({"코딩": (False, "없음")}))
        self.assertEqual(lexicon.judge("코딩")[0], "X")
        lexicon.add("코딩", "manual", "외래어, 실무 통용")
        self.assertEqual(lexicon.judge("코딩")[0], "O")


class RuleRowTests(unittest.TestCase):
    TOC = {"내용": [
        {"no": 1, "sub": 1, "text": "현행 시스템 분석", "page": "3"},
        {"no": 1, "sub": 2, "text": "호텔정보 구분", "page": "7"},
        {"no": 2, "sub": 1, "text": "HTML 기초", "page": "9"},
        {"no": 2, "sub": 2, "text": "환경 구성", "page": "11"},
    ]}

    def lexicon(self):
        directory = Path(tempfile.mkdtemp(prefix="ncs_lexicon_"))
        self.addCleanup(shutil.rmtree, directory)
        (directory / ACTION_NOUNS_FILE).write_text("분석\tmanual\t2026-11-01\t초기\n", encoding="utf-8")
        return ActionNounLexicon(directory, fake_resolver({"구분": (True, "t 1"), "기초": (False, "없음")}))

    def test_rows_follow_steps_two_to_five(self):
        rows = check_toc2(self.TOC, self.lexicon())
        self.assertEqual([r["판정"] for r in rows], ["적합", "적합", "부적합", "판단불가"])
        self.assertEqual([r["머리어"] for r in rows], ["분석", "구분", "기초", "구성"])
        self.assertTrue(all(r["item_id"] == "F02-차례-②" for r in rows))
        self.assertIsNotNone(rows[2]["수정 제안"])
        self.assertEqual(unknown_words(rows), ["구성"])

    def test_no_content_names_gives_single_undecided_row(self):
        rows = check_toc2({"내용": []}, self.lexicon())
        self.assertEqual([r["판정"] for r in rows], ["판단불가"])


class PackagedLexiconTests(unittest.TestCase):
    def test_packaged_list_loads(self):
        words = ActionNounLexicon(DATA).words
        self.assertGreaterEqual(len(words), 100)
        self.assertTrue(all(" " not in w and "\t" not in w for w in words))

    def test_default_lexicon_has_no_resolver_without_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STDICT_API_KEY", None)
            import ncs_core.lexicon as module
            module._default = None
            self.assertIsNone(default_lexicon().resolver)
            module._default = None


if __name__ == "__main__":
    unittest.main()
