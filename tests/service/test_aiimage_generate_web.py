"""도표·표 생성 웹 경로(/api/ai-image/generate/…) — 상태, AI 미설정에서의 명세 요청, 검사, 그리기, 잘못된 입력.

웹 경로에는 가짜 LLM을 넣을 수 없으므로 테스트 환경(키 없음)의 미설정 경로만 본다. 후보 거르기는 tests/engines/test_aiimage_diagram.py가 본다."""

import json
import tempfile
import unittest

from ncs_aiimage.draw import font_available

TEXT = "먼저 예약 요청을 접수하고 객실 현황을 확인한 뒤 예약 확인서를 발송한다."
SPEC = {"kind": "sequence", "title": "예약 접수", "items": [{"label": "예약 요청 접수"}, {"label": "객실 현황 확인"}, {"label": "예약 확인서 발송"}]}
TABLE = {"kind": "table", "header": ["단계", "내용"], "rows": [["접수", "예약 요청"]]}


class GenerateWebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(out_dir=self.out.name))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def test_status(self):
        body = self.client.get("/api/ai-image/generate/status").json()
        self.assertFalse(body["사용 가능"])                       # 테스트 환경에는 키·승인이 없다
        self.assertTrue(body["이유"])
        self.assertEqual([kind["kind"] for kind in body["종류"]], ["sequence", "cycle", "structure", "compare", "table", "bar", "line", "pie"])

    def test_spec_without_ai_makes_nothing(self):
        response = self.client.post("/api/ai-image/generate/spec", json={"text": TEXT})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["method"], response.json()["candidates"]), ("none", []))

    def test_spec_needs_a_paragraph(self):
        self.assertEqual(self.client.post("/api/ai-image/generate/spec", json={"text": "  "}).status_code, 400)
        self.assertEqual(self.client.post("/api/ai-image/generate/spec", json={"text": TEXT, "kind": "donut"}).status_code, 400)

    def test_check(self):
        body = self.client.post("/api/ai-image/generate/check", json={"spec": SPEC, "text": TEXT}).json()
        self.assertEqual((body["checked"], body["ok"], body["problems"]), (True, True, []))
        edited = {**SPEC, "items": SPEC["items"] + [{"label": "보증금 수납"}]}
        body = self.client.post("/api/ai-image/generate/check", json={"spec": edited, "text": TEXT}).json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["problems"][0]["field"], "items[3].label")
        body = self.client.post("/api/ai-image/generate/check", json={"spec": SPEC}).json()      # 글이 없으면 모양만
        self.assertEqual((body["checked"], body["ok"]), (False, None))
        self.assertEqual(self.client.post("/api/ai-image/generate/check", json={"spec": {"kind": "sequence", "items": []}}).status_code, 400)

    def test_table_text(self):
        response = self.client.post("/api/ai-image/generate/render", json={"spec": TABLE, "format": "tsv"})
        self.assertEqual(response.text, "단계\t내용\n접수\t예약 요청\n")
        self.assertIn("<th>단계</th>", self.client.post("/api/ai-image/generate/render", json={"spec": TABLE, "format": "html"}).text)
        self.assertEqual(self.client.post("/api/ai-image/generate/render", json={"spec": SPEC, "format": "html"}).status_code, 400)

    @unittest.skipUnless(font_available(), "한글 글꼴이 없음")
    def test_render_png(self):
        response = self.client.post("/api/ai-image/generate/render", json={"spec": SPEC, "width_mm": 100})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.content[:8], b"\x89PNG\r\n\x1a\n")
        summary = json.loads(response.headers["X-Ai-Summary"])
        self.assertEqual((summary["width"], summary["dpi"], summary["kind"]), (round(100 / 25.4 * 300), 300, "sequence"))
        self.assertEqual(self.client.post("/api/ai-image/generate/render", json={"spec": SPEC, "width_mm": 500}).status_code, 400)
        self.assertEqual(self.client.post("/api/ai-image/generate/render", json={"spec": {"kind": "x"}}).status_code, 400)

    def test_marking_lines(self):
        body = self.client.post("/api/ai-image/generate/marking", json={"title": "예약 접수", "tool": "Claude", "date": "2026-11-24",
                                                                        "kind": "sequence", "number": "1-2"}).json()
        self.assertEqual(body["lines"], ["출처: 집필진 제작(2026)", "Claude를 활용하여 생성함. 2026. 11. 24.", "[그림 1-2] 예약 접수"])
        self.assertEqual(body["note"], "")
        from ncs_core.figures import parse_ai_mark
        self.assertEqual(parse_ai_mark(body["lines"][1]).mode, "generated")          # 필요 지식 ⑧과 권리 증빙 점검이 다시 읽는 꼴
        table = self.client.post("/api/ai-image/generate/marking", json={"title": "화재 종류별 소화기", "tool": "ChatGPT", "date": "2026-07-20",
                                                                         "kind": "table"}).json()
        self.assertEqual(table["lines"][2], "<표 ○-○> 화재 종류별 소화기")
        self.assertIn("F08", table["note"])
        bad = self.client.post("/api/ai-image/generate/marking", json={"title": "x", "tool": "A, B", "date": "2026-07-20", "kind": "sequence"})
        self.assertEqual(bad.status_code, 400)

    def test_graph_check_and_caption(self):
        text = "2023년 예약은 1,200건이었고 2024년에는 1,850건으로 늘었다."
        bar = {"kind": "bar", "title": "연도별 예약 건수", "unit": "건", "categories": ["2023년", "2024년"], "series": [{"name": "", "values": [1200, 1850]}]}
        body = self.client.post("/api/ai-image/generate/check", json={"spec": bar, "text": text}).json()
        self.assertEqual((body["ok"], body["spec"]), (True, bar))
        swapped = {**bar, "series": [{"name": "", "values": [1850, 1200]}]}
        self.assertFalse(self.client.post("/api/ai-image/generate/check", json={"spec": swapped, "text": text}).json()["ok"])
        lines = self.client.post("/api/ai-image/generate/marking", json={"title": "연도별 예약 건수", "tool": "Claude", "date": "2026-11-25",
                                                                         "kind": "bar", "number": "2-1"}).json()
        self.assertEqual((lines["lines"][2], lines["note"]), ("[그림 2-1] 연도별 예약 건수", ""))

    def test_database_paths_need_a_database(self):
        self.assertFalse(self.client.get("/api/ai-image/generate/status").json()["DB"])
        for path, more in (("similar", {}), ("register", {"tool": "Claude", "date": "2026-11-25", "by": "에디터"})):
            response = self.client.post(f"/api/ai-image/generate/{path}", json={"spec": SPEC, **more})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("이미지 저작권 DB", response.json()["error"])

    def test_image_engine_is_off_by_default(self):
        self.assertFalse(self.client.get("/api/ai-image/generate/status").json()["그림 엔진"]["사용 가능"])
        response = self.client.post("/api/ai-image/generate/image", json={"scene": "a workbench", "kind": "photo"})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("꺼져", response.json()["error"])

    def test_image_with_a_runner_and_prompt_checks(self):
        import base64
        import io

        from PIL import Image

        def runner(prompt, width, height, seed):
            self.sent = prompt
            buffer = io.BytesIO()
            Image.new("RGB", (width, height), (seed % 255, 100, 100)).save(buffer, "PNG")
            return buffer.getvalue()

        self.client.app.state.imagegen_runner = runner
        refused = self.client.post("/api/ai-image/generate/image", json={"scene": "portrait of a welder", "kind": "photo"})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["problems"][0]["kind"], "face")
        refused = self.client.post("/api/ai-image/generate/image", json={"scene": "a welder from behind", "scene_ko": "웃는 작업자", "kind": "photo"})
        self.assertEqual(refused.status_code, 400)
        body = self.client.post("/api/ai-image/generate/image", json={"scene": "a welder from behind", "kind": "photo", "count": 2, "seed": 7}).json()
        self.assertEqual([(one["seed"], one["width"], one["height"]) for one in body["images"]], [(7, 1024, 768), (8, 1024, 768)])
        self.assertIn("No visible human faces", self.sent)
        self.assertEqual(body["prompt"], self.sent)
        # 진행 상황과 취소: 화면이 정한 작업 번호로 묻는다
        self.assertEqual(self.client.get("/api/ai-image/generate/progress/job-web-1").status_code, 404)
        self.client.post("/api/ai-image/generate/image", json={"scene": "a welder from behind", "kind": "photo", "count": 1, "job": "job-web-1"})
        state = self.client.get("/api/ai-image/generate/progress/job-web-1").json()
        self.assertEqual((state["state"], state["count"], state["상태"]), ("done", 1, "완료"))
        self.assertEqual(self.client.post("/api/ai-image/generate/cancel/job-web-1").json(), {"cancelled": False})
        self.assertEqual(self.client.post("/api/ai-image/generate/image", json={"scene": "a bench", "kind": "photo", "job": "bad job!"}).status_code, 400)

        def cancelling(prompt, width, height, seed):
            self.client.post("/api/ai-image/generate/cancel/job-web-2")
            return b"png"

        self.client.app.state.imagegen_runner = cancelling
        stopped = self.client.post("/api/ai-image/generate/image", json={"scene": "a welder from behind", "kind": "photo", "count": 2, "job": "job-web-2"})
        self.assertEqual((stopped.status_code, stopped.json()["cancelled"]), (409, True))
        self.assertEqual(self.client.get("/api/ai-image/generate/progress/job-web-2").json()["state"], "cancelled")
        self.client.app.state.imagegen_runner = runner
        png = body["images"][0]["png"]
        self.assertEqual(base64.b64decode(png)[:4], b"\x89PNG")
        seen = self.client.post("/api/ai-image/generate/inspect", json={"png": png, "width_mm": 150}).json()
        self.assertEqual((seen["dpi"], seen["충분"], seen["300 DPI 폭"]), (173, False, 86))
        self.assertNotIn("닮은 그림", seen)                       # 데이터베이스가 없는 서버
        self.assertEqual(self.client.post("/api/ai-image/generate/inspect", json={"png": "!!"}).status_code, 400)
        self.assertEqual(self.client.post("/api/ai-image/generate/inspect", json={"png": base64.b64encode(b"jpeg").decode()}).status_code, 400)

    def test_prompt_without_ai_and_bad_input(self):
        body = self.client.post("/api/ai-image/generate/prompt", json={"text": TEXT, "kind": "photo"}).json()
        self.assertEqual((body["method"], body["scenes"], body["usage"]), ("none", [], 1))
        self.assertEqual(self.client.post("/api/ai-image/generate/prompt", json={"kind": "photo"}).status_code, 400)
        self.assertEqual(self.client.post("/api/ai-image/generate/prompt", json={"text": TEXT, "kind": "bar"}).status_code, 400)

    def test_marking_for_a_generated_picture(self):
        body = self.client.post("/api/ai-image/generate/marking", json={"title": "용접 보호구", "tool": "FLUX", "date": "2026-11-25", "kind": "photo",
                                                                        "number": "1-3", "usage": 4}).json()
        self.assertEqual(body["lines"][1:], ["FLUX를 활용하여 생성함. 2026. 11. 25.", "[그림 1-3] 용접 보호구"])
        self.assertEqual(body["usage"], 4)
        self.assertIn("표기 예 4", body["note"])
        bad = self.client.post("/api/ai-image/generate/marking", json={"title": "x", "tool": "A", "date": "2026-11-25", "kind": "bar", "usage": 4})
        self.assertEqual(bad.status_code, 400)

    def test_render_without_font_is_503(self):
        from unittest import mock

        from ncs_aiimage import draw

        with mock.patch.object(draw, "font_paths", side_effect=draw.FontError("글꼴 없음")):
            response = self.client.post("/api/ai-image/generate/render", json={"spec": SPEC})
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
