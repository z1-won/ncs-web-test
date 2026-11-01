"""FastAPI와 기존 엔진의 결과 일치·업로드 수명·오류 계약을 확인한다."""

import importlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
from ncs_web.server import create_app
from ncs_web import server

FIXTURES = ROOT / "tests" / "fixtures"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PACKAGES = {"position": "ncs_position", "toc": "ncs_toc", "overview": "ncs_overview", "knowledge": "ncs_knowledge", "perform": "ncs_perform", "teaching": "ncs_teaching", "evaluation": "ncs_evaluation", "references": "ncs_references", "colophon": "ncs_colophon", "misc": "ncs_misc"}


class WebappTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ncs_api_test_")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "results"
        self.client = TestClient(create_app(out_dir=self.output, dist_dir=Path(self.temp.name) / "no_build"))
        self.addCleanup(self.client.close)

    def upload(self, check="position", manuscript=MANUSCRIPT, with_plan=True, **data):
        paths = [manuscript, PLAN] if with_plan else [manuscript]
        return self.client.post("/api/review", data={"check": check, **data}, files=[
            ("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in paths
        ])

    def test_all_engines_match_direct_results_and_save(self):
        for check, package in PACKAGES.items():
            engine = importlib.import_module(package)
            for manuscript in sorted(FIXTURES.glob("원고_*.hwpx")):
                with self.subTest(check=check, file=manuscript.name):
                    expected = engine.run_review([str(manuscript), str(PLAN)])
                    response = self.upload(check, manuscript)
                    self.assertEqual(response.status_code, 200, response.text)
                    body = response.json()
                    self.assertEqual(body["전체"], expected.checklist)
                    self.assertEqual(body["지적사항"], expected.findings)
                    self.assertEqual(body["검수확인서"], expected.sheet)
                    self.assertEqual(body["module_code"], expected.module_code)
                    with zipfile.ZipFile(body["저장"]["zip"]) as archive:
                        self.assertIsNone(archive.testzip())
                        name = next(name for name in archive.namelist() if name.endswith("_전체.json"))
                        self.assertEqual(json.loads(archive.read(name)), body["전체"])
                    for path in body["진단"]["inputs"].values():
                        if path:
                            self.assertFalse(Path(path).exists(), "업로드 임시 파일 정리")

    def test_plan_requirements(self):
        self.assertEqual(self.upload(with_plan=False).status_code, 400)
        for check in ("toc", "overview", "knowledge"):
            with self.subTest(check=check):
                self.assertEqual(self.upload(check, with_plan=False).status_code, 200)

    def test_missing_invalid_and_empty_inputs(self):
        responses = [
            self.client.post("/api/review"),
            self.upload("unknown"),
            self.upload(module_code="invalid"),
            self.client.post("/api/review", files={"files": ("empty.hwpx", b"")}),
            self.client.post("/api/review", files={"files": ("bad.hwpx", b"invalid")}),
        ]
        for response in responses:
            with self.subTest(body=response.text):
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.json()["error"], str)
                self.assertNotIn("traceback", response.json())

    def test_default_check_and_same_filename(self):
        # 역할 판별은 파일명이나 업로드 순서에 의존하지 않는다.
        response = self.client.post("/api/review", data={"module_code": "LM1203020201_24v3"}, files=[
            ("files", ("same.hwpx", PLAN.read_bytes())),
            ("files", ("same.hwpx", MANUSCRIPT.read_bytes())),
        ])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["check"], "position")

    def test_upload_token_runs_several_checks_on_one_upload(self):
        """전체 실행의 서버 쪽 흐름: 업로드 1회 → 토큰으로 검수 여러 번 → 토큰 반납. 결과는 files로 직접 올린 것과 같다."""
        created = self.client.post("/api/uploads", files=[
            ("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in (MANUSCRIPT, PLAN)
        ])
        self.assertEqual(created.status_code, 200, created.text)
        token = created.json()
        self.assertEqual(token["roles"], {"manuscript": MANUSCRIPT.name, "plan": PLAN.name})
        self.assertEqual(sorted(token["files"]), sorted([MANUSCRIPT.name, PLAN.name]))
        self.assertGreater(token["expires_in"], 0)
        for check in ("position", "toc", "colophon"):
            with self.subTest(check=check):
                via_token = self.client.post("/api/review", data={"check": check, "upload": token["upload"], "group": token["group"]})
                self.assertEqual(via_token.status_code, 200, via_token.text)
                direct = self.upload(check).json()
                self.assertEqual(via_token.json()["검수확인서"], direct["검수확인서"])
                self.assertEqual(via_token.json()["group"], token["group"])
                # 파일 저장소는 묶음 폴더 아래에 모아 둔다
                self.assertEqual(Path(via_token.json()["저장"]["folder"]).parent, self.output / token["group"])
        self.assertEqual(self.client.delete(f"/api/uploads/{token['upload']}").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/uploads/{token['upload']}").status_code, 404)
        expired = self.client.post("/api/review", data={"check": "toc", "upload": token["upload"]})
        self.assertEqual(expired.status_code, 400)
        self.assertIn("만료", expired.json()["error"])

    def test_upload_token_reports_missing_plan_and_rejects_bad_input(self):
        only_manuscript = self.client.post("/api/uploads", files=[("files", (MANUSCRIPT.name, MANUSCRIPT.read_bytes()))]).json()
        self.assertEqual(only_manuscript["roles"], {"manuscript": MANUSCRIPT.name, "plan": None})
        # 개발계획서가 필요한 위치 검수는 토큰으로도 400 — 화면은 roles.plan이 없으면 위치를 건너뛴다
        self.assertEqual(self.client.post("/api/review", data={"check": "position", "upload": only_manuscript["upload"]}).status_code, 400)
        single = self.client.post("/api/review", data={"check": "toc", "upload": only_manuscript["upload"]})
        self.assertEqual(single.status_code, 200)
        self.assertIsNone(single.json()["group"], "group 없이 토큰만 보내면 묶음이 아닌 단독 실행")
        self.assertEqual(Path(single.json()["저장"]["folder"]).parent, self.output)
        for response in (
            self.client.post("/api/uploads"),
            self.client.post("/api/uploads", files={"files": ("empty.hwpx", b"")}),
            self.client.post("/api/uploads", files={"files": ("bad.hwpx", b"invalid")}),
            self.client.post("/api/review", data={"check": "toc", "upload": "no-such-token"}),
            self.client.post("/api/review", data={"check": "toc", "upload": only_manuscript["upload"], "group": "other"}),
            self.client.post("/api/review", data={"check": "toc", "group": "lonely"}, files={"files": (MANUSCRIPT.name, MANUSCRIPT.read_bytes())}),
        ):
            with self.subTest(body=response.text):
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.json()["error"], str)
        self.assertEqual(len(self.client.app.state.uploads), 1, "실패한 업로드는 보관함에 남지 않는다")

    def test_health_reports_history_support(self):
        body = self.client.get("/api/health").json()
        self.assertEqual(body["checks"], list(PACKAGES))
        self.assertIs(body["history"], False, "파일 저장소는 이력 API가 없다")
        self.assertEqual(self.client.get("/api/reviews").status_code, 405, "이력 API 미등록(OPTIONS 전체 경로 핸들러 때문에 404 대신 405)")

    def test_save_failure_returns_500_and_cleans_uploads(self):
        captured = []

        def fail(review, output):
            captured.extend(review.result.diagnostics["inputs"].values())
            raise OSError("저장 실패 테스트")

        with patch("ncs_service.store.persist_review", side_effect=fail):  # FileStore.save가 부르는 지점
            client = TestClient(create_app(out_dir=self.output))
            with client:
                response = client.post("/api/review", files=[
                    ("files", (p.name, p.read_bytes())) for p in (MANUSCRIPT, PLAN)
                ])
        self.assertEqual(response.status_code, 500)
        self.assertIn("저장 실패 테스트", response.json()["error"])
        self.assertIn("traceback", response.json())
        self.assertTrue(captured)
        self.assertTrue(all(not Path(path).exists() for path in captured))

    def test_health_docs_and_cors(self):
        health = self.client.get("/api/health")
        body = health.json()
        self.assertEqual({k: v for k, v in body.items() if k != "engines"}, {"ok": True, "checks": list(PACKAGES), "history": False})
        # engines: 화면 선택 목록의 글이 되는 엔진 설명 — 등록 순서대로, 구현 항목은 확인서 번호
        self.assertEqual([e["check"] for e in body["engines"]], list(PACKAGES))
        self.assertEqual(body["engines"][0]["component"], "NCS-학습모듈의 위치")
        self.assertTrue(all(e["items"] and all(n in "①②③④⑤⑥⑦⑧" for n in e["items"]) and e["total"] >= len(e["items"]) for e in body["engines"]))
        self.assertEqual(health.headers["access-control-allow-origin"], "*")
        self.assertEqual(self.client.get("/docs").status_code, 200)
        schema = self.client.get("/openapi.json").json()
        responses = schema["paths"]["/api/review"]["post"]["responses"]
        self.assertIn("400", responses)
        self.assertNotIn("422", responses)
        preflight = self.client.options("/api/review", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        })
        self.assertEqual(preflight.status_code, 204)
        self.assertEqual(preflight.headers["access-control-allow-origin"], "*")

    def test_static_files_and_api_routing(self):
        root = self.client.get("/")
        self.assertEqual(root.status_code, 404)
        self.assertIn("charset=utf-8", root.headers["content-type"], "브라우저가 한국어 오류 메시지를 직접 표시할 때 깨지지 않도록")
        self.assertIn("--dist", root.json()["error"])
        dist = Path(self.temp.name) / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<h1>F02</h1>")
        (dist / "app.js").write_text("console.log('F02')")
        with TestClient(create_app(out_dir=self.output, dist_dir=dist)) as client:
            self.assertEqual(client.get("/").text, "<h1>F02</h1>")
            self.assertEqual(client.get("/app.js").status_code, 200)
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(client.get("/api/missing").status_code, 404)

    def test_service_runs_without_http(self):
        from ncs_service import ReviewRequest, execute_review, persist_review

        result = execute_review(ReviewRequest((MANUSCRIPT, PLAN)))
        self.assertFalse(self.output.exists())
        saved = persist_review(result, self.output)
        self.assertTrue(saved.zip_path.is_file())

    def test_default_output_uses_startup_directory_and_frontend_is_opt_in(self):
        startup = Path(self.temp.name) / "startup"
        startup.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(startup)
            app = create_app()
        finally:
            os.chdir(previous)
        with TestClient(app) as client:
            self.assertEqual(client.get("/").status_code, 404)
            self.assertEqual(client.get("/api/health").status_code, 200)
            response = client.post("/api/review", files=[
                ("files", (p.name, p.read_bytes())) for p in (MANUSCRIPT, PLAN)
            ])
        self.assertEqual(response.status_code, 200, response.text)
        saved = Path(response.json()["저장"]["folder"])
        self.assertEqual(saved.parent, (startup / "결과").resolve())
        self.assertTrue(Path(response.json()["저장"]["zip"]).is_file())

    def test_explicit_paths_are_independent_and_resolved_at_startup(self):
        startup = Path(self.temp.name) / "runtime"
        startup.mkdir()
        dist = startup / "ui"
        dist.mkdir()
        (dist / "index.html").write_text("<h1>External UI</h1>")
        previous = Path.cwd()
        try:
            os.chdir(startup)
            app = create_app(out_dir="reports", dist_dir="ui")
        finally:
            os.chdir(previous)
        with TestClient(app) as client:
            self.assertEqual(client.get("/").text, "<h1>External UI</h1>")
            response = client.post("/api/review", files=[
                ("files", (p.name, p.read_bytes())) for p in (MANUSCRIPT, PLAN)
            ])
            self.assertEqual(response.status_code, 200, response.text)
            saved = Path(response.json()["저장"]["folder"])
            self.assertEqual(saved.parent, (startup / "reports").resolve())
            zip_path = Path(response.json()["저장"]["zip"])
            self.assertEqual(client.get(f"/{saved.name}/{zip_path.name}").status_code, 404)
        self.assertEqual(sorted(p.name for p in dist.iterdir()), ["index.html"])

    def test_server_cli_accepts_output_and_frontend_paths(self):
        args = ["server.py", "--out", str(self.output), "--dist", str(Path(self.temp.name) / "ui"), "--port", "8766"]
        with patch.object(sys, "argv", args), patch.object(server, "create_app") as create, patch.object(server.uvicorn, "run") as run:
            server.main()
        self.assertEqual(create.call_args.kwargs["out_dir"], str(self.output))
        self.assertEqual(create.call_args.kwargs["dist_dir"], str(Path(self.temp.name) / "ui"))
        run.assert_called_once_with(create.return_value, host="127.0.0.1", port=8766)


if __name__ == "__main__":
    unittest.main()
