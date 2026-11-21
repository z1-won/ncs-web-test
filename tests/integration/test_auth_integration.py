"""NCS_TEST_DATABASE_URL을 지정하면 계정·로그인·API 막기를 실제 PostgreSQL로 검사한다."""

import os
import unittest

import psycopg
from fastapi.testclient import TestClient

from ncs_service import accounts
from ncs_service.postgres import migrate
from ncs_web.auth import COOKIE
from ncs_web.server import create_app

DSN = os.getenv("NCS_TEST_DATABASE_URL")
LOGIN, PASSWORD = "auth-test-editor", "시험용 비밀번호 1234"


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class AuthIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.clean()
        self.account = accounts.create_account(DSN, login=LOGIN.upper(), name="김에디터", role="editor", org="에디팅기관", password=PASSWORD)

    def tearDown(self):
        self.clean()

    def clean(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM accounts WHERE login LIKE 'auth-test-%'")

    def test_accounts(self):
        self.assertEqual((self.account["login"], self.account["role_name"]), (LOGIN, "에디터"))       # 아이디는 소문자로
        with self.assertRaises(ValueError):
            accounts.create_account(DSN, login=LOGIN, name="중복", role="editor", password=PASSWORD)
        with self.assertRaises(ValueError):
            accounts.create_account(DSN, login="auth-test-x", name="역할", role="boss", password=PASSWORD)
        with psycopg.connect(DSN) as connection:
            stored = connection.execute("SELECT password_hash FROM accounts WHERE login = %s", (LOGIN,)).fetchone()[0]
        self.assertNotIn(PASSWORD, stored)
        self.assertIsNone(accounts.log_in(DSN, LOGIN, "틀린 비밀번호"))
        self.assertIsNone(accounts.log_in(DSN, "auth-test-nobody", PASSWORD))
        token, account = accounts.log_in(DSN, LOGIN, PASSWORD)
        self.assertEqual(accounts.session_account(DSN, token)["id"], account["id"])
        with psycopg.connect(DSN) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM account_sessions WHERE token_hash = %s", (token,)).fetchone())   # 토큰 원문은 없다
        self.assertTrue(accounts.set_active(DSN, LOGIN, False))                                       # 막으면 세션도 끊긴다
        self.assertIsNone(accounts.session_account(DSN, token))
        self.assertIsNone(accounts.log_in(DSN, LOGIN, PASSWORD))
        accounts.set_active(DSN, LOGIN, True)
        token, _ = accounts.log_in(DSN, LOGIN, PASSWORD)
        self.assertTrue(accounts.set_password(DSN, LOGIN, "새 비밀번호 5678"))                            # 바꾸면 세션이 끊긴다
        self.assertIsNone(accounts.session_account(DSN, token))
        self.assertIsNotNone(accounts.log_in(DSN, LOGIN, "새 비밀번호 5678"))

    def test_api_requires_login(self):
        with TestClient(create_app(database_url=DSN)) as client:            # DB가 있으면 로그인이 켜진다
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(client.get("/api/me").status_code, 401)
            for path in ("/api/reviews", "/api/manuscripts", "/api/volumes", "/api/images"):
                self.assertEqual(client.get(path).status_code, 401, path)
            self.assertEqual(client.post("/api/review", data={"check": "toc"}).status_code, 401)
            self.assertEqual(client.post("/api/login", json={"login": LOGIN, "password": "틀림"}).status_code, 401)
            done = client.post("/api/login", json={"login": LOGIN, "password": PASSWORD})
            self.assertEqual(done.status_code, 200, done.text)
            self.assertNotIn("password", done.text)
            cookie = done.headers["set-cookie"].lower()
            self.assertIn("httponly", cookie)
            self.assertIn("samesite=strict", cookie)
            self.assertEqual(client.get("/api/me").json()["account"]["name"], "김에디터")
            self.assertEqual(client.get("/api/manuscripts").status_code, 200)
            self.assertEqual(client.post("/api/logout").status_code, 200)
            self.assertEqual(client.get("/api/manuscripts").status_code, 401)
            client.cookies.set(COOKIE, "made-up-token")
            self.assertEqual(client.get("/api/manuscripts").status_code, 401)

    def test_login_is_locked_after_repeated_failures(self):
        with TestClient(create_app(database_url=DSN)) as client:
            for _ in range(5):
                self.assertEqual(client.post("/api/login", json={"login": LOGIN, "password": "틀림"}).status_code, 401)
            self.assertEqual(client.post("/api/login", json={"login": LOGIN, "password": PASSWORD}).status_code, 429)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class StageMarkByAccountTests(unittest.TestCase):
    """단계 완료 표시의 '누가'는 로그인한 계정에서 읽는다 — 화면이 다른 이름을 보내도 쓰지 않는다."""
    CODE = "LM9999999904_26v1"

    def setUp(self):
        migrate(DSN)
        self.clean()
        accounts.create_account(DSN, login=LOGIN, name="김에디터", role="editor", password=PASSWORD)

    def tearDown(self):
        self.clean()

    def clean(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM accounts WHERE login LIKE 'auth-test-%'")
            connection.execute("DELETE FROM manuscript_stages WHERE module_code = %s", (self.CODE,))
            connection.execute("DELETE FROM manuscript_stage_history WHERE module_code = %s", (self.CODE,))

    def test_name_comes_from_the_session(self):
        with TestClient(create_app(database_url=DSN)) as client:
            self.assertEqual(client.post(f"/api/manuscripts/{self.CODE}/stages/1", json={"done": True}).status_code, 401)
            client.post("/api/login", json={"login": LOGIN, "password": PASSWORD})
            done = client.post(f"/api/manuscripts/{self.CODE}/stages/1", json={"done": True, "by": "남의 이름", "note": "확인"})
            self.assertEqual(done.status_code, 200, done.text)
            self.assertEqual(done.json()["단계"][0]["완료한 사람"], f"김에디터({LOGIN})")

    def test_image_history_name_comes_from_the_session(self):
        """이미지 저작권 DB의 변경 이력도 같다(REQ-02-010) — 보낸 이름은 쓰지 않고, 이름을 안 보내도 된다."""
        import hashlib
        from uuid import uuid4

        from ncs_service.image_db import load_records
        content = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (64).to_bytes(4, "big") + (48).to_bytes(4, "big")
                   + b"\x08\x02\x00\x00\x00" + uuid4().bytes)
        sha256 = hashlib.sha256(content).hexdigest()
        self.addCleanup(lambda: psycopg.connect(DSN, autocommit=True).execute("DELETE FROM image_assets WHERE sha256 = %s", (sha256,)))
        self.assertEqual(load_records(DSN, [{"content": content, "keywords": ["auth-test"]}], changed_by="적재").rejected, [])
        with psycopg.connect(DSN) as connection:
            image_id = str(connection.execute("SELECT id FROM image_assets WHERE sha256 = %s", (sha256,)).fetchone()[0])
        with TestClient(create_app(database_url=DSN)) as client:
            client.post("/api/login", json={"login": LOGIN, "password": PASSWORD})
            first = client.post(f"/api/images/{image_id}/rights", json={"by": "남의 이름", "rights": {"author": "가"}})
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["history"][0]["changed_by"], f"김에디터({LOGIN})")
            second = client.post(f"/api/images/{image_id}/rights", json={"version": first.json()["rights"]["version"], "rights": {"author": "나"}})
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(second.json()["history"][0]["changed_by"], f"김에디터({LOGIN})")
