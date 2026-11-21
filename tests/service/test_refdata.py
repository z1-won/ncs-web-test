"""운영 중에 기준정보 받아 오기 — NCS 요소·수행준거(ncs_fetch, /api/plan/subclasses/{duty}/fetch)와 법령명 조회(law_lookup).
외부 API는 부르지 않는다: ncs_api·law_api의 함수를 가짜로 바꾸고, 기준정보 폴더는 임시 폴더를 쓴다."""

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from ncs_core import law_catalog, law_lookup, ncs_catalog, ncs_fetch, refdata
from ncs_core.law_api import LawApiError, LawRecord
from ncs_core.ncs_api import ApiUnit, NcsApiError

DUTY = "01010101"          # NCS 목록에는 있지만 패키지의 요소·수행준거 표에는 없는 세분류
READY = "12030202"         # 패키지 표에 있는 세분류


def fake_ncs(units):
    """units: [(코드, 이름, {요소 번호: (요소명, [수행준거…])})] → ncs_api 함수 셋을 대신할 것."""
    def list_units(duty):
        return [ApiUnit(duty, code, name, 3, f"{name}이란 … 능력이다.") for code, name, _ in units]

    def elements(duty, number=None):
        return [{"code": code, "no": no, "name": body[0]} for code, _, parts in units if code[8:10] == number for no, body in parts.items()]

    def criteria(duty, number):
        return {no: [f"{no}.{i} {text}" for i, text in enumerate(body[1], 1)]
                for code, _, parts in units if code[8:10] == number for no, body in parts.items()}

    return patch.multiple("ncs_core.ncs_api", units=list_units, elements=elements, criteria=criteria)


V1 = [("0101010101_17v2", "개발전략수립", {1: ("현황 분석하기", ["자료를 수집할 수 있다.", "현황을 분석할 수 있다."]), 2: ("전략 세우기", ["전략을 세울 수 있다."])}),
      ("0101010102_17v2", "사업기획", {1: ("사업 발굴하기", ["사업을 발굴할 수 있다."])})]
V2 = [("0101010101_26v3", "개발전략수립", {1: ("현황 분석하기", ["자료를 수집할 수 있다.", "현황을 분석하고 정리할 수 있다."]), 2: ("전략 세우기", ["전략을 세울 수 있다."])}),
      ("0101010103_26v1", "사업평가", {1: ("성과 평가하기", ["성과를 평가할 수 있다."])})]


class RefdataCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        env = patch.dict(os.environ, {"NCS_API_KEY": "test-key", "LAW_API_OC": "test-oc"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("NCS_CATALOG_FILE", None)
        os.environ.pop("LAW_NAMES_FILE", None)
        refdata.set_data_dir(self.folder.name)
        self.addCleanup(self._reset)

    def _reset(self):
        refdata.set_data_dir(None)
        ncs_catalog.reload()
        law_catalog.reload()

    def table(self, name):
        return Path(self.folder.name).resolve() / name


class NcsFetchTests(RefdataCase):
    def test_no_folder_or_key_means_no_fetch(self):
        self.assertTrue(ncs_fetch.can_fetch())
        refdata.set_data_dir(None)
        self.assertFalse(ncs_fetch.can_fetch())
        refdata.set_data_dir(self.folder.name)
        with patch.dict(os.environ, {"NCS_API_KEY": ""}):
            self.assertFalse(ncs_fetch.can_fetch())

    def test_first_fetch_writes_overlay_and_catalog_sees_it(self):
        self.assertEqual(ncs_catalog.catalog().units_with_detail(DUTY), [])
        packaged = len(ncs_catalog.catalog().units_with_detail(READY))
        with fake_ncs(V1):
            done = ncs_fetch.refresh_duty(DUTY)
        self.assertTrue(done["처음"])
        self.assertEqual(done["변화"]["추가"], ["0101010101_17v2 개발전략수립", "0101010102_17v2 사업기획"])
        units = ncs_catalog.catalog().units_with_detail(DUTY)
        self.assertEqual([u["code"] for u in units], ["0101010101_17v2", "0101010102_17v2"])
        self.assertEqual(units[0]["elements"][0]["criteria"], ["1.1 자료를 수집할 수 있다.", "1.2 현황을 분석할 수 있다."])
        self.assertEqual(units[0]["fetched"], date.today().isoformat())
        # 패키지 표의 다른 세분류는 그대로이고, 패키지 표 파일은 건드리지 않는다
        self.assertEqual(len(ncs_catalog.catalog().units_with_detail(READY)), packaged)
        self.assertIsNone(ncs_catalog.catalog().units_with_detail(READY)[0]["fetched"])
        self.assertTrue(self.table("ncs_elements.tsv").is_file())

    def test_refresh_replaces_the_duty_and_reports_changes(self):
        with fake_ncs(V1):
            ncs_fetch.refresh_duty(DUTY)
        with fake_ncs(V2):
            done = ncs_fetch.refresh_duty(DUTY)
        self.assertFalse(done["처음"])
        self.assertEqual(done["변화"], {"추가": ["0101010103_26v1 사업평가"], "삭제": ["0101010102_17v2 사업기획"],
                                      "변경": ["0101010101_26v3 개발전략수립"]})
        self.assertEqual([u["code"] for u in ncs_catalog.catalog().units_with_detail(DUTY)], ["0101010101_26v3", "0101010103_26v1"])
        with fake_ncs(V2):
            self.assertEqual(ncs_fetch.refresh_duty(DUTY)["변화"], {"추가": [], "삭제": [], "변경": []})
        rows = [line for line in self.table("ncs_elements.tsv").read_text(encoding="utf-8").splitlines() if line.startswith(DUTY)]
        self.assertEqual(len(rows), 3)      # 요소 3개 — 예전 판의 행이 남지 않는다

    def test_overlay_wins_over_packaged_duty(self):
        with fake_ncs([("1203020201_26v4", "객실 예약 관리", {1: ("예약 받기", ["예약을 받을 수 있다."])})]):
            done = ncs_fetch.refresh_duty(READY)
        self.assertFalse(done["처음"])
        self.assertGreater(len(done["변화"]["삭제"]), 0)
        self.assertEqual([u["code"] for u in ncs_catalog.catalog().units_with_detail(READY)], ["1203020201_26v4"])

    def test_failure_writes_nothing(self):
        def broken(duty, number):
            raise NcsApiError("ncsKsaInfo 연결 실패")
        with fake_ncs(V1), patch("ncs_core.ncs_api.criteria", broken):
            with self.assertRaises(NcsApiError):
                ncs_fetch.refresh_duty(DUTY)
        self.assertFalse(self.table("ncs_elements.tsv").exists())
        self.assertEqual(ncs_catalog.catalog().units_with_detail(DUTY), [])
        with patch("ncs_core.ncs_api.units", lambda duty: []), self.assertRaisesRegex(NcsApiError, "능력단위가 없습니다"):
            ncs_fetch.fetch_duty(DUTY)


class PlanFetchWebTests(RefdataCase):
    def client(self, data_dir="use"):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.addCleanup(self.out.cleanup)
        return TestClient(create_app(out_dir=self.out.name, data_dir=self.folder.name if data_dir == "use" else None))

    def test_list_detail_fetch_refresh_and_draft(self):
        with self.client() as client:
            listed = client.get("/api/plan/subclasses").json()
            self.assertTrue(listed["can_fetch"])
            row = next(s for s in listed["subclasses"] if s["duty"] == DUTY)
            self.assertFalse(row["ready"])
            detail = client.get(f"/api/plan/subclasses/{DUTY}").json()
            self.assertEqual((detail["ready"], detail["units"], detail["fetched"]), (False, [], None))
            self.assertGreater(len(detail["listed"]), 0)
            self.assertEqual(client.post("/api/plan/draft", json={"duty": DUTY}).status_code, 400)   # 아직 받아 두지 않음
            with fake_ncs(V1):
                first = client.post(f"/api/plan/subclasses/{DUTY}/fetch")
            self.assertEqual(first.status_code, 200, first.text)
            body = first.json()
            self.assertTrue(body["ready"] and body["처음"])
            self.assertEqual([(u["code"], u["elements"], u["criteria"]) for u in body["units"]],
                             [("0101010101_17v2", 2, 3), ("0101010102_17v2", 1, 1)])
            self.assertEqual(body["fetched"], date.today().isoformat())
            # 받아 둔 세분류는 refresh 없이는 NCS를 다시 부르지 않는다
            with patch("ncs_core.ncs_api.units", side_effect=AssertionError("부르면 안 됨")):
                again = client.post(f"/api/plan/subclasses/{DUTY}/fetch").json()
            self.assertIsNone(again["변화"])
            with fake_ncs(V2):
                changed = client.post(f"/api/plan/subclasses/{DUTY}/fetch?refresh=true").json()
            self.assertEqual(changed["변화"]["삭제"], ["0101010102_17v2 사업기획"])
            self.assertTrue(next(s for s in client.get("/api/plan/subclasses").json()["subclasses"] if s["duty"] == DUTY)["ready"])
            draft = client.post("/api/plan/draft", json={"duty": DUTY})                             # 받아 온 것으로 초안이 만들어진다
            self.assertEqual(draft.status_code, 200, draft.text)
            self.assertEqual([r["번호"] for r in draft.json()["check"]], list("①②③④⑤⑥⑦⑧⑨⑩"))

    def test_errors_are_user_messages(self):
        with self.client() as client:
            self.assertEqual(client.get("/api/plan/subclasses/99999999").status_code, 404)
            self.assertEqual(client.post("/api/plan/subclasses/abc/fetch").status_code, 400)
            with patch("ncs_core.ncs_api.units", side_effect=NcsApiError("HTTP 500 ncsCompeUnitInfo: SERVICE ERROR")), \
                 self.assertLogs("ncs_web", level="WARNING"):
                failed = client.post(f"/api/plan/subclasses/{DUTY}/fetch")
            self.assertEqual(failed.status_code, 502)
            self.assertIn("받아 오지 못했습니다", failed.json()["error"])
            self.assertNotIn("SERVICE ERROR", failed.json()["error"])      # API의 오류 글은 로그에만
        with self.client(data_dir=None) as client:                        # 기준정보 폴더가 없는 서버
            self.assertFalse(client.get("/api/plan/subclasses").json()["can_fetch"])
            refused = client.post(f"/api/plan/subclasses/{DUTY}/fetch")
            self.assertEqual(refused.status_code, 400)
            self.assertIn("관리자", refused.json()["error"])
            ready = client.post(f"/api/plan/subclasses/{READY}/fetch")     # 받아 둔 세분류는 그대로 돌려준다
            self.assertEqual((ready.status_code, ready.json()["ready"]), (200, True))


def record(name, law_id="000001", current="현행", revision="일부개정", effective="20260101", abbreviation=""):
    return LawRecord(name, law_id, "1", "20251201", effective, revision, current, "법률", abbreviation)


class LawLookupTests(RefdataCase):
    def test_looks_up_only_unknown_names_and_appends(self):
        calls = []

        def search(name, display=20):
            calls.append(name)
            return [record("산업안전보건법")] if name == "산업안전보건법" else []

        with patch("ncs_core.law_lookup.search", search), patch("ncs_core.law_lookup.history", lambda name, display=50: []):
            report = law_lookup.ensure(["근로기준법", "산업안전보건법", "산업안전보건법", "없는법"])
        self.assertEqual(report["조회"], ["산업안전보건법", "없는법"])     # 패키지 표에 있는 근로기준법은 조회하지 않는다
        self.assertNotIn("근로기준법", calls)
        catalog = law_catalog.law_catalog()
        self.assertEqual(catalog.lookup("산업안전보건법").status, "현행")
        self.assertEqual(catalog.lookup("없는법").status, "미검색")
        self.assertEqual(catalog.lookup("근로기준법").status, "현행")
        with patch("ncs_core.law_lookup.search", side_effect=AssertionError("부르면 안 됨")):
            self.assertEqual(law_lookup.ensure(["산업안전보건법", "없는법"])["조회"], [])            # 방금 조회한 것은 다시 묻지 않는다

    def test_stale_entries_are_looked_up_again_and_newer_wins(self):
        old = (date.today() - timedelta(days=law_lookup.MAX_AGE_DAYS + 1)).isoformat()
        self.table("law_names.tsv").write_text(f"옛이름법\t옛이름법\t000009\t20200101\t일부개정\t현행\t옛이름법\t{old}\n", encoding="utf-8")
        law_catalog.reload()
        past = LawRecord("옛이름법", "000009", "2", "20240101", "20240101", "일부개정", "연혁", "법률", "")
        renamed = record("새이름법", law_id="000009")
        # judge는 현행 목록을 두 번 찾는다: 이름 그대로(없음) → 연혁의 법령ID로 지금 이름(새이름법)
        with patch("ncs_core.law_lookup.search", side_effect=[[], [renamed]]), \
             patch("ncs_core.law_lookup.history", lambda name, display=50: [past]):
            report = law_lookup.ensure(["옛이름법"])
        self.assertEqual(report["조회"], ["옛이름법"])
        entry = law_catalog.law_catalog().lookup("옛이름법")
        self.assertEqual((entry.status, entry.current_name, entry.checked), ("명칭변경", "새이름법", date.today().isoformat()))

    def test_failures_stop_early_and_nothing_without_key_or_folder(self):
        with patch("ncs_core.law_lookup.search", side_effect=LawApiError("연결 실패: timed out")) as search:
            report = law_lookup.ensure([f"가나다{i}법" for i in range(6)])
        self.assertEqual((report["조회"], len(report["실패"]), search.call_count), ([], 6, law_lookup.MAX_FAILURES))
        self.assertIn("연결 실패", report["오류"])
        self.assertFalse(self.table("law_names.tsv").exists())
        with patch("ncs_core.law_lookup.search", lambda name, display=20: [record(name)]):
            many = law_lookup.ensure([f"라마바{i}법" for i in range(law_lookup.MAX_LOOKUPS + 4)])
        self.assertEqual((len(many["조회"]), many["남김"]), (law_lookup.MAX_LOOKUPS, 4))
        with patch.dict(os.environ, {"LAW_API_OC": ""}):
            self.assertIsNone(law_lookup.ensure(["산업안전보건법"]))
        refdata.set_data_dir(None)
        self.assertIsNone(law_lookup.ensure(["산업안전보건법"]))

    def test_plan_check_looks_up_law_names_in_the_plan(self):
        """개발계획서 점검: 계획서에 적힌 법령명 가운데 표에 없는 것을 조회해 ⑩이 판정한다(조회 전에는 판단불가)."""
        from ncs_plan import run_review

        plan = Path(__file__).resolve().parents[1] / "fixtures" / "개발계획서_LM1203020201_24v3.hwpx"
        seen = []

        def search(name, display=20):
            seen.append(name)
            return [record(name)]

        with patch("ncs_core.law_lookup.search", search):
            result = run_review([plan])
        looked = result.diagnostics["법령 조회"]
        self.assertEqual(looked["새로 조회"], seen)
        self.assertEqual(looked["실패"], [])
        for name in seen:
            self.assertEqual(law_catalog.law_catalog().lookup(name).status, "현행")


if __name__ == "__main__":
    unittest.main()
