"""NCS_TEST_DATABASE_URL을 지정하면 이미지 저작권 DB API(/api/images, REQ-02-010)를 실제 PostgreSQL로 검사한다.

테스트가 넣은 그림은 끝날 때 sha256으로 찾아 지운다. 다른 자료가 섞여 있어도 되게 목록은 테스트용 키워드로 좁혀 본다.
"""

import hashlib
import json
import os
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from ncs_service.image_db import load_records
from ncs_service.postgres import migrate
from ncs_web.server import create_app

DSN = os.getenv("NCS_TEST_DATABASE_URL")
UNIT = "1203020201_24v3"
EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "image_records"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (64).to_bytes(4, "big") + (48).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class ImageApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)
        cls.client = TestClient(create_app(database_url=DSN))

    def setUp(self):
        self.tag = f"테스트-{uuid4()}"          # 이 테스트가 넣은 그림만 고르는 키워드
        self.used: list[str] = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_assets WHERE sha256 = ANY(%s)", (self.used,))

    def add(self, **fields) -> str:
        """그림 1건을 적재하고 id를 돌려준다."""
        content = PNG + uuid4().bytes
        sha256 = hashlib.sha256(content).hexdigest()
        self.used.append(sha256)
        keywords = [self.tag, *fields.pop("keywords", [])]
        report = load_records(DSN, [{"content": content, "keywords": keywords, **fields}], changed_by="적재")
        self.assertEqual(report.rejected, [])
        with psycopg.connect(DSN) as connection:
            return str(connection.execute("SELECT id FROM image_assets WHERE sha256 = %s", (sha256,)).fetchone()[0])

    def listed(self, path: str = "/api/images", **params) -> dict:
        response = self.client.get(path, params={"keyword": self.tag, **params})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def post(self, image_id: str, action: str, expect: int = 200, **body) -> dict:
        response = self.client.post(f"/api/images/{image_id}/{action}", json={"by": "에디팅기관", **body})
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def confirmed(self, **fields) -> str:
        rights = {"category": "author_made", "ownership": "government", "reuse_scope": "all", **fields.pop("rights", {})}
        image_id = self.add(rights=rights, **fields)
        self.post(image_id, "confirm")
        return image_id

    # ── 상태·허용값 ──
    def test_health_and_terms(self):
        self.assertIs(self.client.get("/api/health").json()["image_db"], True)
        terms = self.client.get("/api/images/terms").json()
        self.assertEqual(terms["category"]["public_license"], "공공누리·공유마당")
        self.assertEqual(terms["kogl_type"]["2"], {"attribution": True, "non_commercial": True, "no_derivatives": False})
        self.assertEqual(terms["ai_usage"]["4"], {"name": "AI 창작", "mode": "generated"})

    # ── 관리용 조회 ──
    def test_list_filters_and_paging(self):
        plain = self.add(title="권리 정보 없는 그림")
        kogl = self.add(title="공공누리 그림", kind="graph", rights={"category": "public_license", "license": {"kogl_type": 2}},
                        placements=[{"module_code": "LM" + UNIT, "label": "그림 1-1", "caption": "기온 변화"},
                                    {"module_code": "LM1203020202_24v3", "label": "그림 2-1"}],
                        links=[{"unit_code": UNIT}])
        done = self.confirmed(title="확정된 그림")
        everything = self.listed()
        self.assertEqual((everything["total"], {item["id"] for item in everything["items"]}), (3, {plain, kogl, done}))

        def ids(**params):
            return [item["id"] for item in self.listed(**params)["items"]]

        self.assertEqual(ids(status="none"), [plain])
        self.assertEqual(ids(status="auto"), [kogl])
        self.assertEqual(ids(status="confirmed"), [done])
        self.assertEqual(ids(kogl_type=2), [kogl])
        self.assertEqual(ids(license_scheme="kogl", category="public_license"), [kogl])
        self.assertEqual(ids(module_code="LM1203020202_24v3"), [kogl])
        self.assertEqual(ids(unit_code=UNIT), [kogl])
        self.assertEqual(ids(kind="graph"), [kogl])
        self.assertEqual(ids(q="기온"), [kogl], "수록 위치의 그림명으로도 찾는다")
        self.assertEqual(ids(q="100%_"), [], "검색어의 %와 _는 글자 그대로 본다")
        item = next(i for i in everything["items"] if i["id"] == kogl)
        self.assertEqual((item["placement_count"], item["module_count"], item["has_file"], item["width_px"], item["kogl_type"],
                          item["module_code"], item["label"]), (2, 2, True, 64, 2, "LM" + UNIT, "그림 1-1"))
        self.assertNotIn("content", item)
        page = self.listed(limit=2, offset=2)
        self.assertEqual((page["total"], len(page["items"])), (3, 1))
        self.assertEqual(self.client.get("/api/images", params={"limit": 1000}).status_code, 400)

    def test_detail_and_file(self):
        image_id = self.add(title="상세", rights={"license": {"cc": "by-nc"}, "retrieved_on": "2026-11-17"},
                            placements=[{"module_code": "LM" + UNIT, "label": "그림 1-1", "width_mm": 120.5}],
                            links=[{"unit_code": UNIT, "criterion_no": "1.1", "placement": 0}])
        detail = self.client.get(f"/api/images/{image_id}").json()
        self.assertEqual((detail["title"], detail["has_file"], detail["rights"]["cc_license"], detail["rights"]["non_commercial"],
                          detail["rights"]["retrieved_on"], detail["rights"]["status"]),
                         ("상세", True, "by-nc", True, "2026-11-17", "auto"))
        self.assertEqual((detail["placements"][0]["width_mm"], detail["links"][0]["placement_id"]),
                         (120.5, detail["placements"][0]["id"]))
        self.assertEqual([entry["action"] for entry in detail["history"]], ["created"])
        self.assertEqual(detail["evidence"], [])
        self.assertNotIn("content", detail)

        file = self.client.get(f"/api/images/{image_id}/file")
        self.assertEqual((file.status_code, file.headers["content-type"], file.headers["x-content-type-options"]),
                         (200, "image/png", "nosniff"))
        self.assertTrue(file.content.startswith(PNG))
        self.assertEqual(self.client.get(f"/api/images/{image_id}/file", params={"upscaled": True}).status_code, 404)
        for missing in (str(uuid4()), "not-a-uuid"):
            self.assertEqual(self.client.get(f"/api/images/{missing}").status_code, 404)
            self.assertEqual(self.client.get(f"/api/images/{missing}/file").status_code, 404)

    # ── 수정 ──
    def test_update_rights_writes_history_and_keeps_other_fields(self):
        image_id = self.add(rights={"category": "public_license", "author": "처음"})
        first = self.post(image_id, "rights", rights={"license": {"kogl_type": 1}, "source_org": "○○청"}, by="김담당")
        self.assertEqual((first["rights"]["version"], first["rights"]["kogl_type"], first["rights"]["attribution"],
                          first["rights"]["category"], first["rights"]["author"]), (2, 1, True, "public_license", "처음"))
        entry = first["history"][0]
        self.assertEqual((entry["action"], entry["changed_by"], entry["version"], entry["changes"]["kogl_type"],
                          entry["changes"]["source_org"]), ("updated", "김담당", 2, [None, 1], [None, "○○청"]))
        same = self.post(image_id, "rights", rights={"source_org": "○○청"})
        self.assertEqual((same["rights"]["version"], len(same["history"])), (2, 2), "같은 값이면 버전·이력이 늘지 않는다")
        cleared = self.post(image_id, "rights", rights={"license": None, "author": None})
        self.assertEqual((cleared["rights"]["version"], cleared["rights"]["kogl_type"], cleared["rights"]["license_scheme"],
                          cleared["rights"]["author"], cleared["rights"]["source_org"]), (3, None, None, None, "○○청"))

    def test_update_creates_rights_for_an_image_without_them(self):
        image_id = self.add()
        made = self.post(image_id, "rights", rights={"category": "commissioned"})
        self.assertEqual((made["rights"]["status"], made["rights"]["version"], made["rights"]["reuse_scope"]),
                         ("auto", 1, "unknown"))
        self.assertEqual(made["history"][0]["changes"], {"category": [None, "commissioned"]})

    def test_update_rejections(self):
        image_id = self.add(rights={"ownership": "kogl", "license": {"kogl_type": 1}})
        for rights, fragment in (({"category": "집필자 직접제작"}, "허용값이 아닙니다"),
                                 ({"license": {"kogl_type": 0, "kogl_ai": True}}, "제1~4유형"),
                                 ({"status": "confirmed"}, "기관 확정은"), ({}, "바꿀 내용이 없습니다"),
                                 # 형식은 맞지만 지금 값과 합치면 DB 제약에 걸리는 수정 — 사람 말로 알려 준다
                                 ({"license": None}, "귀속이 공공누리 조건이면 공공누리 유형이 필요합니다")):
            with self.subTest(rights=rights):
                self.assertIn(fragment, self.post(image_id, "rights", expect=400, rights=rights)["error"])
        self.assertEqual(self.client.post(f"/api/images/{image_id}/rights", json={"rights": {"author": "x"}}).status_code, 400,
                         "by 없이는 바꿀 수 없다")
        self.assertEqual(self.client.post(f"/api/images/{image_id}/rights", json={"by": " ", "rights": {"author": "x"}}).status_code, 400)
        self.post(str(uuid4()), "rights", expect=404, rights={"author": "x"})
        untouched = self.client.get(f"/api/images/{image_id}").json()
        self.assertEqual((untouched["rights"]["version"], untouched["rights"]["kogl_type"]), (1, 1))

    def test_stale_version_is_refused(self):
        image_id = self.add(rights={"category": "author_made"})
        self.post(image_id, "rights", rights={"author": "먼저 저장"}, version=1)
        late = self.post(image_id, "rights", expect=409, rights={"author": "늦게 저장"}, version=1)
        self.assertIn("다른 사람이 먼저 바꿨습니다", late["error"])
        self.assertEqual(self.client.get(f"/api/images/{image_id}").json()["rights"]["author"], "먼저 저장")
        self.post(image_id, "confirm", expect=409, version=1)

    # ── 확정 ──
    def test_confirm_requires_category_and_ownership(self):
        nothing = self.add()
        self.assertIn("분류 체계·권리 귀속", self.post(nothing, "confirm", expect=400)["error"])
        partial = self.add(rights={"category": "author_made"})
        error = self.post(partial, "confirm", expect=400)["error"]
        self.assertIn("권리 귀속", error)
        self.assertNotIn("분류 체계", error)
        self.assertEqual(self.client.get(f"/api/images/{partial}").json()["rights"]["status"], "auto")

    def test_confirm_edit_lock_and_unconfirm(self):
        image_id = self.add(rights={"category": "author_made", "ownership": "government"})
        done = self.post(image_id, "confirm", by="박확정")
        rights = done["rights"]
        self.assertEqual((rights["status"], rights["confirmed_by"], rights["version"]), ("confirmed", "박확정", 2))
        self.assertIsNotNone(rights["confirmed_at"])
        self.assertIn("추천 목록에는 나오지 않습니다", done["notice"], "재사용 범위 미확인이면 알려 준다")
        self.assertEqual(done["history"][0]["action"], "confirmed")
        self.post(image_id, "confirm", expect=409)
        locked = self.post(image_id, "rights", expect=409, rights={"reuse_scope": "all"})
        self.assertIn("확정을 푼 뒤", locked["error"])

        opened = self.post(image_id, "unconfirm", by="박확정")
        self.assertEqual((opened["rights"]["status"], opened["rights"]["confirmed_by"], opened["rights"]["version"],
                          opened["rights"]["category"]), ("auto", None, 3, "author_made"))
        self.assertEqual(opened["history"][0]["changes"]["confirmed_by"], ["박확정", None])
        self.post(image_id, "unconfirm", expect=409)
        self.post(image_id, "rights", rights={"reuse_scope": "all"})
        again = self.post(image_id, "confirm")
        self.assertIsNone(again["notice"])
        self.assertEqual([entry["action"] for entry in again["history"]],
                         ["confirmed", "updated", "unconfirmed", "confirmed", "created"])
        self.assertEqual(again["rights"]["version"], 5)

    # ── 증빙 직접 등록·삭제 ──
    def test_evidence_is_registered_and_removed_from_the_detail_screen(self):
        image_id = self.confirmed(title="증빙을 붙일 그림")           # 기관 확정된 그림에도 증빙은 붙일 수 있다
        added = self.post(image_id, "evidence", by="김증빙", kind="license_consent", file_ref=" 원고집필계약서_붙임3.hwp ",
                          submitted_on="2026-10-20", note="원본은 문서고")
        self.assertEqual([(e["kind"], e["file_ref"], e["submitted_on"], e["note"]) for e in added["evidence"]],
                         [("license_consent", "원고집필계약서_붙임3.hwp", "2026-10-20", "원본은 문서고")])
        self.assertEqual((added["history"][0]["action"], added["history"][0]["changed_by"], added["history"][0]["changes"]),
                         ("evidence_added", "김증빙", {"evidence": [None, "이용허락 동의서 (원고집필계약서_붙임3.hwp)"]}))
        self.assertEqual((added["rights"]["status"], added["rights"]["version"]), ("confirmed", 2), "권리 정보와 확정 상태는 그대로다")

        same = self.post(image_id, "evidence", expect=409, kind="license_consent", file_ref="원고집필계약서_붙임3.hwp")
        self.assertIn("같은 증빙이 이미", same["error"])
        self.post(image_id, "evidence", kind="portrait_consent")     # 종류만으로도 등록된다
        self.assertEqual(len(self.client.get(f"/api/images/{image_id}").json()["evidence"]), 2)

        self.assertIn("허용값", self.post(image_id, "evidence", expect=400, kind="receipt")["error"])
        self.post(image_id, "evidence", expect=400, kind="ai_pledge", submitted_on="10/20")
        self.post(image_id, "evidence", expect=400, kind="ai_pledge", by="")
        self.post("00000000-0000-0000-0000-000000000000", "evidence", expect=404, kind="ai_pledge")

        evidence_id = added["evidence"][0]["id"]
        other = self.add(title="다른 그림")
        self.post(other, f"evidence/{evidence_id}/delete", expect=404)     # 다른 그림의 증빙은 지울 수 없다
        self.post(image_id, "evidence/not-a-uuid/delete", expect=404)
        removed = self.post(image_id, f"evidence/{evidence_id}/delete", by="김증빙")
        self.assertEqual([e["kind"] for e in removed["evidence"]], ["portrait_consent"])
        self.assertEqual((removed["history"][0]["action"], removed["history"][0]["changes"]),
                         ("evidence_removed", {"evidence": ["이용허락 동의서 (원고집필계약서_붙임3.hwp)", None]}))
        self.post(image_id, f"evidence/{evidence_id}/delete", expect=404)

    # ── 추천용 조회 ──
    def test_recommendable_shows_only_cleared_non_private_images(self):
        shown = self.confirmed(title="정부 귀속", placements=[{"module_code": "LM" + UNIT, "label": "그림 1-1"}],
                               links=[{"unit_code": UNIT}])
        limited = self.confirmed(title="이용허락 한정", rights={"ownership": "licensed", "reuse_scope": "module_only"})
        private = self.confirmed(title="비공개", rights={"release_class": "private"})
        unknown = self.confirmed(title="범위 미확인", rights={"reuse_scope": "unknown"})
        auto = self.add(title="자동 태깅", rights={"category": "author_made", "ownership": "government", "reuse_scope": "all"})
        bare = self.add(title="권리 정보 없음")

        found = self.listed("/api/images/recommendable")
        self.assertEqual((found["total"], [item["id"] for item in found["items"]]), (2, [shown, limited]),
                         "정부 귀속 + 전체 재사용 자산이 먼저 나온다")
        self.assertEqual([item["scope_check_needed"] for item in found["items"]], [False, True])
        first = found["items"][0]
        # REQ-04-006: 원본 출처·라이선스 정보가 함께 나가고 파일 내용은 싣지 않는다
        self.assertLessEqual({"license_scheme", "kogl_type", "attribution", "non_commercial", "no_derivatives", "source_org",
                              "source_url", "credit_line", "ownership", "reuse_scope", "confirmed_by"}, set(first))
        self.assertFalse({"content", "upscaled_content"} & set(first))
        self.assertEqual([i["id"] for i in self.listed("/api/images/recommendable", unit_code=UNIT)["items"]], [shown])
        self.assertEqual([i["id"] for i in self.listed("/api/images/recommendable", module_code="LM" + UNIT)["items"]], [shown])

        self.assertEqual(self.client.get(f"/api/images/recommendable/{shown}/file").status_code, 200)
        for hidden in (private, unknown, auto, bare):
            with self.subTest(hidden=hidden):
                self.assertEqual(self.client.get(f"/api/images/recommendable/{hidden}/file").status_code, 404)
                self.assertEqual(self.client.get(f"/api/images/{hidden}/file").status_code, 200, "관리용은 볼 수 있다")
        # 확정을 풀면 추천에서도 바로 빠진다
        self.post(shown, "unconfirm")
        self.assertEqual([i["id"] for i in self.listed("/api/images/recommendable")["items"]], [limited])
        self.assertEqual(self.client.get(f"/api/images/recommendable/{shown}/file").status_code, 404)

    # ── 화면에서 올려 적재 ──
    def upload(self, files: list[tuple[str, bytes]], expect: int = 200, **data) -> dict:
        response = self.client.post("/api/images/load", data=data,
                                    files=[("files", (name, content)) for name, content in files])
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def example_files(self) -> list[tuple[str, bytes]]:
        images = sorted((EXAMPLE / "images").glob("*.png"))
        for record in json.loads((EXAMPLE / "records.example.json").read_text(encoding="utf-8"))["records"]:
            self.used.append(record.get("sha256") or hashlib.sha256((EXAMPLE / record["file"]).read_bytes()).hexdigest())
        return [("records.example.json", (EXAMPLE / "records.example.json").read_bytes()),
                *[(f"C:\\고른 폴더\\{path.name}", path.read_bytes()) for path in images]]   # 브라우저가 경로를 붙여 보내도 이름만 쓴다

    def test_upload_check_then_load_the_example(self):
        files = self.example_files()
        checked = self.upload(files, check_only="true")
        self.assertEqual((checked["check_only"], checked["전체"], checked["통과"], checked["거부"]), (True, 3, 3, []))
        with psycopg.connect(DSN) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM image_assets WHERE sha256 = ANY(%s)",
                                                (self.used,)).fetchone()[0], 0, "형식 검사는 DB에 넣지 않는다")
        self.assertIn("by", self.upload(files, expect=400)["error"])
        loaded = self.upload(files, by="화면 적재")
        self.assertEqual((loaded["적재"], loaded["새 그림"], loaded["거부"], loaded["필수 항목 충족률"]), (3, 3, [], 1.0))
        found = self.client.get("/api/images", params={"q": "객실 유형 구분"}).json()["items"]
        row = next(item for item in found if item["sha256"] in self.used)
        self.assertEqual((row["has_file"], row["has_upscaled"], row["placement_count"]), (True, True, 2))
        detail = self.client.get(f"/api/images/{row['id']}").json()
        self.assertEqual(detail["history"][0]["changed_by"], "화면 적재")
        again = self.upload(files, by="화면 적재")
        self.assertEqual((again["새 그림"], again["기존 그림에 합침"]), (0, 3))

    def test_upload_reports_bad_records_and_bad_requests(self):
        content = PNG + uuid4().bytes
        self.used.append(hashlib.sha256(content).hexdigest())
        records = {"schema": "ncs-image-record/0.3", "records": [
            {"file": "images/good.png", "title": "정상", "keywords": [self.tag]},
            {"file": "images/missing.png"}, {"sha256": "a" * 64, "kind": "사진"}]}
        body = json.dumps(records).encode()
        report = self.upload([("r.json", body), ("good.png", content)], by="화면 적재")
        self.assertEqual((report["전체"], report["적재"], [item["index"] for item in report["거부"]]), (3, 1, [1, 2]))
        self.assertIn("찾을 수 없습니다", report["거부"][0]["reasons"][0])
        self.assertEqual(len(self.listed()["items"]), 1)

        self.assertIn("1개", self.upload([("good.png", content)], expect=400, by="x")["error"])
        self.assertIn("1개", self.upload([("a.json", body), ("b.json", body)], expect=400, by="x")["error"])
        self.assertIn("겹치", self.upload([("r.json", body), ("x/good.png", content), ("y/good.png", content)],
                                        expect=400, by="x")["error"])
        self.assertIn("읽지 못했습니다", self.upload([("r.json", b"{not json")], expect=400, by="x")["error"])
        self.assertIn("schema", self.upload([("r.json", b'{"schema": "other", "records": []}')], expect=400, by="x")["error"])
        # 기준 폴더 밖을 가리키는 file은 이름만 남으므로 올린 파일 밖을 읽지 못한다
        escape = json.dumps([{"file": "../../etc/passwd"}]).encode()
        report = self.upload([("r.json", escape)], by="x")
        self.assertEqual((report["적재"], len(report["거부"])), (0, 1))


    # ── 공공누리 수집 JSON(0.1-PoC, REQ-02-012) ──
    def test_upload_kogl_dataset(self):
        saved = os.environ.pop("NCS_CATALOG_FILE", None)      # 골든 테스트가 꺼 둔 NCS 목록을 이 테스트 동안만 켠다
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, "NCS_CATALOG_FILE", saved)
        data = json.loads((EXAMPLE.parent / "kogl_samples" / "kogl_samples.example.json").read_text(encoding="utf-8"))
        good, other, bad = (json.loads(json.dumps(data["items"][0])) for _ in range(3))
        contents = [PNG + uuid4().bytes, PNG + uuid4().bytes]
        self.used += [hashlib.sha256(content).hexdigest() for content in contents]
        source_id = f"KOGL-{uuid4()}"
        good.update(image_id=source_id, file={"name": "a.png", "format": "png", "width_px": 64, "height_px": 48})
        good["ncs_link"]["match_keywords"] = [self.tag, "객실"]
        other.update(image_id=f"{source_id}-2", file={"name": "b.png"})
        other["kogl"] = {"type": "제4유형", "ai_type_combined": True}
        other["ncs_link"]["match_keywords"] = [self.tag]
        bad["kogl"]["type"] = "제9유형"
        body = json.dumps({**data, "items": [good, bad, other]}, ensure_ascii=False).encode()
        files = [("수집.json", body), ("a.png", contents[0]), ("b.png", contents[1])]

        checked = self.upload(files, check_only="true")
        self.assertEqual((checked["형식"], checked["전체"], checked["통과"], [item["index"] for item in checked["거부"]]),
                         ("공공누리 수집 JSON(0.1-PoC)", 3, 2, [1]))
        self.assertEqual(self.listed()["items"], [], "형식 검사는 DB에 넣지 않는다")
        loaded = self.upload(files, by="수집 담당")
        self.assertEqual((loaded["전체"], loaded["적재"], loaded["새 그림"], [item["index"] for item in loaded["거부"]],
                          loaded["추가된 수행준거 연결"], loaded["필수 항목 충족률"]), (3, 2, 2, [1], 2, 0.6667))   # 거부된 1건은 충족하지 못한 것으로 센다
        again = self.upload(files, by="수집 담당")
        self.assertEqual((again["새 그림"], again["기존 그림에 합침"], again["추가된 수행준거 연결"]), (0, 2, 0))

        rows = {row["source_id"]: row for row in self.listed()["items"]}
        self.assertEqual(set(rows), {source_id, f"{source_id}-2"})
        self.assertEqual([row["source_id"] for row in self.client.get("/api/images", params={"q": source_id + "-2"}).json()["items"]],
                         [f"{source_id}-2"], "수집 번호로 찾을 수 있다")
        detail = self.client.get(f"/api/images/{rows[source_id]['id']}").json()
        rights = detail["rights"]
        self.assertEqual((rights["status"], rights["category"], rights["ownership"], rights["license_scheme"], rights["kogl_type"],
                          rights["attribution"], rights["non_commercial"], rights["source_org"], rights["retrieved_on"]),
                         ("auto", "public_license", "kogl", "kogl", 1, True, False, "예시기관", "2026-11-17"))
        self.assertEqual(rights["credit_line"], "공공누리 홈페이지(https://www.kogl.or.kr/)에서 2026. 11. 17. 검색. 공공누리 제1유형.")
        self.assertEqual((detail["placements"], [(link["unit_code"], link["criterion_no"]) for link in detail["links"]]),
                         ([], [(UNIT, "1.1")]))
        fourth = self.client.get(f"/api/images/{rows[source_id + '-2']['id']}").json()["rights"]
        self.assertEqual((fourth["kogl_type"], fourth["kogl_ai"], fourth["non_commercial"], fourth["no_derivatives"], fourth["release_class"]),
                         (4, True, True, True, "inherit"))
        # 자동 적재분은 추천에 나오지 않고, 기관이 재사용 범위를 정해 확정해야 나온다
        self.assertEqual(self.listed("/api/images/recommendable")["items"], [])
        image_id = rows[source_id]["id"]
        self.post(image_id, "rights", version=rights["version"], rights={"reuse_scope": "all"})
        self.post(image_id, "confirm")
        self.assertEqual([row["id"] for row in self.listed("/api/images/recommendable")["items"]], [image_id])
        # 확정 뒤 다시 적재해도 확정 내용은 그대로
        after = self.upload(files, by="수집 담당")
        self.assertEqual(len(after["확정 유지"]), 1)


if __name__ == "__main__":
    unittest.main()
