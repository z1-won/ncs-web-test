"""NCS 분류·능력단위 목록(ncs_core.ncs_catalog)과 위치 검수의 'NCS 목록 기준' 동작."""

import os
import tempfile
import unittest
from pathlib import Path

from ncs_core import ncs_catalog
from ncs_core.ncs_catalog import Catalog
from ncs_position.rules.classification import check_classification
from ncs_position.rules.position import check_position

REAL = Path(__file__).resolve().parents[1] / "src" / "ncs_core" / "data" / "ncs_units.tsv"

SMALL = """# 테스트용
12030204\t이용\t관광\t숙박서비스\t연회관리\t\t2014\t1203020401_23v3\t연회 판촉
12030204\t이용\t관광\t숙박서비스\t연회관리\t\t2014\t1203020402_23v3\t연회 예약 상담
12030205\t이용\t관광\t숙박서비스\t접객서비스\t\t2014\t1203020501_24v3\t접객 응대
"""


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8")
        self.tmp.write(SMALL)
        self.tmp.close()
        self.cat = Catalog(Path(self.tmp.name))

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_lookups(self):
        sub = self.cat.subclass("LM1203020402_23v3")
        self.assertEqual((sub.code, sub.name, sub.names["소분류"]), ("12030204", "연회관리", "숙박서비스"))
        self.assertEqual([u.name for u in sub.units], ["연회 판촉", "연회 예약 상담"])
        self.assertEqual([s.name for s in self.cat.subclasses_of_small("1203020401_23v3")], ["연회관리", "접객서비스"])
        self.assertEqual(self.cat.unit("1203020501").name, "접객 응대")
        self.assertEqual(self.cat.unit("LM1203020501_99v9").code, "1203020501_24v3")  # 버전이 달라도 10자리로 찾는다
        self.assertIsNone(self.cat.subclass("LM9999999901_26v1"))

    def test_env_override_and_missing_file(self):
        saved = os.environ.get("NCS_CATALOG_FILE")
        try:
            os.environ["NCS_CATALOG_FILE"] = self.tmp.name
            self.assertEqual(ncs_catalog.catalog().subclass("12030205").name, "접객서비스")
            os.environ["NCS_CATALOG_FILE"] = self.tmp.name + ".missing"
            self.assertIsNone(ncs_catalog.catalog())
        finally:
            if saved is None:
                os.environ.pop("NCS_CATALOG_FILE", None)
            else:
                os.environ["NCS_CATALOG_FILE"] = saved

    @unittest.skipUnless(REAL.is_file(), "실데이터 목록 없음")
    def test_real_catalog_has_the_project_subclasses(self):
        cat = Catalog(REAL)
        self.assertEqual([u.name for u in cat.subclass("12030204").units],
                         ["연회 판촉", "연회 예약 상담", "연회 행사 진행", "웨딩 행사 준비", "출장 연회", "연회 행사 정산", "연회 행사 사후관리", "연회 행사 준비"])
        self.assertEqual(cat.subclass("20010217").name, "AIoT운영플랫폼구축")
        self.assertEqual(cat.subclass("12030202").names["대분류"], "이용·숙박·여행·오락·스포츠")


class PositionWithCatalogTests(unittest.TestCase):
    """기준이 NCS 목록일 때: 비고에 'NCS 목록'이 적히고, 개발계획서가 목록과 다르면 △로 따로 알린다."""

    REF = {"세분류": ["연회관리", "접객서비스"], "능력단위": ["연회 판촉", "연회 예약 상담"], "학습모듈명": ["연회 판촉", "연회 예약 상담"],
           "행쌍": [("연회 판촉", "연회 판촉"), ("연회 예약 상담", "연회 예약 상담")]}

    def test_manuscript_matches_catalog_but_plan_is_stale(self):
        plan = {**self.REF, "능력단위": ["연회 판촉", "연회 예약상담"], "학습모듈명": ["연회 판촉", "연회 예약상담"]}
        [row] = check_position(self.REF, self.REF, basis="NCS 목록", plan_only=plan)
        self.assertEqual(row["체크"]["③ 능력단위명 목록 일치"], "O")
        self.assertEqual(row["체크"]["개발계획서↔NCS 목록"], "△")
        self.assertIn("개발계획서 「연회 예약상담」 / NCS 목록 「연회 예약 상담」", row["비고"]["개발계획서↔NCS 목록"])

    def test_manuscript_differs_from_catalog(self):
        manuscript = {**self.REF, "능력단위": ["연회 판촉", "연회 기획"], "학습모듈명": ["연회 판촉", "연회 기획"], "행쌍": [("연회 판촉", "연회 판촉"), ("연회 기획", "연회 기획")]}
        [row] = check_position(self.REF, manuscript, basis="NCS 목록", plan_only=self.REF)
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("원고 「연회 기획」 / NCS 목록 「연회 예약 상담」", row["비고"]["③ 능력단위명 목록 일치"])
        self.assertNotIn("개발계획서↔NCS 목록", row["체크"])
        self.assertTrue(row["수정 제안"].startswith("NCS 목록의 능력단위명"))

    def test_classification_notes_name_the_basis(self):
        ref = {"대분류": "이용", "중분류": "관광", "소분류": "숙박서비스"}
        rows = check_classification(ref, {"대분류": "이용", "중분류": "관광", "소분류": "숙박 서비스"}, basis="NCS 목록",
                                    plan={"대분류": "이용", "중분류": "관광", "소분류": "숙박서비스"})
        self.assertIn("원고 「숙박 서비스」 / NCS 목록 「숙박서비스」 — 띄어쓰기만 다름", rows[2]["비고"]["① 개발계획서와 명칭 일치"])
        self.assertEqual(rows[2]["수정 제안"], 'NCS 목록대로 "숙박서비스"로 수정')
        rows = check_classification(ref, ref, basis="NCS 목록", plan={"대분류": "이용", "중분류": "관광", "소분류": "숙박 서비스"})
        self.assertEqual(rows[2]["체크"]["개발계획서↔NCS 목록"], "△")


