"""보안·보관 마무리(KISA 대조 점검 R4, R5, R7과 생성형 AI 응답 캐시 보관 일수).

- R4: API 문서(/docs, /redoc, /openapi.json)는 기본으로 닫고 NCS_WEB_DEBUG=1일 때만 연다
- R5: 모든 응답에 보안 머리글
- R7: 결과 폴더는 보관 일수(NCS_RESULT_TTL_DAYS, 기본 365)를 넘긴 실행 폴더만 지운다
- 캐시: Claude 쪽 응답 캐시(LLM 검토·의견 반영 검토·문장 추천·그림 판독)도 LLM_CACHE_TTL_DAYS를 넘기면 지운다
"""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ncs_web.server import create_app

DAY = 86400


def client(folder, **env):
    with mock.patch.dict(os.environ, env):
        return TestClient(create_app(out_dir=Path(folder) / "results", dist_dir=Path(folder) / "no_build"))


class ApiDocsTests(unittest.TestCase):
    def test_docs_are_closed_by_default_and_open_in_debug(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ.pop("NCS_WEB_DEBUG", None)
            with client(folder) as closed:
                self.assertEqual([closed.get(path).status_code for path in ("/docs", "/redoc", "/openapi.json")], [404, 404, 404])
            with client(folder, NCS_WEB_DEBUG="1") as opened:
                self.assertEqual(opened.get("/openapi.json").status_code, 200)


class SecurityHeaderTests(unittest.TestCase):
    def test_every_response_carries_the_headers(self):
        with tempfile.TemporaryDirectory() as folder, client(folder) as web:
            for path in ("/api/health", "/api/no-such-path"):
                headers = web.get(path).headers
                self.assertEqual(headers["x-content-type-options"], "nosniff", path)
                self.assertEqual(headers["x-frame-options"], "DENY", path)
                self.assertEqual(headers["referrer-policy"], "no-referrer", path)
                self.assertIn("frame-ancestors 'none'", headers["content-security-policy"], path)


class ResultRetentionTests(unittest.TestCase):
    def test_only_old_run_folders_are_removed(self):
        from ncs_service.store import FileStore

        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "결과"
            old_run = out / "LM1203020201_24v3_20251101-101010_차례_abc123"
            new_run = out / "LM1203020201_24v3_20261120-101010_차례_def456"
            old_group = out / "605bec36-85af-4946-88c0-55b3ccf4ab6c"
            mine = out / "내가 둔 자료"                      # 이 서비스가 만든 이름이 아니면 건드리지 않는다
            for path in (old_run, new_run, old_group, mine):
                path.mkdir(parents=True)
                (path / "파일.json").write_text("{}", encoding="utf-8")
            long_ago = time.time() - 400 * DAY
            for path in (old_run, old_group, mine):
                os.utime(path / "파일.json", (long_ago, long_ago))
                os.utime(path, (long_ago, long_ago))
            store = FileStore(out)
            self.assertEqual(store.prune(days=365), 2)
            self.assertEqual(sorted(p.name for p in out.iterdir()), sorted([new_run.name, mine.name]))
            self.assertEqual(store.prune(days=0), 0)                 # 0이면 지우지 않는다


class ClaudeCacheRetentionTests(unittest.TestCase):
    def test_old_responses_are_removed_and_usage_log_stays(self):
        from ncs_llmreview import claude

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for part in ("llmreview/opinion_reflection", "figures/read"):
                (root / part).mkdir(parents=True)
            old, new = root / "llmreview/opinion_reflection/old.json", root / "figures/read/new.json"
            older = root / "figures/read/old.json"
            usage = root / "llmreview/usage.jsonl"
            for path in (old, new, older, usage):
                path.write_text("{}", encoding="utf-8")
            long_ago = time.time() - 40 * DAY
            for path in (old, older, usage):
                os.utime(path, (long_ago, long_ago))
            with mock.patch.dict(os.environ, {"LLM_CACHE_DIR": str(root), "LLM_CACHE_TTL_DAYS": "30"}):
                self.assertEqual(claude.prune_cache(), 2)
            self.assertEqual((old.exists(), older.exists(), new.exists(), usage.exists()), (False, False, True, True))
            with mock.patch.dict(os.environ, {"LLM_CACHE_DIR": str(root), "LLM_CACHE_TTL_DAYS": "0"}):
                self.assertEqual(claude.prune_cache(), 0)


if __name__ == "__main__":
    unittest.main()
