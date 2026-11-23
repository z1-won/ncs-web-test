"""공공누리 수집 JSON(0.1-PoC) → 이미지 레코드(ncs_service.images.kogl_import, REQ-02-012). DB 없이 돈다."""

import copy
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from ncs_knowledge.rules.sources import source_check
from ncs_service.images import image_terms, kogl_import
from ncs_service.images.image_db import main
from ncs_service.images.image_records import normalize

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "examples" / "kogl_samples" / "kogl_samples.example.json"


class KoglCase(unittest.TestCase):
    def setUp(self):
        # 골든 테스트가 NCS_CATALOG_FILE로 NCS 목록을 꺼 두므로, 이 묶음을 도는 동안만 걷어 패키지 기본 목록을 쓴다
        saved = os.environ.pop("NCS_CATALOG_FILE", None)
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, "NCS_CATALOG_FILE", saved)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        shutil.copy(EXAMPLE.parent / "kogl_0001.png", self.folder / "kogl_0001.png")
        self.data = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def item(self, **changes) -> dict:
        """예시 항목에서 일부만 바꾼 것. 'kogl.type'처럼 점으로 안쪽 키를 가리킨다."""
        item = copy.deepcopy(self.data["items"][0])
        for path, value in changes.items():
            target, *rest = path.split("__")
            if rest:
                item[target][rest[0]] = value
            else:
                item[target] = value
        return item

    def convert(self, **changes):
        return kogl_import.convert_item(self.item(**changes), self.folder)

    def check(self, *items) -> dict:
        return kogl_import.run(None, {**self.data, "items": list(items)}, base_dir=self.folder, check_only=True)


class ConversionTests(KoglCase):
    def test_example_becomes_a_valid_image_record(self):
        record, reasons, notes = self.convert()
        self.assertEqual((reasons, notes), ([], []))
        rights = record["rights"]
        self.assertEqual((record["source_id"], record["title"], record["file"], record["keywords"]),
                         ("KOGL-SAMPLE-0001", "객실 유형별 이용 현황 도표", "kogl_0001.png", ["객실", "이용정보", "부대시설"]))
        self.assertEqual((rights["category"], rights["ownership"], rights["license"], rights["source_org"], rights["retrieved_on"]),
                         ("public_license", "kogl", {"kogl_type": 1, "kogl_ai": False}, "예시기관", "2026-11-17"))
        self.assertEqual(rights["reuse_scope"], "all", "공공누리는 학습모듈 한정 허락이 아니다")
        self.assertNotIn("release_class", rights, "제0·1유형은 산출물 분류를 정하지 않는다")
        # 능력단위는 버전까지, 요소·수행준거는 NCS의 글과 맞춰 코드로
        self.assertEqual(record["links"], [{"unit_code": "1203020201_24v3", "element_code": "1203020201_24v3.1", "criterion_no": "1.1"}])
        normal = normalize(record, base_dir=self.folder)          # 이미지 레코드 검사를 그대로 통과한다
        self.assertEqual((normal.asset["format"], normal.asset["width_px"], normal.rights["license_scheme"], normal.rights["attribution"],
                          normal.rights["non_commercial"]), ("png", 80, "kogl", True, False))

    def test_credit_line_is_generated_in_the_f14_form(self):
        made = kogl_import.credit_line("https://www.kogl.or.kr/a?b=1", date(2026, 3, 5), 4)
        self.assertEqual(made, "공공누리 홈페이지(https://www.kogl.or.kr/a?b=1)에서 2026. 3. 5. 검색. 공공누리 제4유형.")
        self.assertEqual(source_check("출처: " + made), ("O", "전자 자료·검색"), "필요 지식 ⑧의 출처 골격 검사를 통과하는 문구여야 한다")
        record, _, notes = self.convert(source__credit_line="손으로 적은 다른 문구")
        self.assertEqual(record["rights"]["credit_line"], "공공누리 홈페이지(https://www.kogl.or.kr/)에서 2026. 11. 17. 검색. 공공누리 제1유형.")
        self.assertTrue(any("만든 문구를 넣었습니다" in note for note in notes))

    def test_every_type_and_ai_combination(self):
        for kogl_type, conditions in image_terms.KOGL_CONDITIONS.items():
            with self.subTest(kogl_type=kogl_type):
                declared = dict(zip(("attribution", "non_commercial", "no_derivatives"), conditions))
                result = self.check(self.item(kogl__type=f"제{kogl_type}유형", kogl__conditions=declared, kogl__ai_type_combined=kogl_type >= 1))
                self.assertEqual((result["통과"], result["거부"]), (1, []))
                record, _, _ = self.convert(kogl__type=f"제{kogl_type}유형", kogl__conditions=declared)
                self.assertEqual(record["rights"].get("release_class"), "inherit" if kogl_type >= 2 else None)
                wrong = {**declared, "non_commercial": not declared["non_commercial"]}       # 유형과 맞지 않는 조건
                rejected = self.check(self.item(kogl__type=f"제{kogl_type}유형", kogl__conditions=wrong))
                self.assertIn("상업적 이용금지", rejected["거부"][0]["reasons"][0])
        ai_with_zero = self.check(self.item(kogl__type="제0유형", kogl__ai_type_combined=True,
                                            kogl__conditions={"attribution": False, "non_commercial": False, "no_derivatives": False}))
        self.assertIn("제1~4유형과만", ai_with_zero["거부"][0]["reasons"][0])
        for written in ("1", 1, "제 3 유형", "3유형"):                                       # 적는 꼴이 조금 달라도 읽는다
            record, reasons, _ = self.convert(kogl__type=written, kogl__conditions=None)
            self.assertEqual((reasons, record["rights"]["license"]["kogl_type"]), ([], int(str(written).strip("제 유형"))))

    def test_ncs_link_falls_back_step_by_step(self):
        record, _, notes = self.convert(ncs_link__performance_criteria="NCS에 없는 수행준거 문장")
        self.assertEqual(record["links"], [{"unit_code": "1203020201_24v3", "element_code": "1203020201_24v3.1"}])
        self.assertIn("능력단위요소까지만", notes[0])
        record, _, notes = self.convert(ncs_link__element="없는 요소", ncs_link__performance_criteria="없는 문장")
        self.assertEqual(record["links"], [{"unit_code": "1203020201_24v3"}])
        record, _, notes = self.convert(ncs_link__lm_code="LM9999999901")
        self.assertEqual(record["links"][0]["unit_code"], "9999999901")
        self.assertIn("NCS 목록에서 찾지 못해", notes[0])
        record, _, notes = self.convert(ncs_link__lm_code="")
        self.assertNotIn("links", record)
        self.assertEqual(self.convert(ncs_link__lm_code="LM1203020201_24v3")[0]["links"][0]["unit_code"], "1203020201_24v3")

    def test_notes_do_not_reject(self):
        record, reasons, notes = self.convert(file__width_px=1920, file__format="jpg", source__original_url="https://example.go.kr/data/1",
                                              status__confirmed_by="홍길동")
        self.assertEqual(reasons, [])
        self.assertIsNotNone(record)
        joined = " / ".join(notes)
        for fragment in ("file.format은 jpg인데 실제 파일은 png", "1920×80px와 실제 80×80px", "공공누리(kogl.or.kr / kogl.go.kr)가 아닙니다",
                         "기관 확정은 확정 화면에서"):
            self.assertIn(fragment, joined)
        go_kr = self.convert(source__original_url="https://www.kogl.go.kr/x")[2]
        self.assertFalse(any("공공누리(" in note for note in go_kr), "F14 예시의 go.kr 주소도 공공누리로 본다")


