"""검토의견서 반영 여부 검토 웹 경로(/api/opinion) — 의견서 둘·원고 하나, 차수 지정, LLM 미설정(판단불가·이유), 잘못된 입력."""

import tempfile
import unittest
from pathlib import Path

import make_fixtures as mf

MANUSCRIPT = ["차 례", "학습모듈의 개요", "1-1.", "국내외 인증 조사", "필요 지식", "<표 1-3> SW제품 관련 국내 인증", "보안기능 확인서",
              "CSAP 인증", "수행 내용", "SW 기술자 평균임금은 매년 한국인공지능·소프트웨어산업협회에서 공표한다."]


def opinion_rows(title, text):
    return [[title, "검토의견서", ""], ["구분", "쪽수", "검토의견"], ["학습 1-1", "필요지식", text], ["종합 의견", "", ""],
            ["- 전체적으로 적절하게 작성되어 있음", "", ""]]


class OpinionWebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        self.out = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(out_dir=self.out.name))
        self.client.__enter__()
        folder = Path(self.out.name)
        self.final = folder / "최종원고.hwpx"
        mf.write_hwpx(self.final, [[mf.p(t) for t in MANUSCRIPT]])
        self.first = folder / "1차_의견서.hwpx"
        mf.write_hwpx(self.first, [[mf.table(opinion_rows("1차 검토", "- <표 1-3> 보안기능 확인서도 추가되면 좋을 것"))]])
        self.second = folder / "2차_의견서.hwpx"
        mf.write_hwpx(self.second, [[mf.table(opinion_rows("2차 검토", "- 한국소프트웨어산업협회는 한국인공지능·소프트웨어산업협회로 명칭 변경됨"))]])

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.out.cleanup()

    def post(self, data=None, opinions=(), **files):
        upload = [("opinions", (p.name, p.read_bytes())) for p in opinions]
        upload += [(k, (v.name, v.read_bytes())) for k, v in files.items()]
        return self.client.post("/api/opinion", data=data or {}, files=upload)

    def test_two_sheets_and_summary(self):
        response = self.post(opinions=(self.first, self.second), manuscript=self.final)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["원고"], self.final.name)
        self.assertEqual([s["차수"] for s in body["의견서"]], ["1차", "2차"])
        self.assertEqual(body["요약"]["총 의견"], 4)
        # 테스트 환경에는 키·승인이 없다 — 규칙으로 대신 판정하지 않고 모두 '확인 필요'와 이유
        self.assertTrue(body["LLM"].startswith("LLM 미설정"), body["LLM"])
        self.assertEqual((body["요약"]["확인 필요"], body["요약"]["반영 후보"], body["요약"]["조치 불필요"]), (4, 0, 0))
        row = body["의견"][0]
        self.assertEqual((row["판정"], row["유형"], row["LLM"]["상태"]), ("확인 필요", "미분류", body["LLM"]))
        self.assertIn("사람이 대조", row["비고"][-1])

    def test_deliberation_sheet(self):
        """심의의견서: 표 머리가 '심의의견'이어도 읽고, 차수 '심의'와 요약의 심의 의견 수가 온다."""
        third = Path(self.out.name) / "심의의견서.hwpx"
        rows = [["심의의견서", "", ""], ["구분", "쪽수", "심의의견"], ["학습 1-1", "필요지식", "- <표 1-3>에 GS인증 근거 법령을 밝힐 것"]]
        mf.write_hwpx(third, [[mf.table(rows)]])
        response = self.post({"rounds": ["2차", "심의"]}, opinions=(self.second, third), manuscript=self.final)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([s["차수"] for s in body["의견서"]], ["2차", "심의"])
        self.assertEqual(body["요약"]["심의 의견"], 1)
        self.assertEqual([r["차수"] for r in body["의견"]][-1], "심의")

    def test_rounds_override(self):
        response = self.post({"rounds": ["2차"]}, opinions=(self.first,), manuscript=self.final)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["의견서"][0]["차수"], "2차")

    def test_same_file_names_are_kept_apart(self):
        response = self.post(opinions=(self.first, self.first), manuscript=self.final)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["의견서"]), 2)

    def test_bad_inputs_are_400(self):
        bad = Path(self.out.name) / "메모.txt"
        bad.write_text("의견서 아님", encoding="utf-8")
        response = self.post(opinions=(bad,), manuscript=self.final)
        self.assertEqual(response.status_code, 400)
        self.assertIn("메모.txt", response.json()["error"])
        self.assertEqual(self.post(opinions=(self.final,), manuscript=self.final).status_code, 400)   # 표 없는 hwpx
        self.assertEqual(self.client.post("/api/opinion").status_code, 400)


if __name__ == "__main__":
    unittest.main()
