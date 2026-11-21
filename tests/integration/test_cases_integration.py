"""NCS_TEST_DATABASE_URL을 지정하면 세분류 건(/api/cases)을 실제 PostgreSQL로 검사한다: 건 만들기, 집필자 붙이기, 보이는 범위, 사건과 상태."""

import os
import unittest

import psycopg
from fastapi.testclient import TestClient

from ncs_service import accounts, cases, flow
from ncs_service.postgres import migrate, set_stage
from ncs_web.server import create_app

DSN = os.getenv("NCS_TEST_DATABASE_URL")
SUBCLASS, YEAR = "99999901", 2099
A, B = "LM9999990101_26v1", "LM9999990102_26v1"
PASSWORD = "시험용 비밀번호 1234"
EDITOR, AUTHOR, OTHER, REVIEWER = "case-test-editor", "case-test-author", "case-test-other", "case-test-reviewer"


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class CaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.clean()
        self.addCleanup(self.clean)
        self.ids = {}
        for login, name, role in [(EDITOR, "김에디터", "editor"), (AUTHOR, "이집필", "author"), (OTHER, "박집필", "author"),
                                  (REVIEWER, "최검토", "reviewer")]:
            self.ids[login] = accounts.create_account(DSN, login=login, name=name, role=role, password=PASSWORD)["id"]
        self.app = create_app(database_url=DSN)

    def clean(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM cases WHERE subclass = %s", (SUBCLASS,))
            connection.execute("DELETE FROM accounts WHERE login LIKE 'case-test-%'")
            connection.execute("DELETE FROM manuscript_stages WHERE module_code = ANY(%s)", ([A, B],))
            connection.execute("DELETE FROM manuscript_stage_history WHERE module_code = ANY(%s)", ([A, B],))

    def client(self, login: str) -> TestClient:
        client = TestClient(self.app)
        self.assertEqual(client.post("/api/login", json={"login": login, "password": PASSWORD}).status_code, 200)
        return client

    def make(self, client, **over) -> dict:
        body = {"subclass": SUBCLASS, "year": YEAR, "improvement": "기존개선", "name": "시험 세분류",
                "volumes": [{"module_code": A, "title": "첫째 권"}, {"module_code": B, "title": "둘째 권"}], **over}
        response = client.post("/api/cases", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_create_assign_and_see_only_own_volumes(self):
        editor, author, other = self.client(EDITOR), self.client(AUTHOR), self.client(OTHER)
        body = {"subclass": SUBCLASS, "year": YEAR, "improvement": "기존개선", "volumes": [{"module_code": A}]}
        self.assertEqual(author.post("/api/cases", json=body).status_code, 403)                    # 집필진은 건을 만들지 못한다
        self.assertEqual(author.get("/api/cases/options").status_code, 403)
        options = editor.get("/api/cases/options").json()
        self.assertEqual(options["improvements"], list(flow.IMPROVEMENTS))
        self.assertIn(self.ids[AUTHOR], [a["id"] for a in options["authors"]])
        self.assertNotIn(self.ids[EDITOR], [a["id"] for a in options["authors"]])

        case = self.make(editor)
        self.assertEqual([v["module_code"] for v in case["volumes"]], [A, B])
        self.assertEqual((case["progress"]["done"], case["progress"]["total"], case["can_manage"]), (0, 2 * len(flow.VOLUME_STAGES), True))
        self.assertEqual(editor.post("/api/cases", json={"subclass": SUBCLASS, "year": YEAR, "improvement": "기존개선",
                                                         "volumes": [{"module_code": A}]}).status_code, 400)       # 같은 세분류·연도
        first = case["volumes"][0]["id"]
        url = f"/api/cases/{case['id']}"
        self.assertEqual(author.get(url).status_code, 404)                                          # 담당이 아니면 건이 있는지도 모른다
        self.assertEqual(author.get("/api/cases").json()["cases"], [])

        self.assertEqual(editor.post(f"{url}/volumes/{first}/author", json={"author_id": self.ids[EDITOR]}).status_code, 400)   # 집필진 계정만
        assigned = editor.post(f"{url}/volumes/{first}/author", json={"author_id": self.ids[AUTHOR]})
        self.assertEqual(assigned.json()["volumes"][0]["author"]["login"], AUTHOR)
        mine = author.get(url).json()
        self.assertEqual([v["module_code"] for v in mine["volumes"]], [A])
        self.assertFalse(mine["can_manage"])
        self.assertNotIn(B, [e["module_code"] for e in mine["events"]])                             # 남의 권의 사건은 오지 않는다
        self.assertEqual(len(author.get("/api/cases").json()["cases"]), 1)
        self.assertEqual(other.get(url).status_code, 404)
        self.assertEqual(self.client(REVIEWER).get("/api/cases").json()["cases"], [])
        self.assertEqual(author.post(f"{url}/volumes/{first}/author", json={"author_id": None}).status_code, 403)
        actions = [e["action"] for e in editor.get(url).json()["events"]]
        self.assertEqual(actions, [flow.AUTHOR_SET, flow.VOLUME_ADDED, flow.VOLUME_ADDED, flow.CREATED])

    def test_volume_must_belong_to_the_subclass(self):
        editor = self.client(EDITOR)
        bad = editor.post("/api/cases", json={"subclass": SUBCLASS, "year": YEAR, "improvement": "기존개선",
                                              "volumes": [{"module_code": "LM1203020201_24v3"}]})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("세분류", bad.json()["error"])
        self.assertEqual(editor.get("/api/cases").json()["cases"], [])                              # 반만 만들어진 건이 남지 않는다
        case = self.make(editor, volumes=[{"module_code": A}])
        self.assertEqual(editor.post(f"/api/cases/{case['id']}/volumes", json={"module_code": A}).status_code, 400)
        added = editor.post(f"/api/cases/{case['id']}/volumes", json={"module_code": B, "title": "둘째 권"})
        self.assertEqual(len(added.json()["volumes"]), 2)

    def test_events_drive_the_state(self):
        editor, author, other = self.client(EDITOR), self.client(AUTHOR), self.client(OTHER)
        case = self.make(editor)
        url, first, second = f"/api/cases/{case['id']}", case["volumes"][0]["id"], case["volumes"][1]["id"]
        editor.post(f"{url}/volumes/{first}/author", json={"author_id": self.ids[AUTHOR]})
        editor.post(f"{url}/volumes/{second}/author", json={"author_id": self.ids[OTHER]})

        def act(client, stage, action, volume=first, note=""):
            return client.post(f"{url}/events", json={"stage": stage, "action": action, "volume_id": volume, "note": note})

        self.assertEqual(act(other, "revision", "submit").status_code, 403)                         # 남의 권
        self.assertEqual(act(author, "revision", "request").status_code, 403)                       # 확인은 집필진이 못 한다
        self.assertEqual(act(editor, "revision", "request").status_code, 409)                       # 아직 제출 전
        self.assertEqual(act(author, "revision", "submit").status_code, 200)
        asked = act(editor, "revision", "request", note="표 3을 다시 봐 주세요").json()
        self.assertEqual(asked["volumes"][0]["stages"]["revision"]["state"], flow.REQUESTED)
        self.assertEqual(asked["volumes"][1]["stages"]["revision"]["state"], flow.WAITING)
        act(author, "revision", "submit")
        done = act(editor, "revision", "done").json()
        self.assertEqual((done["volumes"][0]["stages"]["revision"]["state"], done["volumes"][0]["done"], done["progress"]["done"]),
                         (flow.DONE, 1, 1))
        self.assertEqual(act(editor, "revision", "done").status_code, 409)
        self.assertEqual(act(editor, "volume", "done").status_code, 409)                            # 건너뛴 완료는 사유가 있어야
        proxy = act(editor, "volume", "done", note="직능연이 전화로 확인").json()
        self.assertTrue(proxy["events"][0]["proxy"])                                                # 직능연의 확인을 에디터가 대신 적음
        self.assertEqual(act(editor, "plan", "done", note="x").status_code, 409)                    # 건 단위 단계에 권을 붙이면 안 된다
        plan = act(editor, "plan", "done", volume=None, note="계획서는 종이로 확정").json()
        self.assertEqual(plan["case_stages"]["plan"]["state"], flow.DONE)
        self.assertEqual(act(editor, "nope", "done").status_code, 409)

    def test_progress_marks_are_adopted_and_mirrored(self):
        set_stage(DSN, A, 2, done=True, by="옛 표시(old)", note="초고본 확인")                      # 건에 넣기 전의 완료 표시
        editor = self.client(EDITOR)
        case = self.make(editor)
        url, first = f"/api/cases/{case['id']}", case["volumes"][0]
        self.assertEqual(first["stages"]["draft_edit"]["state"], flow.DONE)
        self.assertEqual(first["stages"]["draft_edit"]["by"], "옛 표시(old)")
        marked = editor.post(f"/api/manuscripts/{A}/stages/7", json={"done": True, "note": "서류 받음"})   # 원고 진행 현황에서 표시
        self.assertEqual(marked.status_code, 200, marked.text)
        now = editor.get(url).json()["volumes"][0]["stages"]
        self.assertEqual((now["volume"]["state"], now["rights"]["state"]), (flow.DONE, flow.DONE))
        self.assertIn(cases.LEGACY_NOTE, now["rights"]["note"])
        editor.post(f"/api/manuscripts/{A}/stages/7", json={"done": False})
        again = editor.get(url).json()
        self.assertEqual(again["volumes"][0]["stages"]["rights"]["state"], flow.WAITING)            # 되돌리면 완료하기 전의 상태로
        self.assertEqual(again["volumes"][1]["stages"]["rights"]["state"], flow.WAITING)


if __name__ == "__main__":
    unittest.main()
