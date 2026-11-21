"""NCS_TEST_DATABASE_URL을 지정하면 권리 증빙 점검 결과를 이미지 저작권 DB에 잇는 것(REQ-02-014 → 010)을 실제 PostgreSQL로 검사한다."""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

import rights_samples as S
from ncs_service.postgres import migrate
from ncs_web.server import create_app

DSN = os.getenv("NCS_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class RightsLinkIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)
        cls.client = TestClient(create_app(database_url=DSN, require_login=False))

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.used = [hashlib.sha256(S.png(index)).hexdigest() for index in range(1, len(S.FIGURES) + 1)]
        self.addCleanup(self.cleanup)
        self.cleanup()

    def cleanup(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_assets WHERE sha256 = ANY(%s)", (self.used,))

    def post(self, expect: int = 200, **data) -> dict:
        manuscript, forms = S.manuscript(self.folder), S.full_forms(self.folder)
        files = [("manuscript", (manuscript.name, manuscript.read_bytes()))] + [("forms", (f.name, f.read_bytes())) for f in forms]
        fields = dict(first_review_on="2026-10-01", submitted_on="2026-10-20", transfer_author="true", transfer_maker="true",
                      portrait="none", pledge="true", save="true", by="에디팅기관")
        response = self.client.post("/api/rights/check", files=files, data={**fields, **data})
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def image(self, index: int) -> dict:
        with psycopg.connect(DSN) as connection:
            image_id = connection.execute("SELECT id FROM image_assets WHERE sha256 = %s", (self.used[index - 1],)).fetchone()[0]
        return self.client.get(f"/api/images/{image_id}").json()

    def test_checked_figures_and_confirmed_evidence_reach_the_image_db(self):
        saved = self.post()["저장"]
        # 증빙 6건 = 집필자 양도 동의서 3(그림 1-1·1-3·2-1) + AI 서약서 1(1-1) + 이용허락 동의서 1(1-2) + 제작자 양도 동의서 1(2-2).
        # 제작 목록은 대조용 서류라 증빙 종류가 아니고, 공공누리·기개발은 낼 증빙이 없다
        self.assertEqual(saved, {"모듈 코드": S.MODULE, "그림": 8, "새 그림": 8, "증빙": 6, "건너뜀": 0, "거부": []})

        first = self.image(1)                       # 그림 1-1: 직접제작(사진) + AI
        self.assertEqual((first["title"], first["has_file"], first["rights"]["category"], first["rights"]["status"],
                          first["rights"]["ai_used"], first["rights"]["ai_mode"], first["rights"]["ai_tool"], first["rights"]["ai_date"]),
                         ("NCS학습모듈 개념도", True, "author_made", "auto", True, "generated", "ChatGPT", "2026-07-20"))
        place = first["placements"][0]
        self.assertEqual((place["module_code"], place["label"], place["caption"], place["source_line"]),
                         (S.MODULE, "그림 1-1", "NCS학습모듈 개념도", "출처: 집필진 제작(2026)"))
        self.assertEqual(sorted((e["kind"], e["file_ref"], e["submitted_on"]) for e in first["evidence"]),
                         [("ai_pledge", "AI서약서.hwpx", "2026-10-20"), ("transfer_consent", None, "2026-10-20")])
        self.assertIn("evidence_added", [entry["action"] for entry in first["history"]])
        self.assertEqual([(e["kind"], e["file_ref"]) for e in self.image(2)["evidence"]], [("license_consent", "원고집필계약서_붙임.hwpx")])
        self.assertEqual(self.image(6)["evidence"], [], "공공누리 자료는 따로 낼 증빙이 없다")
        self.assertEqual((self.image(6)["rights"]["category"], self.image(8)["rights"]), ("public_license", None),
                         "목록에 없는 그림은 그림과 수록 위치만 들어가고 권리 정보는 비어 있다")

        again = self.post()["저장"]                  # 다시 반영해도 그림·증빙이 늘지 않는다
        self.assertEqual((again["그림"], again["새 그림"], again["증빙"]), (8, 0, 0))
        self.assertEqual(len(self.image(1)["evidence"]), 2)

    def test_page_from_the_print_copy_reaches_the_placement(self):
        printed = Path(__file__).resolve().parents[1] / "fixtures" / "출력본_ok_LM1203020201_24v3.pdf"      # [그림 1-1]이 4쪽
        manuscript, forms = S.manuscript(self.folder), S.full_forms(self.folder)
        files = ([("manuscript", (manuscript.name, manuscript.read_bytes())), ("print_copy", (printed.name, printed.read_bytes()))]
                 + [("forms", (f.name, f.read_bytes())) for f in forms])
        response = self.client.post("/api/rights/check", files=files, data={"save": "true", "by": "에디팅기관"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.image(1)["placements"][0]["page"], self.image(2)["placements"][0]["page"]), (4, None))

    def test_figures_sharing_a_number_keep_their_own_picture(self):
        """실제 원고처럼 같은 번호가 두 번 쓰이고 뒤 번호가 빈 캡션이 여럿이어도 그림마다 제 그림 파일에 붙는다."""
        figures = [("그림 1-1", "첫 그림", "출처: 집필진 제작(2026)", ""), ("그림 1-1", "번호가 같은 다른 그림", "출처: 집필진 제작(2026)", ""),
                   ("그림 2-", "뒤 번호가 빈 그림", "출처: 집필진 제작(2026)", ""), ("그림 2-", "뒤 번호가 빈 또 다른 그림", "출처: 집필진 제작(2026)", "")]
        manuscript = S.manuscript(self.folder, figures)
        response = self.client.post("/api/rights/check", files=[("manuscript", (manuscript.name, manuscript.read_bytes()))],
                                    data={"save": "true", "by": "에디팅기관"})
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()["저장"]
        self.assertEqual((saved["그림"], saved["새 그림"], saved["건너뜀"]), (4, 4, 0))
        self.assertEqual([[place["caption"] for place in self.image(index)["placements"]] for index in (1, 2, 3, 4)],
                         [["첫 그림"], ["번호가 같은 다른 그림"], ["뒤 번호가 빈 그림"], ["뒤 번호가 빈 또 다른 그림"]])

    def test_missing_evidence_is_not_linked(self):
        saved = self.post(transfer_author="false", pledge="false")["저장"]
        self.assertEqual(saved["증빙"], 2, "제출로 확인된 것만 잇는다: 이용허락 동의서 1 + 제작자 양도 동의서 1")
        self.assertEqual(self.image(1)["evidence"], [], "집필자 양도 동의서·서약서가 누락이면 그림 1-1에는 이을 증빙이 없다")

    def test_save_needs_a_name_and_a_module_code(self):
        self.assertIn("by", self.post(expect=400, by=" ")["error"])
        self.assertEqual(self.post(module_code="LM1203020202_24v3")["저장"]["모듈 코드"], "LM1203020202_24v3")
        self.assertIn("모듈 코드", self.post(expect=400, module_code="LM12")["error"])


if __name__ == "__main__":
    unittest.main()
