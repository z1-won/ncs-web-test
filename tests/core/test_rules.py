"""규칙 실행(ncs_core.rules): 규칙 하나가 예외로 끝나도 나머지 규칙의 결과는 남고, 그 항목은 판단불가로 확인서에 접힌다."""

import logging
import unittest

from ncs_core import Rule, run_rules
from ncs_core.rules import RULE_ERROR_CHECK
from ncs_core.sheet import SheetItem, build_sheet
from ncs_core.text import flatten


def good_row(item_id):
    return {"item_id": item_id, "region_path": "section1", "원고": "문구", "체크": {"형식": "O"}, "판정": "적합", "비고": {}, "수정 제안": None}


def broken(_context):
    raise KeyError("/srv/secret/path")


class RuleIsolationTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)   # 실패 규칙의 traceback 로그는 이 테스트에서 보지 않는다
        self.addCleanup(logging.disable, logging.NOTSET)

    def test_failed_rule_becomes_undecided_and_others_survive(self):
        rules = (
            Rule("first", "X-①", lambda c: [good_row("X-①")]),
            Rule("second", "X-②", broken),
            Rule("third", "X-③", lambda c: [good_row("X-③")]),
        )
        rows = run_rules(None, rules)
        self.assertEqual([r["item_id"] for r in rows], ["X-①", "X-②", "X-③"])
        failed = rows[1]
        self.assertEqual(failed["판정"], "판단불가")
        self.assertEqual(failed["체크"], {RULE_ERROR_CHECK: "△"})
        note = failed["비고"][RULE_ERROR_CHECK]
        self.assertIn("second", note)
        self.assertIn("KeyError", note)
        self.assertNotIn("secret", note, "예외 메시지(서버 경로가 들어 있을 수 있음)는 비고에 싣지 않는다")
        # 확인서: 실패한 항목은 미검사·적합이 아니라 판단불가, 지적사항에도 나온다
        items = [SheetItem(n, f"항목 {n}", (f"X-{n}",)) for n in "①②③"]
        sheet = build_sheet(rows, items, "시험")
        self.assertEqual([r["검수결과"] for r in sheet], ["적합", "판단불가", "적합"])
        self.assertEqual([f["item_id"] for f in flatten(rows)], ["X-②"])

    def test_failure_item_ids_cover_every_sheet_item_of_a_shared_rule(self):
        """item_prefix가 여러 항목의 공통 머리인 규칙은 failure_item_ids의 항목마다 한 행을 남긴다."""
        rows = run_rules(None, (Rule("shared", "X-", broken, failure_item_ids=("X-①", "X-②")),))
        self.assertEqual([r["item_id"] for r in rows], ["X-①", "X-②"])

    def test_rule_without_rows_is_undecided_not_unimplemented(self):
        """규칙이 행을 내지 않으면 판단불가 — '미검사(규칙 미구현)'는 규칙이 없는 항목에만 쓴다."""
        from ncs_core.rules import NO_TARGET_CHECK

        rows = run_rules(None, (Rule("empty", "X-①", lambda c: []),))
        self.assertEqual([(r["item_id"], r["판정"], r["체크"]) for r in rows], [("X-①", "판단불가", {NO_TARGET_CHECK: "△"})])
        items = [SheetItem("①", "항목 ①", ("X-①",)), SheetItem("②", "규칙 없는 항목", ())]
        self.assertEqual([r["검수결과"] for r in build_sheet(rows, items, "시험")], ["판단불가", "미검사"])
        # 규칙을 돌리지 않으면(rules=()) 여전히 미검사다
        self.assertEqual([r["검수결과"] for r in build_sheet(run_rules(None, ()), items, "시험")], ["미검사", "미검사"])

    def test_wrong_item_id_is_still_a_programming_error(self):
        with self.assertRaises(ValueError):
            run_rules(None, (Rule("first", "X-①", lambda c: [good_row("Y-①")]),))


class WorstTests(unittest.TestCase):
    def test_one_precedence_for_marks_and_verdicts(self):
        """판정 종합은 text.worst 하나 — 체크 표시와 검수결과 어느 쪽이든 부적합 > 판단불가 > 적합."""
        from ncs_core import verdict, worst
        from ncs_core.reporting import overall_verdict

        self.assertEqual(worst(["O", "△", "X"]), "부적합")
        self.assertEqual(worst(["O", "△", "-"]), "판단불가")
        self.assertEqual(worst(["O", "-"]), "적합")
        self.assertEqual(worst([]), "적합")
        self.assertEqual(worst(["적합", "판단불가", "부적합"]), "부적합")
        self.assertEqual(verdict({"a": "O", "b": "△"}), "판단불가")
        self.assertEqual(overall_verdict(["적합", "판단불가"]), "판단불가")


if __name__ == "__main__":
    unittest.main()
