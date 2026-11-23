"""기타 '법령'(F02에 없는 추가 항목): 원고에 적힌 법령 이름의 현행화 대상 후보 — 정의서 V0.23 REQ-02-002 사람 작업 3 '법령 용어 현행화 후보를 확인한다'."""

import unittest
from types import SimpleNamespace

from ncs_core.law_catalog import LawEntry, law_names_in
from ncs_misc.rules.laws import CHECKED, LABEL, check_manuscript_laws


class Laws:
    def __init__(self, *entries):
        self.entries = {entry.written.replace(" ", ""): entry for entry in entries}

    def lookup(self, name):
        return self.entries.get(name.replace(" ", ""))


def entry(written, status, name="", current=""):
    return LawEntry(written, name or written, "1", "20240101", "일부개정", status, current, "2026-11-01")


def context(*paragraphs):
    return SimpleNamespace(manuscript=SimpleNamespace(sections=[[], list(paragraphs)]))


class LawNameTests(unittest.TestCase):
    def test_ordinary_words_are_not_laws(self):
        text = "「관광진흥법」과 근로기준법 시행령을 따른다. 궁중 조리법과 현장 대처법은 법령이 아니다."
        self.assertEqual(law_names_in(text, None), ["관광진흥법", "근로기준법 시행령"])
        self.assertEqual(law_names_in("현장 대처법을 익힌다.", Laws(entry("현장 대처법", "현행"))), ["현장 대처법"])     # 표에서 찾은 이름은 법령이다


class ManuscriptLawTests(unittest.TestCase):
    def test_renamed_and_repealed_are_candidates_never_x(self):
        laws = Laws(entry("전기사업법", "현행"), entry("전기통신기본법", "명칭변경", current="방송통신발전 기본법"), entry("증기기관법", "폐지"))
        [row] = check_manuscript_laws(context("「전기사업법」에 따른다.", "「전기통신기본법」과 「증기기관법」을 본다."), laws)
        self.assertEqual((row["item_id"], row["체크"][LABEL], row["판정"]), ("F02-기타-법령", "△", "판단불가"))
        note = row["비고"][LABEL]
        self.assertIn("원고 「전기통신기본법」 — 현행 명칭 「방송통신발전 기본법」", note)
        self.assertIn("원고 「증기기관법」 — 폐지", note)
        self.assertNotIn("전기사업법", note)
        self.assertIn("내용 전문가", note)                      # 바꿀지는 수행준거 준용 범위와 내용 전문가 판단(F04 2-2)
        self.assertNotIn("X", row["체크"].values())

    def test_spacing_differs_from_official_name(self):
        laws = Laws(entry("개인정보보호법", "현행", name="개인정보 보호법"))
        [row] = check_manuscript_laws(context("개인정보보호법을 지킨다."), laws)
        self.assertEqual(row["체크"][LABEL], "△")
        self.assertIn("원고 「개인정보보호법」 / 법제처 정식 명칭 「개인정보 보호법」 — 띄어쓰기만 다름", row["비고"][LABEL])

    def test_all_current_no_law_and_unknown(self):
        laws = Laws(entry("전기사업법", "현행"))
        [row] = check_manuscript_laws(context("「전기사업법」에 따른다."), laws)
        self.assertEqual((row["체크"], row["판정"]), ({LABEL: "O", CHECKED: "O"}, "적합"))
        [row] = check_manuscript_laws(context("법령 이름이 없는 글이다."), laws)
        self.assertEqual(row["체크"], {LABEL: "-"})
        [row] = check_manuscript_laws(context("「전기사업법」과 「도시가스사업법」을 본다."), laws)      # 표에 없는 이름은 확인하지 못한 것 — 적합이 아니다
        self.assertEqual((row["체크"][LABEL], row["체크"][CHECKED]), ("O", "△"))
        self.assertIn("원고 「도시가스사업법」", row["비고"][CHECKED])
        [row] = check_manuscript_laws(context("「전기사업법」에 따른다."), None)                  # 법령명 표가 없음
        self.assertEqual(row["판정"], "판단불가")


if __name__ == "__main__":
    unittest.main()
