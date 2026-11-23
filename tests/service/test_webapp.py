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

ROOT = Path(__file__).resolve().parents[2]
from ncs_web.server import create_app
from ncs_web import server

FIXTURES = ROOT / "tests" / "fixtures"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PACKAGES = {"position": "ncs_position", "toc": "ncs_toc", "overview": "ncs_overview", "knowledge": "ncs_knowledge", "perform": "ncs_perform", "teaching": "ncs_teaching", "evaluation": "ncs_evaluation", "references": "ncs_references", "colophon": "ncs_colophon", "misc": "ncs_misc", "plan": "ncs_plan"}


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

    def test_plan_draft_returns_file_and_check_in_body(self):
        """초안 점검 요약은 10KB를 넘을 수 있어 응답 헤더가 아니라 본문에 싣는다."""
        import base64
        import os
        from unittest import mock

        patcher = mock.patch.dict(os.environ)   # 골든 테스트가 NCS 목록을 꺼 두었을 수 있다 — 이 테스트 동안만 기본 목록을 쓴다
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("NCS_CATALOG_FILE", None)
        listed = self.client.get("/api/plan/subclasses").json()
        self.assertGreater(len(listed["subclasses"]), 1000)      # NCS 목록의 세분류 전부(받아 두지 않은 것도 보인다)
        self.assertFalse(listed["can_fetch"])                    # 테스트에는 NCS 키도 기준정보 폴더도 없다
        duty = next(s["duty"] for s in listed["subclasses"] if s["ready"])
        response = self.client.post("/api/plan/draft", json={"duty": duty})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("x-plan-check", response.headers)
        body = response.json()
        self.assertTrue(body["filename"].endswith(".hwpx"))
        self.assertEqual(base64.b64decode(body["content"])[:2], b"PK")
        self.assertEqual([row["번호"] for row in body["check"]], list("①②③④⑤⑥⑦⑧⑨⑩"))
        self.assertEqual(self.client.post("/api/plan/draft", json={"duty": "99999999"}).status_code, 400)
        # 개선 계획서: 개선 양식(개선 유형 열 + 변경 전·후 대조표)에 채운다. 유형 이름이 틀리면 400
        units = [u["code"] for u in self.client.get(f"/api/plan/subclasses/{duty}").json()["units"]]
        improved = self.client.post("/api/plan/draft", json={"duty": duty, "kind": "개선", "types": {units[0]: "최소개선"}, "previous": {units[0]: units[0]}})
        self.assertEqual(improved.status_code, 200, improved.text)
        self.assertEqual(self.client.post("/api/plan/draft", json={"duty": duty, "kind": "개선", "types": {units[0]: "대충 개선"}}).status_code, 400)
        self.assertEqual(self.client.post("/api/plan/draft", json={"duty": duty, "kind": "수정"}).status_code, 400)
        # 비교: 신규 초안(기준)과 개선 초안(대상) — 능력단위는 같고 개선 유형·대조표만 대상에 있다
        files = {"base": ("신규.hwpx", base64.b64decode(body["content"])), "target": ("개선.hwpx", base64.b64decode(improved.json()["content"]))}
        compared = self.client.post("/api/plan/compare", files=files)
        self.assertEqual(compared.status_code, 200, compared.text)
        result = compared.json()
        self.assertEqual(result["요약"]["능력단위"], {"기준": len(units), "대상": len(units)})
        self.assertEqual(result["요약"]["수정 금지 칸 변경"], 0)
        self.assertEqual(len(result["개선 유형 변경"]), 1)       # 유형을 고르지 않은 능력단위는 빈 칸으로 둔다(기본값 없음)
        self.assertEqual(next(row for row in result["개선 유형 변경"] if row["코드"] == units[0])["대상"], "최소개선")
        self.assertIn(("변경 전·후 대조표", "분석 결과", "대상에만 있음"), {(row["구역"], row["칸"], row["차이"]) for row in result["차이"]})
        self.assertEqual(self.client.post("/api/plan/compare", files={"base": ("a.hwpx", b"not a file"), "target": files["target"]}).status_code, 400)
        # 반영: 고른 칸만 대상 사본에 넣는다. 한쪽이 빈 칸은 반영하지 않고 알린다. 비교 결과에 없는 행은 받지 않는다
        import json

        picked = [row for row in result["차이"] if row["칸"] == "개선 유형"][:1]
        applied = self.client.post("/api/plan/apply", files=files, data={"rows": json.dumps(picked)})
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(base64.b64decode(applied.json()["content"])[:2], b"PK")
        self.assertEqual((applied.json()["report"]["반영"], len(applied.json()["report"]["반영 못 함"])), (0, 1))
        forged = [{"구역": "모듈 표", "자리": "", "칸": "학습명", "기준": "아무 글", "대상": "없는 글", "차이": "다름"}]
        self.assertEqual(self.client.post("/api/plan/apply", files=files, data={"rows": json.dumps(forged)}).status_code, 400)
        self.assertEqual(self.client.post("/api/plan/apply", files=files, data={"rows": "[]"}).status_code, 400)
        # 개선 유형 판단 자료: 원고에서 신호를 찾을 뿐 유형을 정하지 않는다
        manuscript = sorted(FIXTURES.glob("원고_*.hwpx"))[0]
        signals = self.client.post("/api/plan/type-signals", files={"file": (manuscript.name, manuscript.read_bytes())})
        self.assertEqual(signals.status_code, 200, signals.text)
        self.assertEqual(set(signals.json()) >= {"신호", "확인 못 한 것", "안내", "파일", "모듈 코드"}, True)
        self.assertNotIn("판정", signals.json())

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
        self.assertEqual(token["roles"], {"manuscript": MANUSCRIPT.name, "plan": PLAN.name, "print": None})
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
                # macOS는 /var → /private/var 심볼릭 링크라 양쪽을 resolve해서 비교
                self.assertEqual(Path(via_token.json()["저장"]["folder"]).parent.resolve(), (self.output / token["group"]).resolve())
        self.assertEqual(self.client.delete(f"/api/uploads/{token['upload']}").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/uploads/{token['upload']}").status_code, 404)
        expired = self.client.post("/api/review", data={"check": "toc", "upload": token["upload"]})
        self.assertEqual(expired.status_code, 400)
        self.assertIn("만료", expired.json()["error"])

    def test_upload_roles_come_from_slots_or_order(self):
        """역할은 화면의 업로드 칸(roles)이 정하고, 없으면 넣은 순서(원고 → 개발계획서)다. 내용으로 추측하지 않으며, 그 토큰으로 돌리는 검수에도 그대로 쓰인다."""
        def post(paths, roles):
            return self.client.post("/api/uploads", data={"roles": json.dumps(roles)}, files=[
                ("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in paths
            ])
        # 내용으로는 개발계획서인 파일도 원고 칸에 올리면 원고로 받는다
        swapped = post([PLAN], ["manuscript"])
        self.assertEqual(swapped.status_code, 200, swapped.text)
        self.assertEqual(swapped.json()["roles"], {"manuscript": PLAN.name, "plan": None, "print": None})
        # roles가 없으면 넣은 순서가 역할: 첫 파일 원고, 둘째 개발계획서. 셋째 hwp/hwpx는 맡을 역할이 없어 거절
        other = FIXTURES / "원고_pos_LM1203020201_24v3.hwpx"
        ordered = self.client.post("/api/uploads", files=[("files", (p.name, p.read_bytes())) for p in (MANUSCRIPT, other)])
        self.assertEqual(ordered.status_code, 200, ordered.text)
        self.assertEqual(ordered.json()["roles"], {"manuscript": MANUSCRIPT.name, "plan": other.name, "print": None})
        third = FIXTURES / "원고_eval_LM1203020201_24v3.hwpx"
        extra = self.client.post("/api/uploads", files=[("files", (p.name, p.read_bytes())) for p in (MANUSCRIPT, other, third)])
        self.assertEqual(extra.status_code, 400)
        self.assertIn(third.name, extra.json()["error"])
        both = post([MANUSCRIPT, other], ["manuscript", "plan"])
        self.assertEqual(both.status_code, 200, both.text)
        self.assertEqual(both.json()["roles"], {"manuscript": MANUSCRIPT.name, "plan": other.name, "print": None})
        # 토큰으로 돌린 검수는 지정한 역할을 쓴다: 진단의 입력 경로가 칸대로 나뉜다
        token = post([MANUSCRIPT, PLAN], ["manuscript", "plan"]).json()
        via_token = self.client.post("/api/review", data={"check": "position", "upload": token["upload"]})
        self.assertEqual(via_token.status_code, 200, via_token.text)
        self.assertEqual(via_token.json()["검수확인서"], self.upload("position").json()["검수확인서"])
        self.assertEqual(self.client.post("/api/review", data={"check": "toc", "upload": token["upload"], "roles": '["manuscript"]'}).status_code, 400)
        # files로 직접 올릴 때도 roles를 받는다(개발계획서 작성 페이지의 점검이 이렇게 보낸다)
        direct = self.client.post("/api/review", data={"check": "plan", "roles": '["plan"]'}, files=[("files", (PLAN.name, PLAN.read_bytes()))])
        self.assertEqual(direct.status_code, 200, direct.text)
        # 잘못된 roles: 같은 역할 둘, 개수 불일치, 모르는 역할, 배열 아님, PDF 아닌 출력본
        for paths, roles, word in (
            ([MANUSCRIPT, PLAN], ["manuscript", "manuscript"], "둘 이상"),
            ([MANUSCRIPT, PLAN], ["manuscript"], "개수"),
            ([MANUSCRIPT], ["draft"], "roles"),
            ([MANUSCRIPT], {"manuscript": 0}, "JSON 배열"),
            ([MANUSCRIPT], ["print"], "PDF"),
        ):
            with self.subTest(roles=roles):
                response = post(paths, roles)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn(word, response.json()["error"])
        self.assertEqual(len(self.client.app.state.uploads), 4, "거부된 업로드는 보관함에 남지 않는다")   # 받은 것: swapped·ordered·both·token

    def test_image_dpi_choice_reaches_misc_and_rejects_other_values(self):
        """이미지 해상도 기준(image_dpi)은 150/300만 받고 기타(misc) 검수 설정으로 들어간다. 다른 검수는 무시한다."""
        files = [("files", (MANUSCRIPT.name, MANUSCRIPT.read_bytes()))]
        for value in ("150", "300"):
            with self.subTest(image_dpi=value):
                self.assertEqual(self.client.post("/api/review", data={"check": "misc", "image_dpi": value}, files=files).status_code, 200)
        bad = self.client.post("/api/review", data={"check": "misc", "image_dpi": "200"}, files=files)
        self.assertEqual(bad.status_code, 400)
        self.assertIn("150 / 300", bad.json()["error"])
        self.assertEqual(self.client.post("/api/review", data={"check": "toc", "image_dpi": "200"}, files=files).status_code, 200)

    def test_upload_token_reports_missing_plan_and_rejects_bad_input(self):
        only_manuscript = self.client.post("/api/uploads", files=[("files", (MANUSCRIPT.name, MANUSCRIPT.read_bytes()))]).json()
        self.assertEqual(only_manuscript["roles"], {"manuscript": MANUSCRIPT.name, "plan": None, "print": None})
        # 개발계획서가 필요한 위치 검수는 토큰으로도 400 — 화면은 roles.plan이 없으면 위치를 건너뛴다
        self.assertEqual(self.client.post("/api/review", data={"check": "position", "upload": only_manuscript["upload"]}).status_code, 400)
        single = self.client.post("/api/review", data={"check": "toc", "upload": only_manuscript["upload"]})
        self.assertEqual(single.status_code, 200)
        self.assertIsNone(single.json()["group"], "group 없이 토큰만 보내면 묶음이 아닌 단독 실행")
        self.assertEqual(Path(single.json()["저장"]["folder"]).parent.resolve(), self.output.resolve())
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
        self.assertEqual(self.client.get("/api/reviews").status_code, 404, "이력 API 미등록")

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
        self.assertNotIn("traceback", response.json(), "서버 경로·내부 구조가 담긴 traceback은 기본적으로 응답에 싣지 않는다")
        with patch("ncs_service.store.persist_review", side_effect=fail), patch.dict(os.environ, {"NCS_WEB_DEBUG": "1"}):
            with TestClient(create_app(out_dir=self.output)) as client:
                debug = client.post("/api/review", files=[("files", (p.name, p.read_bytes())) for p in (MANUSCRIPT, PLAN)])
        self.assertIn("저장 실패 테스트", debug.json()["traceback"])
        self.assertTrue(captured)
        self.assertTrue(all(not Path(path).exists() for path in captured))

    def test_bad_file_error_names_the_file_but_not_the_server_path(self):
        """400 오류 문구에는 올린 파일 이름만 들어가고 서버 임시 폴더 경로는 들어가지 않는다(에러페이지 정보 노출 방지)."""
        response = self.client.post("/api/review", data={"check": "toc"}, files=[("files", ("원고_가짜.hwpx", b"this is not a document"))])
        self.assertEqual(response.status_code, 400)
        message = response.json()["error"]
        self.assertIn("원고_가짜.hwpx", message)
        self.assertNotIn("ncs_upload_", message)
        self.assertNotRegex(message, r"(^|[\s:])/", "절대 경로가 들어가면 안 된다")

    def test_health_docs_and_cors(self):
        health = self.client.get("/api/health")
        body = health.json()
        self.assertEqual({k: v for k, v in body.items() if k != "engines"},
                         {"ok": True, "checks": list(PACKAGES), "history": False, "image_db": False,
                          "image_dpi": {"choices": [150, 300], "default": 300}})
        # 이미지 저작권 DB API는 PostgreSQL 저장소일 때만 붙는다 — 파일 저장소에서는 경로 자체가 없다
        self.assertEqual(self.client.get("/api/images").status_code, 404)
        self.assertEqual(self.client.get("/api/images/terms").status_code, 404)
        # engines: 화면 선택 목록의 글이 되는 엔진 설명 — 등록 순서대로, 구현 항목은 확인서 번호
        self.assertEqual([e["check"] for e in body["engines"]], list(PACKAGES))
        self.assertEqual(body["engines"][0]["component"], "NCS-학습모듈의 위치")
        self.assertTrue(all(e["items"] and all(n in "①②③④⑤⑥⑦⑧⑨⑩" for n in e["items"]) and e["total"] >= len(e["items"]) for e in body["engines"]))
        self.assertNotIn("access-control-allow-origin", health.headers, "출처 없는 요청에는 CORS 헤더를 내지 않는다")
        self.assertEqual(self.client.get("/docs").status_code, 200)
        schema = self.client.get("/openapi.json").json()
        responses = schema["paths"]["/api/review"]["post"]["responses"]
        self.assertIn("400", responses)
        self.assertNotIn("422", responses)
        preflight = self.client.options("/api/review", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        })
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers["access-control-allow-origin"], "http://localhost:5173")
        # 허용 목록 밖의 출처(브라우저에서 연 임의의 웹사이트)는 이 로컬 API를 읽거나 지울 수 없어야 한다
        for method, path in (("GET", "/api/health"), ("DELETE", "/api/uploads/x")):
            blocked = self.client.options(path, headers={
                "Origin": "https://evil.example", "Access-Control-Request-Method": method,
            })
            self.assertNotEqual(blocked.status_code, 200, f"{method} {path} preflight must be refused")
            self.assertNotIn("access-control-allow-origin", blocked.headers)
        foreign = self.client.get("/api/health", headers={"Origin": "https://evil.example"})
        self.assertNotIn("access-control-allow-origin", foreign.headers, "응답은 가되 다른 출처의 스크립트는 읽지 못한다")

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
