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
        for name in ("list_reviews", "get_review", "export_zip"):
            self.assertTrue(callable(getattr(PostgresStore("postgresql://example"), name)))


class FileStoreTests(unittest.TestCase):
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
        dsn, passed_review, inputs = save.call_args.args
        self.assertEqual((dsn, passed_review), ("postgresql://example", review))
        self.assertEqual({item["role"] for item in inputs}, {"manuscript", "plan"})

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


if __name__ == "__main__":
    unittest.main()
