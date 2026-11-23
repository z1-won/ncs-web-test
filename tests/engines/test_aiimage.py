"""AI 활용 표기와 생성형 AI 결과물 현황(REQ-02-006 ③④⑤) — 쓴 줄을 다시 읽으면 같은 값, 넣은 원고는 그 밖의 글이 그대로, 현황은 원고 표기와 같다.

정의서 검증 기준: 표기 문구 삽입 100%, 생성함/수정 보완함 구분 오차율 0.5% 이내, 결과물 현황표와 원고 표기 일치 100%.
"""

import io
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

import rights_samples as S
from ncs_aiimage import NOTICE, build_xlsx, inspect, insert_marks, mark_pictures, marked_copy, preview, source_copy
from ncs_aiimage.marking import Mark
from ncs_core.documents import load_document
from ncs_core.figures import MODE_WORDS, ai_line, clean_tool, manuscript_figures, marking_lines, object_particle, parse_ai_mark
from ncs_rights.check import Options
from ncs_rights.service import run

TOOLS = ("ChatGPT", "ChatGPT 6.0", "Gemini 3", "DALL-E 3", "Midjourney", "미드저니", "제미나이", "클로드", "Copilot (GPT-5.1)",
         "Real-ESRGAN", "waifu2x", "Adobe Firefly", "Stable Diffusion XL", "뤼튼", "한글 2024 AI")
DAYS = (date(2026, 1, 1), date(2026, 7, 20), date(2026, 11, 23), date(2026, 12, 31), date(2024, 2, 29))


class MarkTextTests(unittest.TestCase):
    def test_written_line_reads_back_the_same(self):
        """삽입 100%·구분 오차율: 도구 15 × 방식 2 × 날짜 5 = 150줄 모두 같은 값으로 다시 읽혀야 한다."""
        wrong = []
        for tool in TOOLS:
            for mode in MODE_WORDS:
                for day in DAYS:
                    line = ai_line(tool, mode, day)
                    read = parse_ai_mark(line)
                    if read is None or (read.tool, read.mode, read.on) != (tool, mode, day):
                        wrong.append(line)
        self.assertEqual(wrong, [])

    def test_particle_follows_the_last_sound(self):
        self.assertEqual([object_particle(word) for word in ("ChatGPT", "Real-ESRGAN", "waifu2x", "미드저니", "뤼튼", "Gemini 3", "DALL-E 2", "Copilot (GPT-5.1)")],
                         ["를", "을", "를", "를", "을", "을", "를", "을"])

    def test_tool_name_that_cannot_be_read_back_is_refused(self):
        for bad in ("", "   ", "A" * 41, "ChatGPT, Gemini", "v.2", "GPT 6."):
            with self.assertRaises(ValueError, msg=bad):
                clean_tool(bad)
        self.assertEqual(clean_tool("  ChatGPT   6.0 "), "ChatGPT 6.0")
        with self.assertRaises(ValueError):
            ai_line("ChatGPT", "edited", date(2026, 7, 20))

    def test_three_lines_in_order_and_no_invented_source(self):
        lines = marking_lines(source_line="출처: 집필진 제작(2026)", tool="ChatGPT", mode="generated", on=date(2026, 7, 20), label="그림 1-1", title="개념도")
        self.assertEqual(lines, ["출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 7. 20.", "[그림 1-1] 개념도"])
        self.assertEqual(len(marking_lines(source_line="", tool="ChatGPT", mode="modified", on=date(2026, 7, 20), label="그림 1-2", title="예시")), 2)


class MarkedManuscriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.manuscript = S.manuscript(self.folder)
        self.rows = inspect(self.manuscript)["그림"]

    def marks(self, labels, tool="Gemini 3", mode="modified", day="2026-11-23"):
        return [{"key": row["key"], "tool": tool, "mode": mode, "date": day} for row in self.rows if row["그림 번호"] in labels]

    def test_inspect_lists_figures_marks_and_notice(self):
        body = inspect(self.manuscript)
        self.assertEqual([row["그림 번호"] for row in body["그림"]], [label for label, *_ in S.FIGURES])
        self.assertEqual(body["요약"], {"그림": 8, "AI 표기 있음": 1, "출처 줄 없음": 0})
        self.assertEqual(body["그림"][0]["AI 표기"]["도구"], "ChatGPT")
        self.assertTrue(all(row["그림 파일"] for row in body["그림"]))
        self.assertEqual(len(body["유의 안내"]["항목"]), len(NOTICE))
        self.assertTrue(body["표기 넣기"])

    def test_inserted_marks_read_back_and_nothing_else_changes(self):
        before = load_document(self.manuscript)
        content, summary = marked_copy(self.manuscript, self.marks({"그림 1-2", "그림 2-1", "그림 2-4"}) + self.marks({"그림 1-1"}, tool="ChatGPT"))
        self.assertEqual([item["그림"] for item in summary["넣음"]], ["그림 1-2", "그림 2-1", "그림 2-4"])
        self.assertEqual(summary["이미 있음"], ["그림 1-1"])           # 이미 AI 활용 줄이 있는 그림에는 두 번 적지 않는다
        self.assertEqual((summary["다시 읽기"], summary["넣지 못함"]), (3, []))
        marked = self.folder / "marked.hwpx"
        marked.write_bytes(content)
        after = load_document(marked)
        figures = {figure.label: figure for figure in manuscript_figures(after)}
        for label in ("그림 1-2", "그림 2-1", "그림 2-4"):
            self.assertEqual((figures[label].ai.tool, figures[label].ai.mode, figures[label].ai.on), ("Gemini 3", "modified", date(2026, 11, 23)), label)
        self.assertIsNone(figures["그림 1-3"].ai)
        self.assertEqual({label: figure.source_line for label, figure in figures.items()},
                         {figure.label: figure.source_line for figure in manuscript_figures(before)})        # 출처 줄은 그대로
        line = "Gemini 3을 활용하여 수정 보완함. 2026. 11. 23."
        kept = [text for text in after.sections[0] if text != line]
        self.assertEqual(kept, before.sections[0])                                                           # 넣은 줄 말고는 한 글자도 같다
        self.assertEqual(after.sections[0].count(line), 3)
        position = after.sections[0].index("[그림 1-2] NCS학습모듈 활용 예시")
        self.assertEqual(after.sections[0][position - 2:position], [S.FIGURES[1][2], line])                 # 출처 줄 → AI 줄 → 캡션
        with zipfile.ZipFile(self.manuscript) as old, zipfile.ZipFile(io.BytesIO(content)) as new:
            self.assertEqual(old.namelist(), new.namelist())
            for name in old.namelist():
                if name != "Contents/section0.xml":
                    self.assertEqual(old.read(name), new.read(name), name)                                    # 그림 파일과 나머지 항목은 바이트 그대로

    def test_bad_requests_say_what_to_fix(self):
        for marks, word in (([], "골라"), ([{"key": "9:9", "tool": "A", "mode": "modified", "date": "2026-11-23"}], "다시 읽어"),
                            (self.marks({"그림 1-2"}, tool=""), "도구 이름"), (self.marks({"그림 1-2"}, day="11/23"), "YYYY-MM-DD"),
                            (self.marks({"그림 1-2"}, mode="edited"), "활용 방식"), (self.marks({"그림 1-1"}), "이미 AI 활용 줄")):
            with self.assertRaises(ValueError) as caught:
                marked_copy(self.manuscript, marks)
            self.assertIn(word, str(caught.exception))

    def test_marks_that_do_not_point_at_a_caption_are_reported(self):
        document = load_document(self.manuscript)
        figures = manuscript_figures(document)
        _content, summary = insert_marks(self.manuscript.read_bytes(), [Mark(0, 0, "A", "modified", date(2026, 1, 1)), Mark(3, 1, "A", "modified", date(2026, 1, 1))], figures, [len(section) for section in document.sections])
        self.assertEqual(len(summary["넣지 못함"]), 2)
        self.assertEqual(summary["넣음"], [])

    def test_place_is_found_when_the_reader_re_divides_sections(self):
        """구역 하나짜리 원고는 읽을 때 앞부분과 본문 두 구역으로 나뉜다 — 그림의 (구역, 문단)이 파일의 것과 달라도 제자리에 넣는다."""
        parts = [S.p("차 례"), S.p("학습 1. 학습모듈 이해하기"), S.p("핵심 용어"), S.p("학습 1"), S.p("본문 문장이다."),
                 S._pic("image1"), S.p("출처: 집필진 제작(2026)"), S.p("[그림 1-1] 개념도"), S.p("이어지는 문장이다."),
                 S._pic("image2"), S.p("[그림 1-2] 출처 줄이 없는 그림")]
        path = S._write(self.folder / "한구역_LM1203020201_24v3.hwpx", parts, {"image1": S.png(1), "image2": S.png(2)})
        document = load_document(path)
        self.assertEqual((len(document.sections), document.layout["결과"]), (2, "나눔"))
        rows = inspect(path)["그림"]
        self.assertEqual([(row["구역"], row["그림 번호"], bool(row["출처 줄"])) for row in rows], [(1, "그림 1-1", True), (1, "그림 1-2", False)])
        content, summary = marked_copy(path, [{"key": row["key"], "tool": "ChatGPT", "mode": "generated", "date": "2026-07-20"} for row in rows])
        self.assertEqual((len(summary["넣음"]), summary["다시 읽기"], summary["넣지 못함"]), (2, 2, []))
        marked = self.folder / "한구역_표기.hwpx"
        marked.write_bytes(content)
        texts = [text for section in load_document(marked).sections for text in section]
        line = "ChatGPT를 활용하여 생성함. 2026. 7. 20."
        self.assertEqual(texts[6:9] + texts[-2:], ["출처: 집필진 제작(2026)", line, "[그림 1-1] 개념도", line, "[그림 1-2] 출처 줄이 없는 그림"])
        self.assertTrue(all(figure.ai and figure.ai.mode == "generated" for figure in manuscript_figures(load_document(marked))))

    def test_source_line_goes_above_the_ai_line_and_only_where_there_is_none(self):
        """이미지 추천의 출처 문구 넣기(REQ-02-011): 출처 줄 → AI 활용 줄 → 그림 번호 순서를 지키고, 이미 출처 줄이 있으면 넣지 않는다."""
        parts = [S.p("본문 문장이다."), S._pic("image1"), S.p("[그림 1-1] 출처 줄이 없는 그림"), S.p("이어지는 문장이다."),
                 S._pic("image2"), S.p("ChatGPT를 활용하여 수정 보완함. 2026. 7. 20."), S.p("[그림 1-2] AI 활용 줄만 있는 그림"),
                 S._pic("image3"), S.p("출처: 집필진 제작(2026)"), S.p("[그림 1-3] 출처 줄이 있는 그림")]
        path = S._write(self.folder / "출처없음_LM1203020201_24v3.hwpx", parts, {f"image{n}": S.png(n) for n in (1, 2, 3)})
        rows = {row["그림 번호"]: row for row in inspect(path)["그림"]}
        credit = "출처: 한국관광공사(2025). 호텔 로비. 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 7. 1. 검색. 공공누리 제1유형."
        for label, expected in (("그림 1-1", [credit, "[그림 1-1] 출처 줄이 없는 그림"]),
                                ("그림 1-2", [credit, "ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.", "[그림 1-2] AI 활용 줄만 있는 그림"])):
            content, summary = source_copy(path, rows[label]["key"], credit)
            self.assertEqual((summary["넣음"], summary["줄"]), (label, credit))
            copy = self.folder / f"{label}.hwpx"
            copy.write_bytes(content)
            texts = load_document(copy).sections[0]
            at = texts.index(credit)
            self.assertEqual(texts[at:at + len(expected)], expected)
            self.assertEqual([text for text in texts if text != credit], load_document(path).sections[0])
            self.assertEqual({figure.label: figure.source_line for figure in manuscript_figures(load_document(copy))}[label], credit)
        for key, text, word in ((rows["그림 1-3"]["key"], credit, "이미 출처 줄"), (rows["그림 1-1"]["key"], "한국관광공사(2025)", "출처: "),
                                ("9:9", credit, "없는 그림"), (rows["그림 1-1"]["key"], "출처: " + "가" * 500, "500자")):
            with self.assertRaises(ValueError) as caught:
                source_copy(path, key, text)
            self.assertIn(word, str(caught.exception))

    def test_results_match_the_marks_in_the_manuscript(self):
        """현황표와 원고 표기 일치 100%: 표기를 넣은 원고와 그 현황으로 권리 증빙 점검을 돌리면 현황 쪽 지적이 없어야 한다."""
        marks = self.marks({"그림 1-2", "그림 2-2", "그림 2-5"}, tool="Midjourney", mode="generated", day="2026-08-03")
        shown = preview(self.manuscript, marks)
        self.assertEqual([row["결과물 명"] for row in shown["현황"]],
                         ["그림 1-1 NCS학습모듈 개념도", "그림 1-2 NCS학습모듈 활용 예시", "그림 2-2 실습실 배치도", "그림 2-5 목록에 없는 그림"])
        self.assertEqual([row["활용 AI"] for row in shown["현황"]], ["ChatGPT", "Midjourney", "Midjourney", "Midjourney"])
        self.assertEqual([row["순번"] for row in shown["현황"]], [1, 2, 3, 4])
        self.assertIn("이번에 넣을 표기", shown["현황"][1]["비고"])
        self.assertEqual(shown["표기"][0]["줄"], [S.FIGURES[1][2], "Midjourney를 활용하여 생성함. 2026. 8. 3.", "[그림 1-2] NCS학습모듈 활용 예시"])
        content, _ = marked_copy(self.manuscript, marks)
        marked = self.folder / S.MANUSCRIPT_NAME.replace(".hwpx", "_AI표기.hwpx")
        marked.write_bytes(content)
        rows = [[str(row["순번"]), row["결과물 명"], row["학습모듈 해당 쪽수"] or "p.1", row["활용 AI"], row["비고"]] for row in preview(marked, [])["현황"]]
        self.assertEqual(len(rows), 4)
        form = S.form(self.folder, "AI서약서_자동.hwpx", S.ai_table(rows))
        report = run(marked, [form], Options(pledge=True))
        kinds = {finding["종류"] for finding in report["지적사항"]}
        self.assertFalse(kinds & {"현황 누락", "활용 AI 다름", "현황에만 있음", "AI 표시 확인", "AI 표기 일자"}, kinds)
        self.assertEqual(sum(1 for row in report["현황표"] if row["AI 방식"]), 4)

    def test_no_derivative_originals_are_kept_out_of_ai_marks(self):
        """REQ-02-006 ⑥: 공공누리 제3·4유형(변경금지) 원본은 AI 수정 보완·생성 재료에서 제외한다(검증: 변경금지 원본의 수정 보완 0건).
        제2·4유형 원본을 쓴 결과물은 비상업 조건을 표시하고 원본 유형을 현황에 적는다."""
        kogl = "출처: 고용노동부(2025). 직업훈련 통계. 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 7. 1. 검색. 공공누리 제{}유형."
        figures = [("그림 1-1", "변경금지 그림", kogl.format(3), ""), ("그림 1-2", "비상업 그림", kogl.format(2), ""),
                   ("그림 1-3", "비상업 변경금지 그림", kogl.format(4), ""), ("그림 1-4", "자유 그림", kogl.format(1), ""),
                   ("그림 1-5", "이미 표기된 변경금지 그림", kogl.format(3), "ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.")]
        path = S.manuscript(self.folder, figures, name="LM1203020201_24v3_공공누리.hwpx")
        rows = {row["그림 번호"]: row for row in inspect(path)["그림"]}
        self.assertEqual([(rows[f"그림 1-{n}"]["공공누리"] or {}).get("유형") for n in (1, 2, 3, 4)], ["3", "2", "4", "1"])
        self.assertEqual([bool((rows[f"그림 1-{n}"]["공공누리"] or {}).get("변경금지")) for n in (1, 2, 3, 4)], [True, False, True, False])
        marks = [{"key": row["key"], "tool": "Gemini 3", "mode": "modified", "date": "2026-11-23"} for row in rows.values()]
        content, summary = marked_copy(path, marks)
        self.assertEqual([item["그림"] for item in summary["넣음"]], ["그림 1-2", "그림 1-4"])
        self.assertEqual([item["그림"] for item in summary["변경금지 원본 제외"]], ["그림 1-1", "그림 1-3", "그림 1-5"])
        self.assertIn("제3유형", summary["변경금지 원본 제외"][0]["이유"])
        marked = self.folder / "marked_kogl.hwpx"
        marked.write_bytes(content)
        after = {figure.label: figure for figure in manuscript_figures(load_document(marked))}
        self.assertIsNone(after["그림 1-1"].ai)                    # 변경금지 원본에는 표기를 넣지 않았다
        self.assertIsNone(after["그림 1-3"].ai)
        with self.assertRaises(ValueError) as caught:              # 변경금지 그림만 고르면 넣을 것이 없다 — 이유를 말한다
            marked_copy(path, [mark for mark in marks if mark["key"] in (rows["그림 1-1"]["key"], rows["그림 1-3"]["key"])])
        self.assertIn("변경금지", str(caught.exception))
        shown = preview(path, marks)
        self.assertEqual([item["그림"] for item in shown["변경금지 원본 제외"]], ["그림 1-1", "그림 1-3", "그림 1-5"])
        by_name = {row["결과물 명"].split(" ")[1]: row["비고"] for row in shown["현황"]}
        self.assertIn("비상업", by_name["1-2"])                    # 제2유형 원본을 쓴 결과물: 비상업 조건
        self.assertIn("공공누리 제2유형", by_name["1-2"])
        self.assertIn("변경금지 원본", by_name["1-5"])              # 이미 표기가 있는 변경금지 원본은 확인하라고 알린다
        self.assertNotIn("1-1", by_name)

    def test_xlsx_has_the_form_columns_and_keeps_text_as_text(self):
        from openpyxl import load_workbook

        rows = preview(self.manuscript, self.marks({"그림 1-3"}, tool="=HYPERLINK"))["현황"]
        sheet = load_workbook(io.BytesIO(build_xlsx(rows, manuscript=self.manuscript.name))).active
        self.assertEqual([cell.value for cell in sheet[4]], ["순번", "결과물 명", "학습모듈 해당 쪽수", "활용 AI", "비고"])
        self.assertEqual([sheet.cell(5, 2).value, sheet.cell(6, 4).value, sheet.cell(6, 4).data_type], ["그림 1-1 NCS학습모듈 개념도", "=HYPERLINK", "s"])

    def test_pictures_chosen_by_file_get_the_mark_on_their_caption(self):
        content, summary = mark_pictures(self.manuscript, self.manuscript.read_bytes(), {"image3": "Real-ESRGAN", "image1": "waifu2x", "nope": "X"},
                                         on=date(2026, 11, 23))
        self.assertEqual(([item["그림"] for item in summary["넣음"]], summary["이미 있음"], summary["캡션 없음"]), (["그림 1-3"], ["그림 1-1"], ["nope"]))
        self.assertEqual(summary["넣음"][0]["줄"], "Real-ESRGAN을 활용하여 수정 보완함. 2026. 11. 23.")
        self.assertNotEqual(content, self.manuscript.read_bytes())


class WebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.client = TestClient(create_app(out_dir=self.folder / "out", dist_dir=self.folder / "no_build"))
        self.manuscript = S.manuscript(self.folder)

    def post(self, path, marks=None, name=None):
        files = {"manuscript": (name or self.manuscript.name, self.manuscript.read_bytes())}
        return self.client.post(f"/api/ai-image/{path}", files=files, data={} if marks is None else {"marks": json.dumps(marks)})

    def test_figures_preview_marked_and_results(self):
        body = self.post("figures").json()
        self.assertEqual((body["요약"]["그림"], len(body["유의 안내"]["항목"])), (8, 5))
        marks = [{"key": body["그림"][2]["key"], "tool": "ChatGPT 6.0", "mode": "modified", "date": "2026-11-23"}]
        shown = self.post("preview", marks).json()
        self.assertEqual((len(shown["표기"]), len(shown["현황"]), shown["쪽수"]), (1, 2, False))
        marked = self.post("marked", marks)
        self.assertEqual(marked.status_code, 200, marked.text)
        self.assertEqual(json.loads(marked.headers["x-ai-summary"]), {"넣음": 1, "이미 있음": 0, "넣지 못함": 0, "다시 읽기": 1})
        self.assertIn("_AI%ED%91%9C%EA%B8%B0.hwpx", marked.headers["content-disposition"])
        again = self.client.post("/api/ai-image/figures", files={"manuscript": ("marked.hwpx", marked.content)}).json()
        self.assertEqual(again["그림"][2]["AI 표기"], {"도구": "ChatGPT 6.0", "방식": "modified", "일자": "2026. 11. 23.", "글": "ChatGPT 6.0을 활용하여 수정 보완함. 2026. 11. 23."})
        sheet = self.post("results", marks)
        self.assertEqual((sheet.status_code, json.loads(sheet.headers["x-ai-summary"])), (200, {"현황": 2}))
        self.assertEqual(sheet.content[:2], b"PK")

    def test_source_line_copy(self):
        files = {"manuscript": (self.manuscript.name, self.manuscript.read_bytes())}
        key = self.post("figures").json()["그림"][0]["key"]
        refused = self.client.post("/api/ai-image/source", files=files, data={"key": key, "credit": "출처: 집필진 제작(2026)"})
        self.assertEqual(refused.status_code, 400)                     # 시험 원고의 그림에는 모두 출처 줄이 있다
        self.assertIn("이미 출처 줄", refused.json()["error"])

    def test_errors_are_400_with_a_reason(self):
        self.assertEqual(self.post("marked", []).status_code, 400)
        self.assertEqual(self.post("preview", [{"key": "x"}]).status_code, 400)
        self.assertIn("JSON", self.client.post("/api/ai-image/preview", files={"manuscript": ("a.hwpx", self.manuscript.read_bytes())}, data={"marks": "{"}).json()["error"])
        self.assertEqual(self.client.post("/api/ai-image/figures", files={"manuscript": ("a.hwpx", b"not a file")}).status_code, 400)


