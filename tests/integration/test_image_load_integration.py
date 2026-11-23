"""NCS_TEST_DATABASE_URL을 지정하면 이미지 레코드 적재(ncs_service.images.image_db)를 실제 PostgreSQL에서 검사한다.

적재는 스스로 커밋하므로 테스트가 넣은 그림은 끝날 때 sha256으로 찾아 지운다(딸린 행은 함께 지워진다).
"""

import copy
import hashlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg

from ncs_service.images.image_db import load_file, load_records
from ncs_service.images.image_records import read_records
from ncs_service.postgres import migrate

DSN = os.getenv("NCS_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "examples" / "image_records" / "records.example.json"
UNIT = "1203020201_24v3"


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class ImageLoadIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.used: set[str] = set()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_assets WHERE sha256 = ANY(%s)", (list(self.used),))

    def record(self, **fields) -> dict:
        """테스트마다 다른 그림(내용이 다른 바이트) 1건."""
        content = f"image-{uuid4()}".encode()
        self.used.add(hashlib.sha256(content).hexdigest())
        return {"content": content, **fields}

    def load(self, *records, by: str = "테스트"):
        return load_records(DSN, list(records), changed_by=by)

    def one(self, sql: str, *params):
        with psycopg.connect(DSN) as connection:
            return connection.execute(sql, params).fetchone()

    def sha(self, record: dict) -> str:
        return hashlib.sha256(record["content"]).hexdigest()

    def rights(self, record: dict, columns: str):
        return self.one(f"SELECT {columns} FROM image_rights r JOIN image_assets a ON a.id = r.image_id WHERE a.sha256 = %s",
                        self.sha(record))

    def counts(self, record: dict) -> tuple:
        return self.one(
            "SELECT (SELECT count(*) FROM image_placements p WHERE p.image_id = a.id), "
            "(SELECT count(*) FROM image_ncs_links l WHERE l.image_id = a.id), "
            "(SELECT count(*) FROM image_history h WHERE h.image_id = a.id), "
            "(SELECT count(*) FROM image_rights r WHERE r.image_id = a.id) FROM image_assets a WHERE a.sha256 = %s",
            self.sha(record))

    def confirm(self, record: dict):
        with psycopg.connect(DSN) as connection:
            connection.execute(
                "UPDATE image_rights SET status = 'confirmed', confirmed_by = '에디팅기관', confirmed_at = now(), "
                "ownership = 'government', reuse_scope = 'all' "
                "WHERE image_id = (SELECT id FROM image_assets WHERE sha256 = %s)", (self.sha(record),))

    # ── 문서의 예시 파일 ──
    def test_example_file_loads_and_reloads_without_duplicates(self):
        records, base = read_records(EXAMPLE)
        for record in records:
            self.used.add(record.get("sha256") or hashlib.sha256((base / record["file"]).read_bytes()).hexdigest())
        first = load_file(DSN, EXAMPLE, changed_by="테스트")
        self.assertEqual((first.total, first.created, first.merged, first.rejected), (3, 3, 0, []))
        self.assertEqual((first.placements_added, first.links_added, first.acceptance_rate), (2, 3, 1.0))
        figure = hashlib.sha256((base / "images" / "figure_1-1.png").read_bytes()).hexdigest()
        row = self.one("SELECT content, upscaled_width_px, keywords FROM image_assets WHERE sha256 = %s", figure)
        self.assertEqual((bytes(row[0]), row[1], row[2]),
                         ((base / "images" / "figure_1-1.png").read_bytes(), 192, ["객실", "객실 유형", "예약"]))
        # 수행준거 연결이 자기 수록 위치를 가리킨다
        linked = self.one(
            "SELECT p.module_code FROM image_ncs_links l JOIN image_placements p ON p.id = l.placement_id "
            "JOIN image_assets a ON a.id = l.image_id WHERE a.sha256 = %s AND l.criterion_no = '1.1'", figure)
        self.assertEqual(linked, ("LM1203020201_24v3",))

        second = load_file(DSN, EXAMPLE, changed_by="테스트")
        self.assertEqual((second.created, second.merged, second.placements_added, second.links_added,
                          second.rights_updated, second.rejected), (0, 3, 0, 0, 0, []))
        totals = self.one(
            "SELECT count(*), (SELECT count(*) FROM image_placements p JOIN image_assets x ON x.id = p.image_id "
            "WHERE x.sha256 = ANY(%s)), (SELECT count(*) FROM image_history h JOIN image_assets x ON x.id = h.image_id "
            "WHERE x.sha256 = ANY(%s)) FROM image_assets WHERE sha256 = ANY(%s)",
            list(self.used), list(self.used), list(self.used))
        self.assertEqual(totals, (3, 2, 3), "다시 넣어도 그림 3·수록 위치 2·이력 3(등록)에서 늘지 않아야 한다")
        # 자동 태깅만 된 것은 추천에 나오지 않는다
        self.assertEqual(self.one("SELECT count(*) FROM v_image_recommendable WHERE sha256 = ANY(%s)", list(self.used)), (0,))

    # ── 그림 파일 ──
    def test_existing_values_are_kept_and_blanks_filled(self):
        record = self.record(title="처음 제목", keywords=["객실"])
        self.load(record)
        again = {**record, "title": "나중 제목", "kind": "photo", "keywords": ["예약", "객실"],
                 "upscaled": {"content": b"upscaled-1", "engine": "esrgan-fast"}}
        self.assertEqual(self.load(again).merged, 1)
        row = self.one("SELECT title, kind, keywords, upscaled_content, upscale_engine FROM image_assets WHERE sha256 = %s",
                       self.sha(record))
        self.assertEqual((row[0], row[1], row[2], bytes(row[3]), row[4]),
                         ("처음 제목", "photo", ["객실", "예약"], b"upscaled-1", "esrgan-fast"))
        self.load({**record, "upscaled": {"content": b"upscaled-2", "engine": "다른 엔진"}})     # 업스케일본은 처음 것 유지
        row = self.one("SELECT upscaled_content, upscale_engine FROM image_assets WHERE sha256 = %s", self.sha(record))
        self.assertEqual((bytes(row[0]), row[1]), (b"upscaled-1", "esrgan-fast"))

    # ── 수록 위치 ──
    def test_new_placements_are_added_and_same_spot_is_corrected(self):
        record = self.record(placements=[{"module_code": "LM" + UNIT, "label": "그림 1-1", "caption": "틀린 캡션", "page": 12}])
        self.load(record)
        again = copy.deepcopy(record)
        again["placements"] = [{"module_code": "LM" + UNIT, "label": "그림 1-1", "caption": "바로잡은 캡션"},
                               {"module_code": "LM1203020202_24v3", "label": "그림 2-3"}]
        report = self.load(again)
        self.assertEqual((report.merged, report.placements_added), (1, 1))
        self.assertEqual(self.counts(record)[0], 2)
        row = self.one("SELECT p.caption, p.page FROM image_placements p JOIN image_assets a ON a.id = p.image_id "
                       "WHERE a.sha256 = %s AND p.label = '그림 1-1'", self.sha(record))
        self.assertEqual(row, ("바로잡은 캡션", 12), "적은 값은 고치고, 적지 않은 값(쪽)은 그대로")

    # ── 권리 정보 ──
    def test_auto_tagged_rights_are_updated_with_history(self):
        record = self.record(rights={"category": "public_license", "license": {"kogl_type": 1}, "source_org": "○○청"})
        self.load(record)
        self.assertEqual(self.rights(record, "status, version, kogl_type, non_commercial, reuse_scope"),
                         ("auto", 1, 1, False, "unknown"))
        changed = {**record, "rights": {"license": {"kogl_type": 2, "kogl_ai": True}}}
        report = self.load(changed, by="김담당")
        self.assertEqual(report.rights_updated, 1)
        # 적지 않은 묶음(category·source_org)은 그대로, license 묶음만 바뀐다
        self.assertEqual(self.rights(record, "status, version, kogl_type, kogl_ai, non_commercial, category, source_org"),
                         ("auto", 2, 2, True, True, "public_license", "○○청"))
        history = self.one(
            "SELECT h.changed_by, h.version, h.changes FROM image_history h JOIN image_assets a ON a.id = h.image_id "
            "WHERE a.sha256 = %s AND h.action = 'updated'", self.sha(record))
        self.assertEqual(history, ("김담당", 2, {"kogl_type": [1, 2], "kogl_ai": [False, True], "non_commercial": [False, True]}))
        self.assertEqual(self.load(changed).rights_updated, 0, "같은 값을 다시 넣으면 버전이 오르지 않는다")
        self.assertEqual(self.rights(record, "version"), (2,))

    def test_confirmed_rights_are_never_overwritten(self):
        record = self.record(rights={"category": "author_made", "author": "집필진"},
                             placements=[{"module_code": "LM" + UNIT, "label": "그림 1-1"}])
        self.load(record)
        self.confirm(record)
        again = {**record, "rights": {"category": "prior_module", "author": "다른 사람", "license": {"kogl_type": 4}},
                 "placements": [{"module_code": "LM1203020202_24v3", "label": "그림 3-1"}],
                 "links": [{"unit_code": UNIT}]}
        report = self.load(again)
        self.assertEqual((report.merged, report.rights_updated, report.kept_confirmed, report.rejected),
                         (1, 0, [self.sha(record)], []))
        self.assertEqual(self.rights(record, "status, version, category, author, kogl_type, reuse_scope"),
                         ("confirmed", 1, "author_made", "집필진", None, "all"))
        self.assertEqual(self.counts(record)[:2], (2, 1), "확정된 그림에도 새 수록 위치와 수행준거 연결은 추가된다")
        self.assertEqual(self.one("SELECT count(*) FROM v_image_recommendable WHERE sha256 = %s", self.sha(record)), (1,))

    # ── 거부 ──
    def test_bad_records_are_reported_and_do_not_block_the_rest(self):
        good, other = self.record(title="정상"), self.record(title="정상 2")
        bad_shape = self.record(kind="사진")
        report = self.load(good, bad_shape, "레코드가 아님", other)
        self.assertEqual((report.total, report.accepted, report.acceptance_rate), (4, 2, 0.5))
        self.assertEqual([item["index"] for item in report.rejected], [1, 2])
        self.assertIn("허용값이 아닙니다", report.rejected[0]["reasons"][0])
        self.assertIsNone(self.one("SELECT 1 FROM image_assets WHERE sha256 = %s", self.sha(bad_shape)))
        self.assertIsNotNone(self.one("SELECT 1 FROM image_assets WHERE sha256 = %s", self.sha(other)))
        self.assertEqual(report.as_dict()["필수 항목 충족률"], 0.5)

    def test_database_refusal_rolls_back_only_that_record(self):
        """형식 검사를 통과했지만 DB 제약에 걸리는 건 — 그 건의 그림·수록 위치까지 모두 되돌린다."""
        good = self.record()
        # 검사가 모르는 조합: 귀속은 그대로 두고 이미 공공누리 조건(kogl)인 권리에서 유형만 지우는 갱신
        victim = self.record(rights={"ownership": "kogl", "license": {"kogl_type": 1}},
                             placements=[{"module_code": "LM" + UNIT, "label": "그림 1-1"}])
        self.load(victim)
        clash = {**victim, "rights": {"license": {"scheme": "other", "note": "유형 삭제"}},
                 "placements": [{"module_code": "LM" + UNIT, "label": "그림 9-9"}], "links": [{"unit_code": UNIT}]}
        report = self.load(clash, good)
        self.assertEqual((report.accepted, report.created, report.placements_added, report.links_added,
                          report.rights_updated), (1, 1, 0, 0, 0))
        self.assertEqual(len(report.rejected), 1)
        self.assertIn("image_rights_kogl_ownership_check", report.rejected[0]["reasons"][0])
        self.assertEqual(self.counts(victim), (1, 0, 1, 1), "거부된 건의 수록 위치·연결·이력이 남으면 안 된다")
        self.assertEqual(self.rights(victim, "kogl_type, version"), (1, 1))

    def test_changed_by_is_required(self):
        with self.assertRaises(ValueError):
            load_records(DSN, [], changed_by=" ")

    def test_cli_loads_the_example_and_prints_the_report(self):
        records, base = read_records(EXAMPLE)
        for record in records:
            self.used.add(record.get("sha256") or hashlib.sha256((base / record["file"]).read_bytes()).hexdigest())
        env = {**os.environ, "DATABASE_URL": DSN}
        done = subprocess.run([sys.executable, "-m", "ncs_service.images.image_db", str(EXAMPLE), "--by", "테스트"],
                              env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('"필수 항목 충족률": 1.0', done.stdout)
        missing = subprocess.run([sys.executable, "-m", "ncs_service.images.image_db", str(EXAMPLE)],
                                 env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(missing.returncode, 2)


if __name__ == "__main__":
    unittest.main()
