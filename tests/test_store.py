"""저장소 선택과 FileStore 동작. PostgresStore의 실제 저장은 test_postgres*.py가 검사한다."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ncs_service import FileStore, PostgresStore, ReviewRequest, StoredReview, execute_review, open_store

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"


class StoreSelectionTests(unittest.TestCase):
    def test_database_url_decides_the_store(self):
        self.assertIsInstance(open_store(out_dir="x"), FileStore)
        self.assertIsInstance(open_store(out_dir="x", database_url=None), FileStore)
        self.assertIsInstance(open_store(out_dir="x", database_url="postgresql://example"), PostgresStore)

    def test_both_stores_share_the_same_call_shape(self):
        for store in (FileStore("x"), PostgresStore("postgresql://example")):
            with self.subTest(store=type(store).__name__):
                for name in ("supports_history", "prepare", "save"):
                    self.assertTrue(hasattr(store, name), f"{type(store).__name__}.{name}")
        self.assertFalse(FileStore("x").supports_history)
        self.assertTrue(PostgresStore("postgresql://example").supports_history)
        for name in ("list_reviews", "get_review", "export_zip", "delete_review"):
            self.assertTrue(callable(getattr(PostgresStore("postgresql://example"), name)))


class FileStoreTests(unittest.TestCase):
    def test_group_runs_are_saved_under_the_group_folder(self):
        review = execute_review(ReviewRequest((MANUSCRIPT, PLAN), "toc"))
        with tempfile.TemporaryDirectory() as folder:
            store = FileStore(Path(folder) / "결과")
            stored = store.save(review, [], group_id="11111111-2222-3333-4444-555555555555")
            self.assertEqual(stored.directory.parent, (Path(folder) / "결과" / "11111111-2222-3333-4444-555555555555").resolve())   # ← 이 줄
            self.assertTrue(stored.zip_path.is_file())

    def test_save_writes_run_folder_and_reports_paths(self):
        review = execute_review(ReviewRequest((MANUSCRIPT, PLAN), "toc"))
        with tempfile.TemporaryDirectory() as folder:
            store = FileStore(Path(folder) / "결과")
            store.prepare()
            stored = store.save(review, [(MANUSCRIPT.name, MANUSCRIPT), (PLAN.name, PLAN)])
            self.assertIsInstance(stored, StoredReview)
            self.assertIsNone(stored.run_id, "파일 저장소는 이력 id가 없다")
            self.assertTrue(stored.directory.is_dir() and stored.directory.parent == store.out_dir)
            self.assertTrue(stored.zip_path.is_file())
            self.assertIn("검수결과", stored.summary)
            self.assertFalse(hasattr(store, "list_reviews"), "파일 저장소는 이력 조회를 제공하지 않는다")

    def test_save_ignores_uploads_argument(self):
        review = execute_review(ReviewRequest((MANUSCRIPT, PLAN), "toc"))
        with tempfile.TemporaryDirectory() as folder:
            a = FileStore(Path(folder) / "a").save(review)
            b = FileStore(Path(folder) / "b").save(review, [("x.hwpx", MANUSCRIPT)])
            self.assertEqual(a.summary, b.summary)


@unittest.skipUnless(importlib.util.find_spec("psycopg"), "psycopg 미설치(web extra 없음)")
class PostgresStoreDelegationTests(unittest.TestCase):
    """DB 없이 호출 모양만 본다: 모듈 함수에 dsn과 인자를 그대로 넘기는가. 패치 대상 모듈이 psycopg를 import하므로 web extra가 필요하다."""

    def test_save_passes_dsn_review_and_input_metadata(self):
        review = execute_review(ReviewRequest((MANUSCRIPT, PLAN), "position"))
        store = PostgresStore("postgresql://example")
        with patch("ncs_service.postgres.save_review", return_value=("run-1", {"검수결과": "적합", "항목": {}})) as save:
            stored = store.save(review, [(MANUSCRIPT.name, MANUSCRIPT), (PLAN.name, PLAN)])
        self.assertEqual(stored, StoredReview({"검수결과": "적합", "항목": {}}, run_id="run-1"))
        dsn, passed_review, inputs, group_id = save.call_args.args
        self.assertEqual((dsn, passed_review, group_id), ("postgresql://example", review, None))
        self.assertEqual({item["role"] for item in inputs}, {"manuscript", "plan"})
        with patch("ncs_service.postgres.save_review", return_value=("run-2", {"검수결과": "적합", "항목": {}})) as save:
            store.save(review, [(MANUSCRIPT.name, MANUSCRIPT), (PLAN.name, PLAN)], group_id="g-1")
        self.assertEqual(save.call_args.args[3], "g-1")

    def test_group_methods_delegate_to_postgres(self):
        store = PostgresStore("postgresql://example")
        with patch("ncs_service.postgres.list_groups", return_value=[{"group_id": "g"}]) as groups, \
             patch("ncs_service.postgres.get_group", return_value={"group_id": "g", "runs": []}) as group, \
             patch("ncs_service.postgres.delete_group", return_value=True) as delete:
            self.assertEqual(store.list_groups(module_code="LM1", limit=5, offset=0), [{"group_id": "g"}])
            self.assertEqual(store.get_group("g")["group_id"], "g")
            self.assertTrue(store.delete_group("g"))
        groups.assert_called_once_with("postgresql://example", module_code="LM1", limit=5, offset=0)
        group.assert_called_once_with("postgresql://example", "g")
        delete.assert_called_once_with("postgresql://example", "g")

    def test_group_verdict_prefers_fail_then_undecided(self):
        from ncs_service.postgres import group_verdict

        self.assertEqual(group_verdict(["적합", "판단불가", "부적합"]), "부적합")
        self.assertEqual(group_verdict(["적합", "판단불가"]), "판단불가")
        self.assertEqual(group_verdict(["적합", "적합"]), "적합")
        self.assertEqual(group_verdict([]), "미검사")

    def test_export_zip_rebuilds_from_history_with_the_engine(self):
        review = execute_review(ReviewRequest((MANUSCRIPT, PLAN), "position"))
        found = {"check": "position", "module_code": review.result.module_code, "전체": review.result.checklist,
                 "지적사항": review.result.findings, "진단": review.result.diagnostics, "검수확인서": review.result.sheet}
        store = PostgresStore("postgresql://example")
        with patch("ncs_service.postgres.get_review", return_value=found):
            content, filename = store.export_zip("run-1")
        self.assertTrue(content.startswith(b"PK"), "ZIP 서명")
        self.assertTrue(filename.endswith("_위치_검수결과.zip"), filename)
        with patch("ncs_service.postgres.get_review", return_value=None):
            self.assertIsNone(store.export_zip("missing"))

    def test_delete_review_delegates_to_postgres(self):
        store = PostgresStore("postgresql://example")
        with patch("ncs_service.postgres.delete_review", return_value=True) as delete:
            self.assertTrue(store.delete_review("run-1"))
        delete.assert_called_once_with("postgresql://example", "run-1")


if __name__ == "__main__":
    unittest.main()
