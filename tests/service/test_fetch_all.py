"""NCS 요소·수행준거 미리 받기(scripts/data/fetch_all_ncs.py) — 이미 있는 세분류는 건너뛰고, 한도에서 멈추고, 실패한 세분류는 쓰지 않는다. NCS는 부르지 않는다."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ncs_core import ncs_catalog, ncs_fetch, refdata
from ncs_core.ncs_api import NcsApiError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fetch_all_ncs", ROOT / "scripts" / "data" / "fetch_all_ncs.py")
fetch_all = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_all)


def fake_units(duty: str) -> list[dict]:
    code = f"{duty}01_26v1"
    return [{"duty": duty, "code": code, "name": "시험 능력단위", "level": 3, "definition": "시험 능력단위란 시험하는 능력이다.",
             "elements": [{"code": f"{code}.1", "no": 1, "name": "시험하기", "criteria": ["1.1 시험할 수 있다."]}]}]


class FetchAllTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = mock.patch.dict(os.environ, {"NCS_API_KEY": "test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("NCS_CATALOG_FILE", None)          # 골든 테스트가 목록을 꺼 둔 채 먼저 돌았을 수 있다
        refdata.set_data_dir(self.temp.name)
        ncs_catalog.reload()
        self.addCleanup(lambda: (refdata.set_data_dir(None), ncs_catalog.reload()))
        self.lines = []

    def run_all(self, only, **options):
        return fetch_all.run(only, out=self.lines.append, **options)

    def test_skips_what_is_already_there_and_writes_the_rest(self):
        catalog = ncs_catalog.catalog()
        wanted = sorted(duty for duty in catalog.subclasses if duty.startswith("1203"))
        have = [duty for duty in wanted if catalog.units_with_detail(duty)]
        self.assertTrue(have and len(have) < len(wanted))             # 패키지 표에 일부만 들어 있는 소분류 묶음
        with mock.patch.object(ncs_fetch, "fetch_duty", side_effect=fake_units) as fetch:
            result = self.run_all(["1203"], budget=100000)
        self.assertEqual(sorted(result["받음"]), [duty for duty in wanted if duty not in have])
        self.assertEqual((result["남음"], result["실패"], result["멈춘 까닭"]), (0, [], "끝까지 돌았음"))
        self.assertEqual(fetch.call_count, len(wanted) - len(have))
        self.assertTrue(all(ncs_catalog.catalog().units_with_detail(duty) for duty in wanted))
        with mock.patch.object(ncs_fetch, "fetch_duty", side_effect=fake_units) as again:      # 다시 돌리면 받을 것이 없다
            self.assertEqual(self.run_all(["1203"])["멈춘 까닭"], "받을 세분류가 없음")
        again.assert_not_called()

    def test_stops_at_the_budget_and_resumes(self):
        todo, _ = fetch_all.plan(ncs_catalog.catalog(), ["0101"], False)
        self.assertGreater(len(todo), 2)
        budget = todo[0][2] + todo[1][2]
        with mock.patch.object(ncs_fetch, "fetch_duty", side_effect=fake_units):
            first = self.run_all(["0101"], budget=budget)
            self.assertEqual((first["받음"], first["쓴 호출"]), ([todo[0][0], todo[1][0]], budget))
            self.assertIn("닿음", first["멈춘 까닭"])
            second = self.run_all(["0101"], budget=10**6)
        self.assertEqual(second["받음"], [duty for duty, _, _ in todo[2:]])

    def test_failed_subclass_is_not_written_and_quota_stops(self):
        todo, _ = fetch_all.plan(ncs_catalog.catalog(), ["0101"], False)

        def flaky(duty):
            if duty == todo[0][0]:
                raise NcsApiError("ncsKsaInfo 연결 실패: timed out")
            if duty == todo[2][0]:
                raise NcsApiError("ncsCompeUnitInfo: LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR — 한도 초과")
            return fake_units(duty)

        with mock.patch.object(ncs_fetch, "fetch_duty", side_effect=flaky):
            result = self.run_all(["0101"], budget=10**6)
        self.assertEqual(([duty for duty, _ in result["실패"]], result["받음"]), ([todo[0][0]], [todo[1][0]]))
        self.assertIn("한도 초과", result["멈춘 까닭"])
        self.assertFalse(ncs_catalog.catalog().units_with_detail(todo[0][0]))

    def test_dry_run_only_counts(self):
        with mock.patch.object(ncs_fetch, "fetch_duty") as fetch:
            result = self.run_all(["20"], dry_run=True)
        fetch.assert_not_called()
        self.assertGreater(result["남은 호출"], result["남음"])


if __name__ == "__main__":
    unittest.main()
