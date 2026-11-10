"""차례 ⑦(쪽수 일치) 규칙 — 출력본에서 찾은 제목 쪽(headings)을 가짜로 넣어 판정 경로를 하나씩 본다."""

import unittest
from pathlib import Path

from ncs_toc import run_review
from ncs_toc.rules.pages import CHECK, check_toc7, toc_targets

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PRINT_COPY = FIXTURES / "출력본_ok_LM1203020201_24v3.pdf"

TOC = {
    "학습": [{"no": 1, "text": "요구사항 확인하기", "page": "1"}],
    "내용": [{"no": 1, "sub": 1, "text": "현행 시스템 분석", "page": "3"}, {"no": 1, "sub": 2, "text": "요구사항 정의", "page": None}],
    "줄": [{"lesson": 1, "kind": "평가", "page": "12", "after": 2}],
    "꼬리": {"참고 자료": "40"},
    "쪽 깨짐": ["1-2"],
}


def heading(folio, source="읽음", index=0):
    return {"folio": folio, "source": source, "index": index, "line": ""}


def by_key(rows):
    return {row["region_path"].split(" > ")[-1]: row for row in rows}


class TocTargetsTests(unittest.TestCase):
    def test_every_toc_line_becomes_a_target_with_the_parser_key(self):
        self.assertEqual(toc_targets(TOC), [
            ("학습 1", "학습 1. 요구사항 확인하기", "1"),
            ("1-1", "1-1. 현행 시스템 분석", "3"),
            ("1-2", "1-2. 요구사항 정의", None),
            ("학습 1 평가", "학습 1 • 평가", "12"),
            ("참고 자료", "참고 자료", "40"),
        ])


class RuleTests(unittest.TestCase):
    def test_without_print_copy_one_undecided_row_explains_why(self):
        [row] = check_toc7(TOC, None)
        self.assertEqual(row["판정"], "판단불가")
        self.assertIn("출력본 PDF가 없어", row["비고"][CHECK])
        self.assertIn("PDF로 저장", row["수정 제안"])

    def test_unreadable_print_copy_reason_is_passed_through(self):
        [row] = check_toc7(TOC, None, print_missing="출력본을 읽지 못함 (스캔본)")
        self.assertEqual(row["비고"][CHECK], "출력본을 읽지 못함 (스캔본)")

    def test_print_copy_of_another_manuscript_is_not_compared(self):
        [row] = check_toc7(TOC, {"학습 1": heading("1")}, module_code="LM1203020201_24v3", print_code="LM1203020299_24v1")
        self.assertEqual(row["판정"], "판단불가")
        self.assertIn("다른 원고의 출력본", row["비고"][CHECK])

    def test_each_outcome(self):
        headings = {
            "학습 1": heading("1"),                 # 같음 → O
            "1-1": heading("5"),                   # 다름 → X
            # '1-2'는 차례 쪽이 '?'(쪽 깨짐) → X, 출력본 조회 없이
            "학습 1 평가": heading("12", "추정"),   # 같지만 추정 → △
            # '참고 자료'는 출력본에서 못 찾음 → △
        }
        rows = by_key(check_toc7(TOC, headings, module_code="LM1203020201_24v3", print_code="LM1203020201_24v3"))
        self.assertEqual({k: r["체크"][CHECK] for k, r in rows.items()},
                         {"학습 1": "O", "1-1": "X", "1-2": "X", "학습 1 평가": "△", "참고 자료": "△"})
        self.assertEqual(rows["1-1"]["비고"][CHECK], "차례 「1-1. 현행 시스템 분석 3」, 출력본 5쪽")
        self.assertIn("차례 필드 갱신", rows["1-1"]["수정 제안"])
        self.assertEqual(rows["1-2"]["비고"][CHECK], "차례 「1-2. 요구사항 정의 ?」 (쪽수가 갱신되지 않음)")
        self.assertIn("추정", rows["학습 1 평가"]["비고"][CHECK])
        self.assertIn("시작 쪽을 찾지 못함", rows["참고 자료"]["비고"][CHECK])
        self.assertEqual(rows["학습 1"]["비고"], {})
        self.assertEqual(rows["학습 1"]["출력본"], "1")

    def test_toc_line_without_page_is_not_applicable(self):
        toc = {"학습": [{"no": 1, "text": "명", "page": None}], "내용": [], "줄": [], "꼬리": {}, "쪽 깨짐": []}
        [row] = check_toc7(toc, {"학습 1": heading("1")})
        self.assertEqual(row["체크"][CHECK], "-")
        self.assertEqual(row["판정"], "적합")

    def test_folio_could_not_be_read_is_undecided_with_physical_page(self):
        rows = by_key(check_toc7({**TOC, "쪽 깨짐": []}, {"학습 1": heading(None, None, index=7)}))
        self.assertEqual(rows["학습 1"]["체크"][CHECK], "△")
        self.assertIn("8번째 쪽", rows["학습 1"]["비고"][CHECK])


class EndToEndTests(unittest.TestCase):
    def test_fixture_print_copy_makes_every_toc_line_pass(self):
        result = run_review([MANUSCRIPT, PRINT_COPY])
        rows = [r for r in result.checklist if r["item_id"] == "F02-차례-⑦"]
        self.assertEqual(len(rows), 11)
        self.assertTrue(all(r["체크"][CHECK] == "O" for r in rows))
        self.assertEqual([s["검수결과"] for s in result.sheet if s["번호"] == "⑦"], ["적합"])
        self.assertEqual(result.diagnostics["counts"]["print_pages"], 45)
        self.assertNotIn("F02-차례-⑦", result.diagnostics["not_implemented"])

    def test_without_print_copy_sheet_says_undecided_and_warns(self):
        result = run_review([MANUSCRIPT])
        self.assertEqual([s["검수결과"] for s in result.sheet if s["번호"] == "⑦"], ["판단불가"])
        self.assertTrue(any("출력본 PDF가 없어" in w for w in result.diagnostics["warnings"]))


if __name__ == "__main__":
    unittest.main()
