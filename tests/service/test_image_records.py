"""이미지 레코드 형식 검사(ncs_service.images.image_records) — DB 없이 돈다. 문서의 예시 파일과 '거부되는 예'가 실제와 같은지도 본다."""

import hashlib
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from ncs_service.images import image_terms
from ncs_service.images.image_db import main
from ncs_service.images.image_records import SCHEMA, RecordError, normalize, read_records, rights_changes

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "examples" / "image_records" / "records.example.json"
SHA = "a" * 64


def reasons(record, **kwargs) -> list[str]:
    try:
        normalize(record, **kwargs)
    except RecordError as error:
        return error.reasons
    return []


class ExampleFileTests(unittest.TestCase):
    """docs/examples의 예시는 담당자들이 베껴 쓰는 기준이다 — 항상 통과해야 한다."""

    def setUp(self):
        self.records, self.base = read_records(EXAMPLE)

    def test_every_example_record_is_valid(self):
        for index, record in enumerate(self.records):
            with self.subTest(index=index):
                self.assertEqual(reasons(record, base_dir=self.base), [])

    def test_extraction_example_is_filled_from_the_file(self):
        record = normalize(self.records[0], base_dir=self.base)
        data = (self.base / "images" / "figure_1-1.png").read_bytes()
        asset = record.asset
        self.assertEqual(asset["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual((asset["filename"], asset["format"], asset["width_px"], asset["height_px"], asset["byte_size"]),
                         ("figure_1-1.png", "png", 96, 64, len(data)))
        self.assertEqual(asset["content"], data)
        self.assertEqual((asset["upscaled_format"], asset["upscaled_width_px"], asset["upscaled_height_px"],
                          asset["upscale_engine"]), ("png", 192, 128, "esrgan-fast"))
        self.assertEqual([p["module_code"] for p in record.placements], ["LM1203020201_24v3", "LM1203020202_24v3"])
        self.assertEqual(record.placements[1]["page"], None)
        self.assertEqual([link["placement"] for link in record.links], [0, 1])
        # usage 2(집필진 삽화 AI 수정 보완) → 수정 보완함, 다른 AI 키가 있으므로 used는 true
        self.assertEqual((record.rights["ai_used"], record.rights["ai_mode"], record.rights["ai_date"]),
                         (True, "modified", date(2026, 10, 20)))
        self.assertNotIn("license_scheme", record.rights, "적지 않은 묶음은 담지 않는다(다시 넣을 때 덮어쓰지 않도록)")

    def test_kogl_example_derives_scheme_and_conditions(self):
        rights = normalize(self.records[1], base_dir=self.base).rights
        self.assertEqual({key: rights[key] for key in ("license_scheme", "kogl_type", "kogl_ai", "attribution",
                                                       "non_commercial", "no_derivatives", "share_alike")},
                         {"license_scheme": "kogl", "kogl_type": 2, "kogl_ai": True, "attribution": True,
                          "non_commercial": True, "no_derivatives": False, "share_alike": False})
        self.assertEqual(rights["retrieved_on"], date(2026, 11, 17))

    def test_metadata_only_example_needs_no_file(self):
        record = normalize(self.records[2], base_dir=self.base)
        self.assertIsNone(record.asset["content"])
        self.assertEqual((record.rights["license_scheme"], record.rights["cc_license"], record.rights["share_alike"],
                          record.rights["non_commercial"]), ("cc", "by-nc-sa", True, True))

    def test_cli_check_passes_the_example_without_a_database(self):
        self.assertEqual(main([str(EXAMPLE), "--check"]), 0)


class DerivedValueTests(unittest.TestCase):
    def test_every_kogl_type_and_cc_license_gets_its_conditions(self):
        names = ("attribution", "non_commercial", "no_derivatives", "share_alike")
        for kogl_type, conditions in image_terms.KOGL_CONDITIONS.items():
            rights = normalize({"sha256": SHA, "rights": {"license": {"kogl_type": kogl_type}}}).rights
            self.assertEqual(tuple(rights[name] for name in names), (*conditions, False), kogl_type)
        for code, conditions in image_terms.CC_LICENSE.items():
            rights = normalize({"sha256": SHA, "rights": {"license": {"cc": code}}}).rights
            self.assertEqual(tuple(rights[name] for name in names), conditions, code)

    def test_schemes_without_a_type_take_conditions_as_written(self):
        rights = normalize({"sha256": SHA, "rights": {"license": {"scheme": "expired", "note": "보호기간 만료"},
                                                       "conditions": {"attribution": False}}}).rights
        self.assertEqual((rights["license_scheme"], rights["attribution"], rights["non_commercial"]), ("expired", False, None))

    def test_every_ai_usage_gets_its_mode(self):
        for usage, (_, mode) in image_terms.AI_USAGE.items():
            self.assertEqual(normalize({"sha256": SHA, "rights": {"ai": {"usage": usage}}}).rights["ai_mode"], mode)

    def test_ai_not_used_can_be_stated(self):
        rights = normalize({"sha256": SHA, "rights": {"ai": {"used": False}}}).rights
        self.assertEqual((rights["ai_used"], rights["ai_usage"], rights["ai_tool"]), (False, None, None))

    def test_small_cleanups(self):
        record = normalize({"sha256": SHA.upper(), "keywords": [" 객실 ", "예약", "객실", ""],
                            "placements": [{"module_code": " LM1203020201_24v3 "}],
                            "links": [{"unit_code": "1203020201_24v3"}, {"unit_code": "1203020201_24v3"}]})
        self.assertEqual(record.asset["sha256"], SHA)
        self.assertEqual(record.asset["keywords"], ["객실", "예약"])
        self.assertEqual((record.placements[0]["module_code"], record.placements[0]["label"],
                          record.placements[0]["para_index"]), ("LM1203020201_24v3", "", 0))
        self.assertEqual(len(record.links), 1)
        self.assertIsNone(record.rights)

    def test_bytes_can_be_given_directly(self):
        asset = normalize({"content": b"not an image"}).asset
        self.assertEqual((asset["sha256"], asset["byte_size"], asset["format"]),
                         (hashlib.sha256(b"not an image").hexdigest(), 12, None))


class RejectionTests(unittest.TestCase):
    def assert_rejected(self, record, *fragments, **kwargs):
        found = reasons(record, **kwargs)
        self.assertTrue(found, "거부되어야 합니다")
        for fragment in fragments:
            self.assertTrue(any(fragment in reason for reason in found), f"사유에 '{fragment}'가 없습니다: {found}")

    def test_documented_rejections(self):
        """docs/IMAGE_RECORD.md '거부되는 예' 표와 같은 입력·같은 사유."""
        self.assert_rejected({}, "sha256 또는 file이 필요합니다")
        self.assert_rejected({"sha256": SHA, "kind": "사진"}, "허용값이 아닙니다")
        self.assert_rejected({"sha256": SHA, "rights": {"license": {"kogl_type": 1}, "conditions": {"non_commercial": True}}},
                             "상업적 이용금지", "라이선스 유형과 다릅니다")
        self.assert_rejected({"sha256": SHA, "rights": {"license": {"kogl_type": 0, "kogl_ai": True}}},
                             "AI유형(kogl_ai)은 제1~4유형과만")
        self.assert_rejected({"sha256": SHA, "rights": {"ownership": "kogl"}}, "kogl_type이 필요합니다")
        self.assert_rejected({"sha256": SHA, "rights": {"ai": {"usage": 1, "mode": "modified"}}}, "생성함", "수정 보완함")
        self.assert_rejected({"sha256": SHA, "rights": {"status": "confirmed", "confirmed_by": "누구"}},
                             "기관 확정은 적재로 할 수 없습니다")

    def test_shape_errors(self):
        self.assert_rejected("그림", "객체")
        self.assert_rejected({"sha256": "abc"}, "16진 64자")
        self.assert_rejected({"sha256": SHA, "caption": "오타 난 키"}, "모르는 키 caption")
        self.assert_rejected({"sha256": SHA, "width_px": 0}, "width_px는 1 이상의 정수")
        self.assert_rejected({"sha256": SHA, "width_px": True}, "width_px")
        self.assert_rejected({"sha256": SHA, "keywords": "객실"}, "keywords는 문자열 목록")
        self.assert_rejected({"sha256": SHA, "placements": [{"label": "그림 1-1"}]}, "placements[0]: module_code가 필요합니다")
        self.assert_rejected({"sha256": SHA, "placements": [{"module_code": "LM1"}, {"module_code": "LM1"}]},
                             "placements[1]", "두 번")
        self.assert_rejected({"sha256": SHA, "placements": [{"module_code": "LM1", "width_mm": -1}]}, "width_mm")
        self.assert_rejected({"sha256": SHA, "links": [{"element_code": "x"}]}, "links[0]: unit_code가 필요합니다")
        self.assert_rejected({"sha256": SHA, "links": [{"unit_code": "u", "placement": 0}]}, "수록 위치가 없습니다")
        self.assert_rejected({"sha256": SHA, "rights": {"retrieved_on": "2026/11/17"}}, "YYYY-MM-DD")
        self.assert_rejected({"sha256": SHA, "upscaled": {"engine": "esrgan-fast"}}, "업스케일본 file이 필요합니다")

    def test_license_errors(self):
        self.assert_rejected({"sha256": SHA, "rights": {"license": {"kogl_type": 5}}}, "0~4")
        self.assert_rejected({"sha256": SHA, "rights": {"license": {"kogl_type": 1, "cc": "by"}}}, "함께 적을 수 없습니다")
        self.assert_rejected({"sha256": SHA, "rights": {"license": {"scheme": "kogl"}}}, "kogl_type이 필요합니다")
        self.assert_rejected({"sha256": SHA, "rights": {"license": {"scheme": "cc"}}}, "cc 유형이 필요합니다")
        self.assert_rejected({"sha256": SHA, "rights": {"license": {"scheme": "other", "kogl_type": 1}}}, "유형과 맞지 않습니다")
        self.assert_rejected({"sha256": SHA, "rights": {"license": {"cc": "BY"}}}, "허용값이 아닙니다")
        self.assert_rejected({"sha256": SHA, "rights": {"ai": {"used": False, "tool": "도구"}}}, "used가 false인데")

    def test_all_reasons_of_one_record_are_reported_together(self):
        found = reasons({"sha256": SHA, "kind": "사진", "width_px": -1, "placements": [{}]})
        self.assertEqual(len(found), 3, found)

    def test_file_must_exist_match_and_stay_inside_the_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "records"
            shutil.copytree(EXAMPLE.parent, base)
            (Path(folder) / "outside.png").write_bytes(b"outside")
            self.assert_rejected({"file": "images/none.png"}, "찾을 수 없습니다", base_dir=base)
            self.assert_rejected({"file": "../outside.png"}, "기준 폴더 밖", base_dir=base)
            self.assert_rejected({"file": "images/figure_1-1.png", "sha256": SHA}, "파일 내용과 다릅니다", base_dir=base)
            self.assert_rejected({"file": "images/figure_1-1.png"}, "기준 폴더가 없습니다")

    def test_read_records_checks_the_schema_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            path.write_text(json.dumps({"schema": "other/1", "records": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_records(path)
            path.write_text(json.dumps({"schema": SCHEMA, "records": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_records(path)
            path.write_text(json.dumps([{"sha256": SHA}]), encoding="utf-8")
            self.assertEqual(read_records(path), ([{"sha256": SHA}], Path(folder)))


class RightsChangeTests(unittest.TestCase):
    """확정 화면의 권리 정보 수정 요청(rights_changes) — 레코드의 rights와 같은 검사에 '비우기'가 더해진다."""

    def test_only_written_groups_change(self):
        self.assertEqual(rights_changes({"category": "author_made", "author": " 집필진 "}),
                         {"category": "author_made", "author": "집필진"})
        changes = rights_changes({"license": {"kogl_type": 3}})
        self.assertEqual((changes["license_scheme"], changes["no_derivatives"], changes["non_commercial"]),
                         ("kogl", True, False))
        self.assertNotIn("category", changes)

    def test_null_clears(self):
        self.assertEqual(rights_changes({"author": None, "retrieved_on": None, "reuse_scope": None}),
                         {"author": None, "retrieved_on": None, "reuse_scope": "unknown"})
        cleared = rights_changes({"license": None})
        self.assertEqual((cleared["license_scheme"], cleared["kogl_type"], cleared["kogl_ai"], cleared["attribution"]),
                         (None, None, False, None))
        self.assertEqual(len(cleared), 9)
        cleared = rights_changes({"ai": None})
        self.assertEqual((cleared["ai_used"], cleared["ai_usage"], cleared["ai_tool"]), (False, None, None))
        self.assertEqual(len(cleared), 8)

    def test_bad_requests_are_rejected_with_reasons(self):
        for value, fragment in (({}, "바꿀 내용이 없습니다"), (None, "바꿀 내용이 없습니다"), ("x", "객체"),
                                ({"category": "집필자 직접제작"}, "허용값이 아닙니다"),
                                ({"status": "confirmed"}, "기관 확정은 적재로 할 수 없습니다"),
                                ({"license": {"kogl_type": 1}, "conditions": {"non_commercial": True}}, "라이선스 유형과 다릅니다"),
                                ({"ownership": "kogl"}, "kogl_type이 필요합니다")):
            with self.subTest(value=value):
                with self.assertRaises(RecordError) as caught:
                    rights_changes(value)
                self.assertTrue(any(fragment in reason for reason in caught.exception.reasons), caught.exception.reasons)


if __name__ == "__main__":
    unittest.main()
