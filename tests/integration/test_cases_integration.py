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
        self.assertEqual(author.get("/api/cases").json()["cases"], [])      # 시험 계정은 다른 건의 담당이 아니다

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
        self.assertEqual([c for c in editor.get("/api/cases").json()["cases"] if c["subclass"] == SUBCLASS], [])   # 반만 만들어진 건이 남지 않는다
        case = self.make(editor, volumes=[{"module_code": A}])
        self.assertEqual(editor.post(f"/api/cases/{case['id']}/volumes", json={"module_code": A}).status_code, 400)
        added = editor.post(f"/api/cases/{case['id']}/volumes", json={"module_code": B, "title": "둘째 권"})
        self.assertEqual(len(added.json()["volumes"]), 2)

    def flow_setup(self):
        editor, author, other = self.client(EDITOR), self.client(AUTHOR), self.client(OTHER)
        case = self.make(editor)
        url, first, second = f"/api/cases/{case['id']}", case["volumes"][0]["id"], case["volumes"][1]["id"]
        editor.post(f"{url}/volumes/{first}/author", json={"author_id": self.ids[AUTHOR]})
        editor.post(f"{url}/volumes/{second}/author", json={"author_id": self.ids[OTHER]})
        return editor, author, other, url, first, second

    def test_events_drive_the_state(self):
        editor, author, other, url, first, second = self.flow_setup()

        def act(client, stage, action, volume=first, note=""):
            return client.post(f"{url}/events", json={"stage": stage, "action": action, "volume_id": volume, "note": note})

        self.assertEqual(act(other, "rights", "submit").status_code, 403)                           # 남의 권
        self.assertEqual(act(author, "rights", "request").status_code, 403)                         # 확인은 집필진이 못 한다
        self.assertEqual(act(editor, "rights", "request").status_code, 409)                         # 아직 제출 전
        self.assertEqual(act(author, "draft_edit", "submit").status_code, 409)                      # 원고를 올리는 단계는 파일로 제출
        self.assertEqual(act(author, "rights", "submit").status_code, 200)
        asked = act(editor, "rights", "request", note="양도 동의서가 빠졌습니다").json()
        self.assertEqual(asked["volumes"][0]["stages"]["rights"]["state"], flow.REQUESTED)
        self.assertEqual(asked["volumes"][1]["stages"]["rights"]["state"], flow.WAITING)
        act(author, "rights", "submit")
        done = act(editor, "rights", "done").json()
        self.assertEqual((done["volumes"][0]["stages"]["rights"]["state"], done["volumes"][0]["done"], done["progress"]["done"]),
                         (flow.DONE, 1, 1))
        self.assertEqual(act(editor, "rights", "done").status_code, 409)
        self.assertEqual(act(editor, "volume", "done").status_code, 409)                            # 건너뛴 완료는 사유가 있어야
        proxy = act(editor, "volume", "done", note="직능연이 전화로 확인").json()
        self.assertTrue(proxy["events"][0]["proxy"])                                                # 직능연의 확인을 에디터가 대신 적음
        self.assertEqual(act(editor, "plan", "done", note="x").status_code, 409)                    # 건 단위 단계에 권을 붙이면 안 된다
        self.assertEqual(act(other, "plan", "submit", volume=None).status_code, 200)                # 건 단위 단계: 담당 권이 있는 집필진
        plan = act(editor, "plan", "done", volume=None).json()
        self.assertEqual(plan["case_stages"]["plan"]["state"], flow.DONE)
        self.assertEqual(act(editor, "nope", "done").status_code, 409)

    def test_manuscript_round_trip_from_submission_to_next_stage(self):
        """집필진이 초고본을 올림 → 에디터 할 일 → 검수가 판본에 붙음 → 보완 요청 → 다시 제출 → 완료 → 다음 단계로."""
        editor, author, other, url, first, second = self.flow_setup()
        hwpx = ("초고본.hwpx", b"PK\x03\x04 first draft", "application/octet-stream")

        def todo(client):
            return [(t["title"], t["stage"], t["state"], t["proxy"]) for t in client.get("/api/cases/todo").json() if url.endswith(t["case_id"])]

        def submit(client, content, volume=first, stage="draft_edit", name="초고본.hwpx"):
            return client.post(f"{url}/volumes/{volume}/versions", data={"stage": stage, "note": ""}, files={"file": (name, content)})

        self.assertEqual(todo(author), [("건 전체", "plan", flow.WAITING, False)])                   # 처음은 건 단위의 개발계획서
        self.assertEqual(todo(editor), [])                                                          # 집필진 차례는 에디터 할 일에 없다
        author.post(f"{url}/events", json={"stage": "plan", "action": "submit"})
        self.assertEqual(todo(editor), [("건 전체", "plan", flow.SUBMITTED, True)])                  # 직능연 차례: 에디터가 대신 적을 수 있음
        editor.post(f"{url}/events", json={"stage": "plan", "action": "done"})
        self.assertEqual(todo(author), [("첫째 권", "draft_edit", flow.WAITING, False)])

        self.assertEqual(submit(author, b"x", name="초고본.pdf").status_code, 400)
        self.assertEqual(submit(other, hwpx[1]).status_code, 403)
        self.assertEqual(submit(author, hwpx[1], stage="rights").status_code, 409)                  # 원고를 올리는 단계가 아님
        sent = submit(author, hwpx[1])
        self.assertEqual(sent.status_code, 200, sent.text)
        volume = sent.json()["volumes"][0]
        self.assertEqual((volume["current"]["key"], volume["current"]["state"], volume["current"]["turn"]), ("draft_edit", flow.SUBMITTED, ["에디터"]))
        version = volume["versions"][0]
        self.assertEqual((version["number"], version["filename"], version["review"]), (1, "초고본.hwpx", None))
        self.assertEqual(submit(author, hwpx[1]).status_code, 400)                                  # 같은 파일을 다시 낼 수 없다
        self.assertEqual(todo(author), [])
        self.assertEqual(todo(editor), [("첫째 권", "draft_edit", flow.SUBMITTED, False)])

        got = author.get(f"{url}/versions/{version['id']}/file")
        self.assertEqual((got.status_code, got.content), (200, hwpx[1]))
        self.assertEqual(other.get(f"{url}/versions/{version['id']}/file").status_code, 404)
        self.assertEqual(author.post(f"{url}/versions/{version['id']}/upload").status_code, 403)    # 검수는 에디터가 돌린다
        ready = editor.post(f"{url}/versions/{version['id']}/upload").json()
        self.assertIn("toc", ready["checks"])
        self.assertNotIn("position", ready["checks"])                                               # 개발계획서가 필요한 검수는 빠진다
        self.assertEqual(ready["module_code"], A)
        editor.delete(f"/api/uploads/{ready['upload']}")

        request = {"stage": "draft_edit", "action": "request", "volume_id": first}
        self.assertEqual(editor.post(f"{url}/events", json=request).status_code, 409)               # 검수 기록 없이 보완 요청하려면 사유
        run_id = self.fake_review(version["id"], ready["group"])
        with_review = editor.get(url).json()["volumes"][0]["versions"][0]["review"]
        self.assertEqual((with_review["group"], with_review["verdict"], with_review["checks"]), (ready["group"], "부적합", 1))
        asked = editor.post(f"{url}/events", json={**request, "note": "차례 ③을 고쳐 주세요"})
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertEqual(todo(author), [("첫째 권", "draft_edit", flow.REQUESTED, False)])
        self.assertEqual(author.get("/api/cases/todo").json()[0]["note"], "차례 ③을 고쳐 주세요")

        again = submit(author, b"PK\x03\x04 second draft")
        self.assertEqual([v["number"] for v in again.json()["volumes"][0]["versions"]], [2, 1])
        finish = {"stage": "draft_edit", "action": "done", "volume_id": first}
        self.assertEqual(editor.post(f"{url}/events", json=finish).status_code, 409)                # 새 판본은 아직 검수 전
        done = editor.post(f"{url}/events", json={**finish, "note": "고친 곳만 눈으로 확인"}).json()
        self.assertEqual(done["volumes"][0]["current"]["key"], "review1")                           # 다음 단계로 넘어간다
        self.assertEqual(done["volumes"][1]["current"]["key"], "draft_edit")
        self.assertEqual(done["volumes"][0]["reopen"], ["draft_edit"])
        with psycopg.connect(DSN) as connection:
            evidence = connection.execute("SELECT evidence FROM case_events WHERE action = 'request' AND volume_id = %s", (first,)).fetchone()[0]
            connection.execute("DELETE FROM review_runs WHERE id = %s", (run_id,))
        self.assertEqual((evidence["version"], evidence["review_group"]), (version["id"], ready["group"]))

    def fake_review(self, version_id: str, group_id: str) -> str:
        """검수 실행 한 건을 직접 넣고 판본에 붙인다(엔진을 돌리지 않고 연결만 본다)."""
        from uuid import uuid4

        run_id = str(uuid4())
        with psycopg.connect(DSN) as connection:
            connection.execute("INSERT INTO review_runs (id, check_name, module_code, verdict, group_id) VALUES (%s, 'toc', %s, '부적합', %s)",
                               (run_id, A, group_id))
        cases.tag_review_version(DSN, run_id, version_id)
        return run_id

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
