"""평가 ①의 확정 비교·불확실성 처리·독립 영역 검증."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from ncs_core import load_document
from ncs_evaluation import CheckConfig, prepare_review, evaluate_review
from ncs_evaluation.rules.names import compare_table
from ncs_web.server import create_app

FIXTURES = Path(__file__).parent / "fixtures"


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.ms = load_document(next(FIXTURES.glob("원고_ok*")))
        self.plan = load_document(next(FIXTURES.glob("개발계획서*")))

    def result(self, ms=None, plan=True):
        return evaluate_review(prepare_review(ms or self.ms, self.plan if plan else None))

    @staticmethod
    def item_one(result):
        """①의 행만. ②③은 같은 구역을 다른 기준으로 보므로 ① 검증에서는 뺀다."""
        return [r for r in result.checklist if r["item_id"] == "F02-평가-①"]

    def test_complete_fixture_passes_item_one(self):
        result = self.result()
        rows = self.item_one(result)
        self.assertEqual({r["판정"] for r in rows}, {"적합"})
        self.assertEqual(result.sheet[0]["검수결과"], "적합")
        self.assertEqual(result.sheet[3]["검수결과"], "판단불가")  # ④: 합성 원고의 평가 항목 '항목'은 예시 어미가 아니라 사람 확인
        self.assertEqual(len([r for r in rows if "평가 준거 >" in r["region_path"]]), 2)
        self.assertEqual(len([r for r in rows if "평가 방법 >" in r["region_path"]]), 2)

    def test_no_plan_does_not_fall_back_to_toc(self):
        self.assertEqual(self.result(plan=False).sheet[0]["검수결과"], "판단불가")

    def test_missing_method_table_cannot_pass(self):
        tables = [t for t in self.ms.tables if "학습 목표" in t["cells"].values() or t["section"] == 0]
        result = self.result(replace(self.ms, tables=tables))
        method_rows = [r for r in self.item_one(result) if r["region_path"].endswith("평가 방법")]
        self.assertEqual(len(method_rows), 2)
        self.assertEqual({r["판정"] for r in method_rows}, {"판단불가"})

    def test_each_evaluation_kind_is_compared_independently(self):
        tables = deepcopy(self.ms.tables)
        target = next(t for t in tables if t["section"] == 1 and "학습 목표" not in t["cells"].values())
        target["cells"][(1, 0)] = "잘못된 학습 내용명"
        result = self.result(replace(self.ms, tables=tables))
        rows = self.item_one(result)
        self.assertTrue(any(r["판정"] == "부적합" and "평가 방법" in r["region_path"] for r in rows))
        self.assertTrue(all(r["판정"] == "적합" for r in rows if "평가 준거" in r["region_path"]))

    def test_split_heading_inside_table_and_non_evaluation_tables(self):
        """실데이터 양식: '1-1.'과 제목이 다른 문단이고 둘 다 틀(표) 안. 피드백·내비게이터 표는 평가표가 아니므로 조용히 건너뛴다."""
        sections = deepcopy(self.ms.sections)
        body = sections[1]
        i = body.index("1-1. 현행 시스템 분석")
        body[i:i + 1] = ["1-1.", "현행 시스템 분석"]
        shift = lambda p: p + 1 if p > i else p  # 문단이 하나 늘어난 만큼 뒤 표 위치를 민다
        tables = [dict(t, paragraph=shift(t["paragraph"])) if t["section"] == 1 else t for t in deepcopy(self.ms.tables)]
        table_paragraphs = [self.ms.table_paragraphs[0], frozenset({shift(p) for p in self.ms.table_paragraphs[1]} | {i, i + 1})]
        eval_start = next(p for p, t in enumerate(body) if t.strip() in ("평 가", "평가"))
        tables.append({"section": 1, "paragraph": eval_start + 1, "rows": 1, "cols": 2,
                       "cells": {(0, 0): "1. 서술형 시험", (0, 1): "피드백 내용"}, "styles": None})
        ms = replace(self.ms, sections=sections, tables=tables, table_paragraphs=table_paragraphs)
        rows = self.item_one(self.result(ms))
        self.assertEqual({r["판정"] for r in rows}, {"적합"}, [r for r in rows if r["판정"] != "적합"])

    def test_numbered_names_are_compared_by_id_not_order(self):
        expected = {(1, 1): "가 분석", (1, 2): "나 분석"}
        self.assertEqual(compare_table("표", [(1, "1-2. 나 분석"), (2, "1-1. 가 분석")], expected)["판정"], "적합")
        self.assertEqual(compare_table("표", [(1, "1-2. 가 분석"), (2, "1-1. 나 분석")], expected)["판정"], "부적합")

    def test_repeated_and_mixed_names_are_resolved_exactly(self):
        expected = {(1, 1): "가", (1, 2): "나"}
        for values in ([(1, "가"), (2, "가"), (3, "나")],
                       [(1, "1-1. 가"), (2, "나")],
                       [(1, "1-1. 가"), (2, "1-1. 가"), (3, "1-2. 나")]):
            self.assertEqual(compare_table("표", values, expected)["판정"], "적합")
        self.assertEqual(compare_table("표", [(1, "가"), (2, "가")], expected)["판정"], "부적합")
        self.assertEqual(compare_table("표", [], expected)["판정"], "판단불가")
        ambiguous = {(1, 1): "같은 이름", (1, 2): "같은 이름"}
        self.assertEqual(compare_table("표", [(1, "같은 이름")], ambiguous)["판정"], "판단불가")
        self.assertEqual(compare_table("표", [(1, "1-1. 가"), (2, "1-1. 틀린 이름")], expected)["판정"], "부적합")

    def test_multiple_complete_method_tables_can_pass_individually(self):
        tables = deepcopy(self.ms.tables)
        target = next(t for t in tables if t["section"] == 1 and "학습 목표" not in t["cells"].values())
        tables.append(deepcopy(target))
        self.assertEqual(self.result(replace(self.ms, tables=tables)).sheet[0]["검수결과"], "적합")

    def test_missing_extra_and_substantive_whitespace_difference(self):
        expected = {(1, 1): "시스템 분석", (1, 2): "요구 정의"}
        for values in ([(1, "시스템 분석")], [(1, "시스템 분석"), (2, "요구 정의"), (3, "추가")],
                       [(1, "시스템분석"), (2, "요구 정의")]):
            self.assertEqual(compare_table("표", values, expected)["판정"], "부적합")
        self.assertEqual(compare_table("표", [(1, "시스템\n분석"), (2, "요구 정의")], expected)["판정"], "적합")

    def test_no_body_boundaries_cannot_pass_but_hwp_can(self):
        context = prepare_review(self.ms, self.plan)
        body = deepcopy(context.body)
        body["lessons"] = []
        result = evaluate_review(replace(context, body=body))
        self.assertEqual(result.sheet[0]["검수결과"], "판단불가")
        # hwp는 표 안/밖 구분이 없지만 ①은 제목을 표 안에서도 읽으므로 hwpx와 같은 판정을 낸다
        result = self.result(replace(self.ms, format="hwp", table_paragraphs=None))
        self.assertEqual(result.sheet[0]["검수결과"], "적합")

    def test_duplicate_body_heading_cannot_be_silently_deduplicated(self):
        sections = deepcopy(self.ms.sections)
        index = sections[1].index("현행 시스템을 분석한다.")
        sections[1][index] = "1-1. 현행 시스템 분석"
        self.assertEqual(self.result(replace(self.ms, sections=sections)).sheet[0]["검수결과"], "판단불가")

    def test_unknown_table_in_evaluation_cannot_pass(self):
        tables = deepcopy(self.ms.tables)
        target = next(t for t in tables if t["section"] == 1)
        target["cells"][(0, 0)] = "인식 불가 머리글"
        self.assertEqual(self.result(replace(self.ms, tables=tables)).sheet[0]["검수결과"], "판단불가")

    def test_split_tables_are_not_reported_as_missing_names(self):
        tables = deepcopy(self.ms.tables)
        target = next(t for t in tables if t["section"] == 1)
        part = deepcopy(target)
        target["cells"] = {k: v for k, v in target["cells"].items() if k[0] != 2}
        part["cells"] = {k: v for k, v in part["cells"].items() if k[0] != 1}
        tables.append(part)
        result = self.result(replace(self.ms, tables=tables))
        self.assertEqual(result.sheet[0]["검수결과"], "판단불가")

    def test_body_heading_in_wrong_lesson_fails(self):
        sections = deepcopy(self.ms.sections)
        a = sections[1].index("1-1. 현행 시스템 분석")
        b = sections[1].index("2-1. UI 요구사항 확인")
        sections[1][a], sections[1][b] = sections[1][b], sections[1][a]
        self.assertEqual(self.result(replace(self.ms, sections=sections)).sheet[0]["검수결과"], "부적합")

    def test_relocated_sections_and_invalid_config(self):
        tables = deepcopy(self.ms.tables)
        for table in tables:
            table["section"] = 1 - table["section"]
        ms = replace(self.ms, sections=list(reversed(self.ms.sections)), tables=tables,
                     table_paragraphs=list(reversed(self.ms.table_paragraphs)))
        result = evaluate_review(prepare_review(ms, self.plan, config=CheckConfig(front_section=1, body_section=0)))
        self.assertEqual(result.sheet[0]["검수결과"], "적합")
        with self.assertRaises(ValueError):
            CheckConfig(front_section=1, body_section=1)

    def test_web_upload_evaluation(self):
        with tempfile.TemporaryDirectory() as out:
            with TestClient(create_app(out_dir=out, database_url="")) as client:
                files = [("files", (doc.path.name, doc.path.read_bytes(), "application/octet-stream"))
                         for doc in (self.ms, self.plan)]
                response = client.post("/api/review", data={"check": "evaluation"}, files=files)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["검수확인서"][0]["검수결과"], "적합")


if __name__ == "__main__":
    unittest.main()
