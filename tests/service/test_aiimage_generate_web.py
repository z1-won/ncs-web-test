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

    def test_render_without_font_is_503(self):
        from unittest import mock

        from ncs_aiimage import draw

        with mock.patch.object(draw, "font_paths", side_effect=draw.FontError("글꼴 없음")):
            response = self.client.post("/api/ai-image/generate/render", json={"spec": SPEC})
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
