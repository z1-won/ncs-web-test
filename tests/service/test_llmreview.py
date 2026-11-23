"""LLM 검토 — 조각·프롬프트·답 검증(가짜 Claude)과 웹 경로(상태 → 실행 → 이전 결과 → JSON·메모 원고).

네트워크를 쓰지 않는다: 웹은 app.state.llm_review_generate, 서비스는 generate 인자로 가짜 Claude를 넣는다.
가짜 Claude는 받은 조각의 첫 줄을 인용해 지적 하나와, 원문에 없는 인용(버려져야 함) 하나를 돌려준다.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "tests" / "fixtures" / "원고_ok_LM1203020201_24v3.hwpx"


CALLS = []


def fake_claude(system, document, request, *, task, tasks):
    CALLS.append(tasks)
    text = dict(re.findall(r"^\[(\d+)\] (.*)$", document, re.M))
    pieces = json.loads(document.split("조각: ", 1)[1])
    said = []
    for name in tasks:
        n = next(x for piece in pieces[name] for x in piece["검수 대상"] if isinstance(x, int))
        said += [{"항목": name, "n": n, "문제": "시험 문제", "인용": text[str(n)][:6], "이유": "시험 근거", "수정 문장": "고친 문장"},
                 {"항목": name, "n": n, "문제": "지어냄", "인용": "원문에 없는 글", "이유": "-", "수정 문장": "-"}]
    return {"model": "fake", "cached": False, "usage": {"input": 1000, "output": 100}, "data": {"지적": said}}


class ServiceTests(unittest.TestCase):
    def test_findings_have_part_reason_fix_and_drop_invented_quotes(self):
        from ncs_llmreview import review_manuscript, to_rows
        CALLS.clear()
        result = review_manuscript(MANUSCRIPT, tasks=["perform3_safety", "eval4_items", "misc3_names"], generate=fake_claude)
        self.assertEqual(CALLS, [["eval4_items", "misc3_names"]])     # 조각 있는 항목 둘을 한 번에(조각 없는 안전·유의는 안 물음)
        self.assertEqual({f["task"] for f in result["findings"]}, {"eval4_items", "misc3_names"})
        f = result["findings"][0]
        for key in ("항목", "위치", "수정해야 하는 부분", "근거_종류", "근거", "수정 방안"):
            self.assertIn(key, f)
        self.assertEqual(f["근거"], "시험 근거")
        self.assertEqual(result["usage"]["dropped"], 2)                              # 항목마다 지어낸 인용 하나씩 버림
        self.assertNotIn("원문에 없는 글", json.dumps(result["findings"], ensure_ascii=False))
        rows = to_rows(result)
        self.assertEqual({r["판정"] for r in rows}, {"판단불가"})                  # LLM 결과는 사람 확인 후보만

    def test_unquoted_source_task(self):
        """출처 검토(008) — 출처 표시 없는 인용: 규칙이 이미 보는 문단(출처 줄이 붙음·(저자, 연도)·인용 부호)은 보내지 않는다."""
        from types import SimpleNamespace

        from ncs_llmreview.chunks import src_unquoted_chunks
        from ncs_llmreview.prompts import build_request, problem_kinds
        lines = ["1-1. 시장 분석",
                 "2023년 국내 소프트웨어 시장 규모는 약 15조 원으로 전년보다 8% 늘었다고 조사되었다.",
                 "홍길동(2020)은 시장 세분화를 고객 집단을 나누는 일이라고 하였다고 설명하였다.",
                 "그림처럼 고객 요구를 수집하는 절차는 네 단계로 이루어진다고 볼 수 있다.",
                 "출처: 집필진 제작(2025)",
                 "“품질은 고객의 명시적·묵시적 요구를 만족시키는 제품 특성의 총체이다”라고 정의하는 경우가 많다.",
                 "짧은 줄"]
        doc = SimpleNamespace(sections=[[], lines], aside_paragraphs=None, section_table_paragraphs=lambda s: frozenset())
        [chunk] = src_unquoted_chunks(doc, "")
        self.assertEqual([x["n"] for x in chunk["검수 대상"]], [1])
        self.assertIn("통계·수치", problem_kinds("src_unquoted"))
        self.assertIn("REQ-02-008", build_request(["src_unquoted"], {}))

    def test_manuscript_text_sent_once_and_split_when_cut(self):
        from ncs_llmreview import claude, review_manuscript
        from ncs_llmreview.service import document_text
        text, targets = document_text({"a": [{"위치": "x", "검수 대상": [{"n": 3, "글": "같은 문단"}]}],
                                       "b": [{"위치": "y", "검수 대상": [{"n": 3, "글": "같은 문단"}]}]})
        self.assertEqual(text.count("같은 문단"), 1)                       # 두 항목이 같은 문단을 봐도 글은 한 번
        self.assertEqual(targets, {"a": {3: "같은 문단"}, "b": {3: "같은 문단"}})

        documents = []

        def cut_when_two(system, document, request, *, task, tasks):
            documents.append(document)
            if len(tasks) > 1:
                raise claude.ClaudeError("출력이 max_tokens에서 잘림")
            return fake_claude(system, document, request, task=task, tasks=tasks)
        CALLS.clear()
        result = review_manuscript(MANUSCRIPT, tasks=["eval4_items", "misc3_names"], generate=cut_when_two)
        self.assertEqual(CALLS, [["eval4_items"], ["misc3_names"]])
        self.assertEqual(len(set(documents)), 1)                            # 나눠 불러도 원고 블록은 같음(캐시 접두)
        self.assertFalse(result["errors"])
        import os
        from unittest import mock
        CALLS.clear()
        with mock.patch.dict(os.environ, {"LLM_REVIEW_BATCH": "1"}):
            review_manuscript(MANUSCRIPT, tasks=["eval4_items", "misc3_names"], generate=fake_claude)
        self.assertEqual(CALLS, [["eval4_items"], ["misc3_names"]])

    def test_unknown_tasks_rejected(self):
        from ncs_llmreview import review_manuscript
        with self.assertRaises(ValueError):
            review_manuscript(MANUSCRIPT, tasks=["없는 항목"], generate=fake_claude)


class WebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.app = create_app(out_dir=self.out.name)
        self.client = TestClient(self.app)
        self.client.__enter__()
        response = self.client.post("/api/uploads", files=[("files", (MANUSCRIPT.name, MANUSCRIPT.read_bytes()))])
        self.assertEqual(response.status_code, 200, response.text)
        self.token = response.json()["upload"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def test_nothing_runs_until_the_button(self):
        """원고를 올려도 LLM 검토 결과는 없다(자동 실행하지 않음) — 실행 경로를 불러야 생긴다."""
        self.app.state.llm_review_generate = fake_claude
        self.assertEqual(self.client.get(f"/api/uploads/{self.token}/llm-review").status_code, 404)
        status = self.client.get("/api/llm-review/status").json()
        self.assertTrue(status["available"])
        self.assertEqual(len(status["tasks"]), 6)                     # 5개 + 출처 표시 없는 인용(008)
        run = self.client.post(f"/api/uploads/{self.token}/llm-review", data={"tasks": "perform3_safety,eval4_items"})
        self.assertEqual(run.status_code, 200, run.text)
        self.assertTrue(run.json()["findings"])
        again = self.client.get(f"/api/uploads/{self.token}/llm-review")
        self.assertEqual(again.json()["findings"], run.json()["findings"])
        self.assertEqual(self.client.get(f"/api/uploads/{self.token}/llm-review/result.json").status_code, 200)
        memo = self.client.get(f"/api/uploads/{self.token}/llm-review/memo")
        self.assertEqual(memo.status_code, 200, memo.text)
        self.assertGreater(json.loads(memo.headers["x-memo-summary"])["placed"], 0)

    def test_status_without_key_explains_why(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "LLM_ALLOW_UPLOAD": ""}):
            status = self.client.get("/api/llm-review/status").json()
        self.assertFalse(status["available"])
        self.assertTrue(status["problem"])


if __name__ == "__main__":
    unittest.main()
