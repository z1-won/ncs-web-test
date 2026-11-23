"""스키마 마이그레이션 목록의 규약 검사. DB 없이 SQL 텍스트와 목록 구조만 본다.

실제 적용은 tests/integration/test_postgres_integration.py(NCS_TEST_DATABASE_URL 필요)가 검사한다.
"""

import re
import unittest

from ncs_service.images import image_terms
from ncs_service.migrations import IMAGE_DB, MIGRATIONS, SCHEMA


class MigrationListTests(unittest.TestCase):
    def test_names_are_numbered_unique_and_ordered(self):
        names = [name for name, _ in MIGRATIONS]
        self.assertEqual(len(names), len(set(names)), "마이그레이션 이름이 중복됩니다")
        numbers = []
        for name in names:
            match = re.fullmatch(r"(\d{3})_[a-z0-9_]+", name)
            self.assertIsNotNone(match, f"이름은 'NNN_snake_case' 형식이어야 합니다: {name}")
            numbers.append(int(match.group(1)))
        self.assertEqual(numbers, sorted(numbers), "번호는 오름차순이어야 합니다")
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)), "번호는 001부터 빈틈없이 이어져야 합니다")

    def test_first_migration_is_the_initial_schema(self):
        self.assertEqual(MIGRATIONS[0], ("001_initial", SCHEMA))

    def test_engine_list_is_not_encoded_in_the_schema(self):
        """check_name의 허용값은 registry.ENGINES가 검증한다. SQL에 다시 적으면 엔진 추가마다 DB를 바꿔야 한다."""
        for name, sql in MIGRATIONS:
            self.assertNotRegex(sql, r"check_name\s+text[^,]*CHECK", f"{name}: check_name에 CHECK 제약이 있습니다")
            for engine_name in ("position", "toc", "overview", "knowledge"):
                self.assertNotIn(f"'{engine_name}'", sql, f"{name}: 엔진 이름이 SQL에 직접 적혀 있습니다")

    def test_every_statement_is_idempotent_or_guarded(self):
        """시작할 때마다 migrate()가 돌아도 안전해야 하므로 CREATE/ALTER는 IF (NOT) EXISTS를 쓴다."""
        for name, sql in MIGRATIONS:
            for statement in filter(None, (part.strip() for part in sql.split(";"))):
                head = statement.split()[0].upper()
                if head in ("CREATE", "ALTER", "DROP"):
                    # 뷰는 IF NOT EXISTS가 없어 CREATE OR REPLACE로 다시 돌려도 안전하게 한다
                    self.assertRegex(statement, r"IF (NOT )?EXISTS|^CREATE OR REPLACE VIEW",
                                     f"{name}: 보호 절이 없습니다: {statement[:60]}")


def allowed_values(sql: str, table: str, column: str) -> set[str]:
    """CREATE TABLE <table> 안에서 '<column> … CHECK (<column> IN (…))'에 적힌 값들."""
    body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", sql, re.S)
    assert body, f"{table} 정의를 찾지 못했습니다"
    found = re.search(rf"^\s*{column} text[^\n]*CHECK \({column} IN \(([^)]*)\)\)", body.group(1), re.M)
    assert found, f"{table}.{column}의 허용값 CHECK를 찾지 못했습니다"
    return set(re.findall(r"'([a-z0-9_-]+)'", found.group(1)))


