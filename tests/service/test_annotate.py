"""원고 hwpx에 검수 메모 달기(ncs_service.annotate) — 문단 찾기, 메모 XML 구조, 본문 불변, 웹 엔드포인트."""

import io
import re
import json
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ncs_core import load_document
from ncs_core.hwpx import HP
from ncs_service import ReviewRequest, execute_review
from ncs_service.annotate import Annotator, annotate_hwpx

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
MANUSCRIPT = FIXTURES / "원고_eval_LM1203020201_24v3.hwpx"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"


def bad_rows(*checks):
    out = []
    for check in checks:
        out.extend(r for r in execute_review(ReviewRequest((MANUSCRIPT, PLAN), check)).result.checklist if r["판정"] != "적합")
    return out


class AnnotateTests(unittest.TestCase):
    def test_memos_are_attached_and_text_is_unchanged(self):
        rows = bad_rows("toc", "evaluation", "knowledge")
        self.assertTrue(rows, "픽스처에 지적이 있어야 의미 있는 테스트")
        content, summary = annotate_hwpx(MANUSCRIPT.read_bytes(), rows)
        self.assertEqual(summary["placed"] + summary["unplaced"], len(rows))
        self.assertGreater(summary["placed"], 0)
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.namelist()[0], "mimetype")
            memos = 0
            for name in z.namelist():
                if name.startswith("Contents/section"):
                    root = ET.fromstring(z.read(name))
                    begins = [fb for fb in root.iter(HP + "fieldBegin") if fb.get("type") == "MEMO"]
                    ends = {fe.get("beginIDRef") for fe in root.iter(HP + "fieldEnd")}
                    for fb in begins:
                        self.assertIn(fb.get("id"), ends, "fieldBegin마다 짝 fieldEnd")
                        params = {e.get("name"): e.text for e in fb.find(HP + "parameters")}
                        self.assertEqual(params["MemoShapeIDRef"], "65535")
                        self.assertTrue(fb.find(HP + "subList").findall(HP + "p"))
                    memos += len(begins)
        self.assertEqual(memos, summary["memos"])
        # 본문 문단 글은 그대로(메모 문단은 '본문 밖' 문단으로 분류된다)
        before = load_document(MANUSCRIPT)
        out = Path(ROOT / "tests" / "_annotated.hwpx")
        out.write_bytes(content)
        try:
            after = load_document(out)
        finally:
            out.unlink(missing_ok=True)
        body_before = [t for s in before.sections for t in s if t]
        body_after = [t for i, s in enumerate(after.sections) for j, t in enumerate(s)
                      if t and j not in (after.section_aside_paragraphs(i) or frozenset())]
        self.assertEqual(body_after, body_before)

    def test_memo_text_lists_only_failed_checks_and_suggestion(self):
        row = {"item_id": "F02-차례-①", "판정": "부적합", "체크": {"'~하기' 종결": "X", "기호 글꼴 문자 없음": "O"},
               "비고": {"'~하기' 종결": "'~하기'로 종결되지 않음", "개발계획서": "읽지 못함"}, "수정 제안": "예약 현황 확인하기"}
        lines = Annotator.memo_lines(row)
        self.assertEqual(lines[0], "[차례-①] 부적합")
        self.assertIn("• '~하기' 종결: '~하기'로 종결되지 않음", lines)
        self.assertIn("• 개발계획서: 읽지 못함", lines)
        self.assertTrue(lines[-1].startswith("→ 수정 제안: 예약 현황 확인하기"))
        self.assertFalse(any("기호 글꼴" in line for line in lines))

    def test_unplaced_rows_go_to_summary(self):
        row = {"item_id": "F02-판권-①", "판정": "부적합", "region_path": "section9 > 없는 자리", "원고": None, "체크": {"x": "X"}, "비고": {"x": "없음"}}
        content, summary = annotate_hwpx(MANUSCRIPT.read_bytes(), [row])
        self.assertEqual((summary["placed"], summary["unplaced"], summary["memos"]), (0, 1, 1))
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            text = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("Contents/section"))
        self.assertIn("문단을 특정하지 못한 지적 1건", text)

    def test_each_defect_case_gets_its_own_memo(self):
        # 비고의 사례 줄마다 원고 문구(원고 「…」)가 있는 문단에 메모 하나 — 왜(사례)·어떻게(수정 제안). 문구가 없는 사례(누락)는 행 자리로
        with zipfile.ZipFile(MANUSCRIPT) as z:
            texts = re.findall(r"<hp:t>([^<]{8,})</hp:t>", "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("Contents/section")))
        a, b = texts[0], texts[-1]
        row = {"item_id": "F02-시험-①", "판정": "부적합", "region_path": "section0", "원고": a, "체크": {"① 대조": "X"},
               "비고": {"① 대조": f"1. 원고 「{a}」, 개발계획서 「{a}X」 (글자가 다름)\n2. 원고 「{b}」, 개발계획서 「{b}Y」 (글자가 다름)\n3. 누락: 개발계획서에는 「없는 문구」가 있는데 원고에 없음"},
               "수정 제안": "개발계획서대로 고침"}
        content, summary = annotate_hwpx(MANUSCRIPT.read_bytes(), [row])
        self.assertEqual(summary["unplaced"], 0)
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            sections = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("Contents/section"))
        memos = [re.findall(r"<hp:t>([^<]*)</hp:t>", m) for m in re.findall(r'type="MEMO".*?</hp:subList>', sections, re.S)]
        bodies = [m for m in memos if not m[0].startswith("[F02 자동검수 총괄]")]
        self.assertEqual(len(bodies), 2, memos)                      # 문구 a 자리, 문구 b 자리 (누락 사례는 행 자리 = a 문단에 합쳐짐)
        by_first = {m[1]: m for m in bodies}
        self.assertIn(f"왜: 원고 「{b}」, 개발계획서 「{b}Y」 (글자가 다름)", by_first)
        memo_a = next(m for m in bodies if f"원고 「{a}」" in m[1])
        self.assertEqual(memo_a[0], "[시험-①] ① 대조: 부적합")
        self.assertIn("왜: 누락: 개발계획서에는 「없는 문구」가 있는데 원고에 없음", memo_a)
        self.assertEqual(memo_a.count("어떻게: 개발계획서대로 고침"), 1)

    def test_same_case_from_several_lessons_is_written_once(self):
        # 학습 1·2·3이 글자까지 같은 비고를 내고 한 문단에 모이면(평가 ⑤처럼 원고 문구가 없어 행 자리로 떨어지는 경우)
        # 같은 '[항목] 체크: 판정 / 왜' 블록을 세 번 적지 않고 한 번만, 어느 학습들에서 왔는지 덧붙인다.
        rows = [{"item_id": "F02-평가-⑤", "판정": "판단불가", "region_path": "section9 > 없는 자리", "위치": f"학습 {n}", "원고": None,
                 "체크": {"⑤ 심화·보충 학습 각각 제시": "△"}, "비고": {"⑤ 심화·보충 학습 각각 제시": "낱말로 찾지 못함"},
                 "수정 제안": "평가 방법마다 피드백 블록을 둘 것"} for n in (1, 2, 3)]
        lines = Annotator.case_lines([type("C", (), {"row": r, "check": "⑤ 심화·보충 학습 각각 제시", "line": "낱말로 찾지 못함"})() for r in rows])
        self.assertEqual(lines, ["[평가-⑤] ⑤ 심화·보충 학습 각각 제시: 판단불가", "왜: 낱말로 찾지 못함 (학습 1·학습 2·학습 3)",
                                 "어떻게: 평가 방법마다 피드백 블록을 둘 것"])

    def test_memo_date_is_the_review_time(self):
        # 한글은 Command의 4·5번째 수(UTC FILETIME)로 날짜를 보여 준다. CreateDateTime은 한국 시각 + Z
        from ncs_service.annotate import FILETIME_EPOCH
        from datetime import timedelta
        row = {"item_id": "F02-판권-①", "판정": "부적합", "region_path": "section9 > 없는 자리", "원고": None, "체크": {"x": "X"}, "비고": {"x": "없음"}}
        content, _ = annotate_hwpx(MANUSCRIPT.read_bytes(), [row], created_at="2026-11-02T05:11:46.000Z")
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            sections = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("Contents/section"))
        low, high = re.search(r'name="Command">MEMO/65535/\d+/(\d+)/(\d+)/', sections).groups()
        when = FILETIME_EPOCH + timedelta(microseconds=((int(high) << 32) | int(low)) / 10)
        self.assertEqual(when.isoformat(), "2026-11-02T05:11:46+00:00")
        self.assertIn('name="CreateDateTime">2026-11-02T14:11:46Z<', sections)

    def test_memo_text_uses_editor_char_shape(self):
        # 메모 글자는 에디터 메모와 같게 함초롬돋움 9pt·장평 97%·자간 -2%: header.xml에 글꼴(언어별)·글자 모양을 추가하고 메모 문단만 그것을 가리킨다. 원고 run은 그대로
        row = {"item_id": "F02-판권-①", "판정": "부적합", "region_path": "section9 > 없는 자리", "원고": None, "체크": {"x": "X"}, "비고": {"x": "없음"}}
        content, _ = annotate_hwpx(MANUSCRIPT.read_bytes(), [row])
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            header = z.read("Contents/header.xml").decode("utf-8")
            sections = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("Contents/section"))
        self.assertIn('face="함초롬돋움"', header)
        new_ids = re.findall(r'<hh:charPr id="(\d+)" height="900"', header)
        self.assertEqual(len(new_ids), 1, header)
        added = re.search(rf'<hh:charPr id="{new_ids[0]}".*?</hh:charPr>', header, re.S).group(0)
        self.assertIn('<hh:ratio hangul="97" latin="97"', added)
        self.assertIn('<hh:spacing hangul="-2" latin="-2"', added)
        # 행간 160%: 메모 문단만 새 문단 모양을 가리킨다
        memo = re.search(r'type="MEMO".*?</hp:subList>', sections, re.S).group(0)
        para_ids = re.findall(r'<hp:p [^>]*paraPrIDRef="(\d+)"', memo)
        self.assertEqual(len(set(para_ids)), 1, memo)
        added_para = re.search(rf'<hh:paraPr [^>]*id="{para_ids[0]}".*?</hh:paraPr>', header, re.S).group(0)
        self.assertIn('snapToGrid="0"', added_para)
        self.assertTrue(all('type="PERCENT" value="160"' in ls for ls in re.findall(r"<hh:lineSpacing[^>]*/>", added_para)) and "lineSpacing" in added_para, added_para)
        self.assertEqual(set(re.findall(r'<hp:run charPrIDRef="(\d+)"><hp:t>', memo)), {new_ids[0]})


class WebAnnotateTests(unittest.TestCase):
    def test_endpoint_needs_token_and_hwpx_manuscript(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        rows = bad_rows("toc")
        with TestClient(create_app(out_dir=ROOT / "tests" / "_annotate_out")) as client:
            token = client.post("/api/uploads", files=[("files", (p.name, p.read_bytes())) for p in (MANUSCRIPT, PLAN)]).json()
            response = client.post("/api/export/annotated", data={"upload": token["upload"], "rows": json.dumps(rows), "module_code": "LM1203020201_24v3"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.content.startswith(b"PK"))
            self.assertIn("placed", json.loads(response.headers["x-memo-summary"]))
            self.assertEqual(client.post("/api/export/annotated", data={"upload": "nope", "rows": "[]"}).status_code, 400)
            self.assertEqual(client.post("/api/export/annotated", data={"upload": token["upload"], "rows": "{}"}).status_code, 400)
            plan_only = client.post("/api/uploads", files=[("files", (PLAN.name, PLAN.read_bytes()))]).json()
            self.assertEqual(client.post("/api/export/annotated", data={"upload": plan_only["upload"], "rows": "[]"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
