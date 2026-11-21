"""계정과 로그인(ncs_service.accounts, ncs_web.auth) — 비밀번호 해시, 로그인 실패 제한, DB 없는 서버(로그인 없음), 역할 허용값."""

import re
import tempfile
import unittest

from ncs_service.accounts import MIN_PASSWORD, ROLES, hash_password, token_hash, verify_password
from ncs_service.migrations import MIGRATIONS
from ncs_web.auth import OPEN_PATHS, Throttle


class PasswordTests(unittest.TestCase):
    def test_hash_is_salted_and_verifies(self):
        first, second = hash_password("correct horse 배터리"), hash_password("correct horse 배터리")
        self.assertNotEqual(first, second)                               # 소금이 달라 같은 비밀번호도 값이 다르다
        self.assertTrue(first.startswith("scrypt$"))
        self.assertNotIn("correct horse", first)
        self.assertTrue(verify_password("correct horse 배터리", first))
        self.assertFalse(verify_password("correct horse 배터리!", first))

    def test_short_password_and_broken_hash(self):
        with self.assertRaises(ValueError):
            hash_password("a" * (MIN_PASSWORD - 1))
        for broken in ("", "plain", "scrypt$x$8$1$AA==$AA==", "md5$1$1$1$AA==$AA=="):
            self.assertFalse(verify_password("anything-long", broken))

    def test_session_token_is_stored_as_hash(self):
        self.assertEqual(len(token_hash("abc")), 64)
        self.assertNotEqual(token_hash("abc"), "abc")


class ThrottleTests(unittest.TestCase):
    def test_locks_after_limit_and_unlocks_after_time(self):
        now = [0.0]
        throttle = Throttle(limit=3, seconds=60, clock=lambda: now[0])
        for _ in range(3):
            self.assertFalse(throttle.locked("kim"))
            throttle.failed("kim")
        self.assertTrue(throttle.locked("kim"))
        self.assertFalse(throttle.locked("lee"))                         # 아이디마다 따로 센다
        now[0] = 61
        self.assertFalse(throttle.locked("kim"))
        throttle.failed("kim")
        throttle.passed("kim")                                           # 성공하면 지운다
        self.assertEqual(throttle.fails, {})


class RoleTests(unittest.TestCase):
    def test_roles_match_the_database_constraint(self):
        sql = dict(MIGRATIONS)["012_accounts"]
        allowed = set(re.findall(r"'(\w+)'", re.search(r"role IN \(([^)]*)\)", sql).group(1)))
        self.assertEqual(allowed, set(ROLES))


class WithoutDatabaseTests(unittest.TestCase):
    def test_server_without_database_has_no_login(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(out_dir=folder)) as client:
                self.assertEqual(client.get("/api/me").json(), {"auth": False, "account": None})
                self.assertEqual(client.get("/api/health").status_code, 200)     # 막히지 않는다
                self.assertEqual(client.post("/api/login", json={"login": "a", "password": "b"}).status_code, 400)
            with self.assertRaises(ValueError):
                create_app(out_dir=folder, require_login=True)                    # 계정을 둘 곳이 없다
        self.assertIn("/api/login", OPEN_PATHS)


if __name__ == "__main__":
    unittest.main()