class ImageDbSchemaTests(unittest.TestCase):
    """006_image_db(REQ-02-010): 허용값이 ncs_service.images.image_terms와 같고, 필요한 표·뷰가 모두 있다."""

    def test_migration_is_registered(self):
        self.assertIn(("006_image_db", IMAGE_DB), MIGRATIONS)

    def test_tables_and_view_exist(self):
        for table in ("image_assets", "image_placements", "image_rights", "image_evidence", "image_ncs_links",
                      "image_history"):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table} (", IMAGE_DB)
        self.assertIn("CREATE OR REPLACE VIEW v_image_recommendable", IMAGE_DB)

    def test_allowed_values_match_image_terms(self):
        cases = [
            ("image_assets", "kind", image_terms.KIND),
            ("image_rights", "status", image_terms.STATUS),
            ("image_rights", "category", image_terms.CATEGORY),
            ("image_rights", "ownership", image_terms.OWNERSHIP),
            ("image_rights", "reuse_scope", image_terms.REUSE_SCOPE),
            ("image_rights", "release_class", image_terms.RELEASE_CLASS),
            ("image_rights", "license_scheme", image_terms.LICENSE_SCHEME),
            ("image_rights", "cc_license", image_terms.CC_LICENSE),
            ("image_rights", "ai_mode", image_terms.AI_MODE),
            ("image_evidence", "kind", image_terms.EVIDENCE_KIND),
            ("image_history", "action", image_terms.HISTORY_ACTION),
        ]
        for table, column, terms in cases:
            with self.subTest(column=f"{table}.{column}"):
                self.assertEqual(allowed_values(IMAGE_DB, table, column), set(terms))

    def test_ai_usage_and_kogl_tables_agree_with_the_constraints(self):
        """SQL의 '1·4는 생성', '2·4는 상업적 이용금지', '3·4는 변경금지'와 image_terms의 표가 같은 말을 한다."""
        self.assertEqual({no for no, (_, mode) in image_terms.AI_USAGE.items() if mode == "generated"}, {1, 4})
        self.assertIn("(ai_mode = 'generated') = (ai_usage IN (1, 4))", IMAGE_DB)
        self.assertEqual(set(image_terms.AI_USAGE), set(range(1, 6)))
        self.assertEqual({mode for _, mode in image_terms.AI_USAGE.values()}, set(image_terms.AI_MODE))
        for kogl_type, (attribution, non_commercial, no_derivatives) in image_terms.KOGL_CONDITIONS.items():
            self.assertEqual(attribution, kogl_type >= 1)
            self.assertEqual(non_commercial, kogl_type in (2, 4))
            self.assertEqual(no_derivatives, kogl_type in (3, 4))
        self.assertEqual(set(image_terms.KOGL_CONDITIONS), set(range(0, 5)))
        for code, (attribution, non_commercial, no_derivatives, share_alike) in image_terms.CC_LICENSE.items():
            parts = code.split("-")
            self.assertEqual(attribution, code != "cc0")
            self.assertEqual((non_commercial, no_derivatives, share_alike), ("nc" in parts, "nd" in parts, "sa" in parts))

    def test_named_constraints_do_not_collide_with_column_checks(self):
        """열에 붙인 CHECK는 PostgreSQL이 <표>_<열>_check로 이름 짓는다. 같은 이름의 CONSTRAINT를 또 만들면 적용이 실패한다."""
        for table, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", IMAGE_DB, re.S):
            automatic = {f"{table}_{column}_check" for column in re.findall(r"^\s*(\w+) [a-z][^\n]*CHECK \(", body, re.M)}
            named = re.findall(r"CONSTRAINT (\w+) CHECK", body)
            self.assertEqual(len(named), len(set(named)), f"{table}: 제약 이름이 중복됩니다")
            self.assertFalse(automatic & set(named), f"{table}: 열 CHECK의 자동 이름과 겹칩니다")

    def test_recommendable_view_excludes_unconfirmed_and_unknown_scope(self):
        view = IMAGE_DB[IMAGE_DB.index("CREATE OR REPLACE VIEW"):]
        self.assertIn("r.status = 'confirmed'", view)
        self.assertIn("r.reuse_scope <> 'unknown'", view)
        columns = view[:view.index("FROM image_assets")]
        self.assertNotRegex(columns, r"a\.(upscaled_)?content\s*[,\n]", "추천 목록에 그림 파일 내용을 싣지 않는다")


if __name__ == "__main__":
    unittest.main()
