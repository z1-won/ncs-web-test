"""시연 계정 안내(/api/login/demo) — 로그인을 쓰지 않는 서버와 NCS_DEMO_PASSWORD가 없는 서버는 아무것도 내주지 않는다."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ncs_web import auth
from ncs_web.server import create_app

ROWS = [
    {"id": "1", "login": "demo-editor", "name": "김에디터", "role": "editor", "role_name": "에디터", "org": "에디팅기관", "active": True},
    {"id": "2", "login": "demo-author", "name": "이집필", "role": "author", "role_name": "집필진", "org": "개발기관", "active": False},
    {"id": "3", "login": "kim", "name": "김실제", "role": "editor", "role_name": "에디터", "org": "에디팅기관", "active": True},
]


class _Store:
    dsn = "postgresql://unused"


def _client(require_login: bool) -> TestClient:
    app = FastAPI()
    auth.install(app, _Store(), require_login=require_login)
    return TestClient(app)


class LoginDemoTests(unittest.TestCase):
    def test_server_without_database_gives_nothing(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {"NCS_DEMO_PASSWORD": "시연용 값"}):
            client = TestClient(create_app(out_dir=Path(temp) / "out", dist_dir=Path(temp) / "no_build"))
            self.assertEqual(client.get("/api/login/demo").json(), {"password": None, "accounts": []})

    def test_nothing_without_the_environment_variable(self):
        env = {key: value for key, value in os.environ.items() if key != "NCS_DEMO_PASSWORD"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("ncs_service.auth.accounts.list_accounts", return_value=ROWS) as listing:
            self.assertEqual(_client(True).get("/api/login/demo").json(), {"password": None, "accounts": []})
            listing.assert_not_called()

    def test_only_active_demo_accounts_are_listed_before_login(self):
        with mock.patch.dict(os.environ, {"NCS_DEMO_PASSWORD": "시연용 값"}), mock.patch("ncs_service.auth.accounts.list_accounts", return_value=ROWS):
            body = _client(True).get("/api/login/demo").json()      # 로그인하지 않은 요청에도 열려 있다
        self.assertEqual(body["password"], "시연용 값")
        self.assertEqual(body["accounts"], [{"login": "demo-editor", "name": "김에디터", "role": "editor", "role_name": "에디터", "org": "에디팅기관"}])


if __name__ == "__main__":
    unittest.main()
