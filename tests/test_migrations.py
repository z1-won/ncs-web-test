"""스키마 마이그레이션 목록의 규약 검사. DB 없이 SQL 텍스트와 목록 구조만 본다.

실제 적용은 tests/test_postgres_integration.py(NCS_TEST_DATABASE_URL 필요)가 검사한다.
"""

import re
import unittest

from ncs_service.postgres import MIGRATIONS, SCHEMA


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
                    self.assertRegex(statement, r"IF (NOT )?EXISTS", f"{name}: 보호 절이 없습니다: {statement[:60]}")


if __name__ == "__main__":
    unittest.main()