if __name__ == "__main__":
    unittest.main()


class PrerequisiteCodeTests(unittest.TestCase):
    """개요 ③: 선수학습의 NCS 코드 병기·유효성·명칭 (실데이터 목록 사용)."""

    def setUp(self):
        self.saved = os.environ.get("NCS_CATALOG_FILE")
        os.environ["NCS_CATALOG_FILE"] = str(REAL)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("NCS_CATALOG_FILE", None)
        else:
            os.environ["NCS_CATALOG_FILE"] = self.saved

    @staticmethod
    def run_items(items, code="LM1203020408_23v3"):
        from ncs_overview.rules.prerequisite_codes import check_prerequisite_codes
        [row] = check_prerequisite_codes({"선수학습": {"items": items, "text": ", ".join(items), "p": 1}}, code)
        return row

    @unittest.skipUnless(REAL.is_file(), "실데이터 목록 없음")
    def test_subject_names_and_correct_codes_pass(self):
        row = self.run_items(["호텔 경영론", "연회 예약 상담(LM1203020402_23v3)"])
        self.assertEqual(row["판정"], "적합", row["비고"])

    @unittest.skipUnless(REAL.is_file(), "실데이터 목록 없음")
    def test_each_defect_is_named(self):
        row = self.run_items(["연회 행사 준비(1203020411_23v2)", "연회 행사 진행(LM1203020405_19v1)", "웨딩 행사 진행(LM1203020406_23v3)",
                              "연회 행사 정산(LM1203020408_23v3)", "연회 판촉"])
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("코드 꼴은 LM", row["비고"]["③ 코드 병기"])
        self.assertIn("NCS 학습모듈명인데 코드가 없음 (예: 연회 판촉(LM1203020401_23v3))", row["비고"]["③ 코드 병기"])
        self.assertIn("버전이 목록과 다름", row["비고"]["③ 코드 유효(NCS 목록)"])
        self.assertIn("자신의 코드", row["비고"]["③ 코드 유효(NCS 목록)"])
        self.assertIn("원고 「웨딩 행사 진행」 / NCS 목록 「웨딩 행사 준비」", row["비고"]["③ 명칭 일치(NCS 목록)"])

    def test_without_catalog_only_format_is_checked(self):
        os.environ["NCS_CATALOG_FILE"] = str(REAL) + ".missing"
        row = self.run_items(["연회 예약 상담(LM1203020402_23v3)", "호텔 경영론"])
        self.assertEqual(row["판정"], "판단불가")
        self.assertIn("NCS 목록", row["비고"]["③ 코드 유효(NCS 목록)"])


class PrerequisiteLevelTests(unittest.TestCase):
    """개요 ④: 선수학습 능력단위 수준 ≤ 이 모듈 수준 (실데이터 수준 표 사용)."""

    def setUp(self):
        self.saved = os.environ.get("NCS_CATALOG_FILE")
        os.environ["NCS_CATALOG_FILE"] = str(REAL)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("NCS_CATALOG_FILE", None)
        else:
            os.environ["NCS_CATALOG_FILE"] = self.saved

    @staticmethod
    def run_items(items, code="LM1203020408_23v3"):
        from ncs_overview.rules.prerequisite_codes import check_prerequisite_levels
        [row] = check_prerequisite_levels({"선수학습": {"items": items, "text": ", ".join(items), "p": 1}}, code)
        return row

    @unittest.skipUnless(REAL.with_name("ncs_levels.tsv").is_file(), "수준 표 없음")
    def test_levels_are_read(self):
        cat = Catalog(REAL)
        self.assertEqual((cat.level("LM1203020401_23v3"), cat.level("1203020405"), cat.level("LM2001021701_25v1")), (4, 2, 6))
        self.assertIsNone(cat.level("9999999999"))

    @unittest.skipUnless(REAL.with_name("ncs_levels.tsv").is_file(), "수준 표 없음")
    def test_higher_level_is_rejected_and_subjects_are_ignored(self):
        row = self.run_items(["연회 판촉(LM1203020401_23v3)", "연회 행사 진행(LM1203020405_23v2)", "호텔 경영론", "웨딩 행사 준비"])
        self.assertEqual(row["판정"], "부적합")
        self.assertEqual(row["비고"]["④ 선수학습 수준 ≤ 이 모듈 수준"], "「연회 판촉(LM1203020401_23v3)」 수준 4 > 이 모듈 수준 3")
        self.assertEqual(row["이 모듈 수준"], 3)
        ok = self.run_items(["연회 행사 진행(LM1203020405_23v2)", "웨딩 행사 준비"])  # 2, 3 ≤ 3
        self.assertEqual(ok["판정"], "적합")
        none = self.run_items(["호텔 경영론"])
        self.assertEqual(none["체크"]["④ 선수학습 수준 ≤ 이 모듈 수준"], "-")

    def test_without_levels_table_is_undecided(self):
        os.environ["NCS_CATALOG_FILE"] = str(REAL) + ".missing"
        row = self.run_items(["연회 판촉(LM1203020401_23v3)"])
        self.assertEqual(row["판정"], "판단불가")