class RejectionTests(KoglCase):
    def test_each_required_field(self):
        cases = [
            (dict(file__name="없는그림.png"), "함께 올라오지 않았습니다"), (dict(file__name=""), "file.name"),
            (dict(kogl__type="제5유형"), "제0유형~제4유형"), (dict(kogl__type=None), "제0유형~제4유형"), (dict(kogl__type=True), "제0유형~제4유형"),
            (dict(kogl__ai_type_combined="yes"), "true/false"),
            (dict(source__retrieved_at="2026.11.17"), "YYYY-MM-DD"), (dict(source__original_url="kogl.or.kr/abc"), "http(s) 주소"),
            (dict(source__original_url="https://www.kogl.or.kr/a b"), "http(s) 주소"), (dict(source__original_org=""), "원 출처 기관"),
            (dict(ncs_link__lm_code="LM12"), "LM + 숫자 10자리"), (dict(ncs_link__match_keywords="객실"), "문자열 목록"),
            (dict(title="(예시) 시장 조사 회의 장면"), "자리표시"), (dict(source__original_url="https://www.kogl.or.kr/(해당 자료 URL)"), "자리표시"),
            (dict(kogl="제1유형"), "객체"),
        ]
        for changes, fragment in cases:
            with self.subTest(changes=changes):
                record, reasons, _ = self.convert(**changes)
                self.assertIsNone(record)
                self.assertTrue(any(fragment in reason for reason in reasons), reasons)
        self.assertEqual(kogl_import.convert_item("글", self.folder)[1], ["항목은 객체({…})여야 합니다"])

    def test_file_name_cannot_leave_the_folder(self):
        (self.folder.parent / "outside.png").write_bytes((self.folder / "kogl_0001.png").read_bytes())
        self.addCleanup((self.folder.parent / "outside.png").unlink)
        record, reasons, _ = self.convert(file__name="../outside.png")
        self.assertIsNone(record)
        self.assertIn("'outside.png'이(가) 함께 올라오지 않았습니다", reasons[0])

    def test_report_keeps_the_original_item_numbers(self):
        """바꾸다 거부된 건과 레코드 검사에서 거부된 건이 수집 JSON의 순번으로 한 목록에 나온다."""
        bad_conditions = self.item(kogl__conditions={"attribution": False})
        result = self.check(self.item(kogl__type="x"), self.item(), bad_conditions, self.item(file__name="없음.png"))
        self.assertEqual((result["전체"], result["통과"], [r["index"] for r in result["거부"]]), (4, 1, [0, 2, 3]))
        self.assertIn("출처표시", result["거부"][1]["reasons"][0])
        self.assertEqual(result["형식"], "공공누리 수집 JSON(0.1-PoC)")
        with self.assertRaises(ValueError):
            kogl_import.run(None, {"schema_version": "0.1-PoC", "items": {}}, base_dir=self.folder, check_only=True)
        with self.assertRaises(ValueError):
            kogl_import.run(None, self.data, base_dir=self.folder)          # DB 없이 적재

    def test_dataset_detection(self):
        self.assertTrue(kogl_import.is_dataset(self.data))
        for other in ({"schema": "ncs-image-record/0.3", "records": []}, {"items": []}, [], {"schema_version": "9", "items": []}):
            self.assertFalse(kogl_import.is_dataset(other))

    def test_cli_check_reads_both_formats(self):
        self.assertEqual(main([str(EXAMPLE), "--check"]), 0)
        task_example = self.folder / "task.json"           # 과업 안내의 입력 예시 그대로: 자리표시와 없는 그림 때문에 거부된다
        item = self.item(title="(예시) 시장 조사 회의 장면", source__original_url="https://www.kogl.or.kr/(해당 자료 URL)")
        task_example.write_text(json.dumps({**self.data, "items": [item]}, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(main([str(task_example), "--check"]), 1)


if __name__ == "__main__":
    unittest.main()