class RegisterTests(unittest.TestCase):
    def test_upscaled_pictures_become_image_records_with_ai_fields(self):
        from ncs_service.images import ai_register
        from ncs_service.images.image_db import LoadReport

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            manuscript = S.manuscript(folder)
            work = folder / "work"
            work.mkdir()
            for bin_id, engine in (("image2", "esrgan-best"), ("image9", "waifu2x-photo")):
                (work / f"{bin_id}.bin").write_bytes(S.png(99, 80, 60))
                (work / f"{bin_id}.json").write_text(json.dumps({"bin_id": bin_id, "status": "완료", "engine": engine, "target_dpi": 300,
                                                                "new_href": f"BinData/{bin_id}.png", "media_type": "image/png"}), encoding="utf-8")
            with mock.patch("ncs_service.images.image_db.load_records", return_value=LoadReport(total=1, created=1)) as load:
                result = ai_register.register_upscaled("dsn", manuscript, work, "LM1203020201_24v3", by="김에디터", on=date(2026, 11, 23), target_dpi=300)
            records = load.call_args.args[1]
        self.assertEqual(result, {"그림": 1, "새 그림": 1, "확정 유지": 0, "캡션 없음": ["image9"], "거부": []})
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["rights"], {"ai": {"used": True, "usage": 3, "mode": "modified", "tool": "Real-ESRGAN", "date": "2026-11-23",
                                                   "original_source": "홍길동(2024). 직업교육 사례집. 한국출판. p.12."}})
        self.assertEqual((record["placements"][0]["label"], record["placements"][0]["module_code"], record["upscaled"]["engine"]),
                         ("그림 1-2", "LM1203020201_24v3", "esrgan-best"))
        self.assertEqual(record["content"], S.png(2))
        from ncs_service.images.image_records import normalize
        self.assertEqual(normalize(record).rights["ai_usage"], 3)             # 이미지 레코드 형식 검사를 통과한다


if __name__ == "__main__":
    unittest.main()
