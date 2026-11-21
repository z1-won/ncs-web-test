"""배치 대조의 오차율 셈(scripts/batch/batch_compare.error_rates) — 기대 행과 조작하지 않은 항목을 어떻게 세는지."""

import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "batch"))

from batch_compare import error_rates  # noqa: E402
from ncs_core import FAIL, PASS, UNDECIDED  # noqa: E402


def row(doc, comp, no, expected, actual, outcome):
    return {"문서": doc, "구성요소": comp, "번호": no, "기대": expected, "실제": actual, "결과": outcome}


class ErrorRateTests(unittest.TestCase):
    def setUp(self):
        self.matched = [row("a", "차례", "①", FAIL, FAIL, "일치"), row("a", "차례", "②", FAIL, PASS, "미탐"),
                        row("b", "차례", "①", PASS, FAIL, "불일치(부적합)"), row("b", "차례", "②", PASS, UNDECIDED, "불일치(판단불가)"),
                        row("b", "차례", "③", UNDECIDED, UNDECIDED, "일치")]
        self.verdicts = {"a": {("차례", "①"): FAIL, ("차례", "②"): PASS, ("차례", "③"): PASS, ("개요", "①"): FAIL, ("개요", "②"): UNDECIDED},
                         "b": {("차례", "①"): FAIL, ("차례", "②"): UNDECIDED, ("차례", "③"): UNDECIDED, ("개요", "①"): PASS, ("개요", "②"): PASS}}
        self.expected = defaultdict(set, {"a": {("차례", "①"), ("차례", "②")}, "b": {("차례", "①"), ("차례", "②"), ("차례", "③")}})
        self.base = {("차례", "③"): PASS, ("개요", "①"): PASS, ("개요", "②"): UNDECIDED}

    def test_with_baseline(self):
        rows = {r["구성요소"]: r for r in error_rates(self.matched, self.verdicts, self.expected, self.base, ["차례", "개요"])}
        # 차례: 기대 부적합 2(미탐 1) + 기대 적합 1(오탐 1, 판단불가 1은 보류) + 조작 안 한 ③(a만, 원본과 같음)
        self.assertEqual((rows["차례"]["정답이 있는 판정"], rows["차례"]["미탐"], rows["차례"]["오탐"], rows["차례"]["보류(판단불가)"]), (4, 1, 1, 1))
        self.assertEqual((rows["차례"]["오차율"], rows["차례"]["미탐율"]), ("50.00%", "50.00%"))
        # 개요: ①은 원본 적합 → a 부적합은 오탐, b 적합은 맞음. ②는 원본도 판단불가라 제외
        self.assertEqual((rows["개요"]["정답이 있는 판정"], rows["개요"]["오탐"], rows["개요"]["제외(원본도 판단불가·미검사)"]), (2, 1, 2))
        self.assertEqual((rows["전체"]["정답이 있는 판정"], rows["전체"]["틀림"], rows["전체"]["오차율"]), (6, 3, "50.00%"))

    def test_without_baseline_counts_expected_rows_only(self):
        rows = {r["구성요소"]: r for r in error_rates(self.matched, self.verdicts, self.expected, None, ["차례", "개요"])}
        self.assertEqual((rows["전체"]["정답이 있는 판정"], rows["전체"]["틀림"]), (3, 2))
        self.assertEqual(rows["개요"]["오차율"], "-")


if __name__ == "__main__":
    unittest.main()
