"""원고 진행 현황(REQ-02-007, ncs_service.progress) — 개수만 남기는 요약, 기록 → 단계 7개와 진행도, 목록의 단계 수, DB 없는 서버."""

import json
import tempfile
import unittest

from ncs_service.progress import (EMPTY, OPINION, RECORDED, RIGHTS, STAGES, build, content_progress, editing_progress,
                                  stages_recorded, summarize_opinion, summarize_rights)

CODE = "LM2001021701_25v1"


def opinion_result():
    rows = [("1차", "반영 후보"), ("1차", "미반영 후보"), ("1차", "조치 불필요"), ("2차", "확인 필요"), ("심의", "반영 후보"), ("", "확인 필요")]
    return {"의견": [{"번호": i, "차수": r, "판정": v, "의견": "비밀 의견 문장", "근거": [{"문단": "원고 문단"}]} for i, (r, v) in enumerate(rows, 1)],
            "요약": {"총 의견": 6, "조치 요구": 5, "반영 후보": 2, "미반영 후보": 1, "확인 필요": 2, "조치 불필요": 1}, "LLM": "사용(모델) · 호출 2번"}


def record(kind, counts, at, manuscript="원고.hwpx"):
    return {"id": at, "created_at": at, "kind": kind, "manuscript": manuscript, "counts": counts}


class SummaryTests(unittest.TestCase):
    def test_opinion_summary_keeps_counts_only(self):
        summary = summarize_opinion(opinion_result())
        self.assertEqual(summary["전체"]["총 의견"], 6)
        self.assertEqual(summary["차수별"]["1차"], {"총 의견": 3, "조치 요구": 2, "반영 후보": 1, "미반영 후보": 1, "확인 필요": 0, "조치 불필요": 1})
        self.assertEqual(sorted(summary["차수별"]), ["1차", "2차", "심의", "차수 모름"])
        self.assertEqual(summary["생성형 AI"], "사용")
        text = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn("비밀 의견 문장", text)      # 의견 글·원고 문단은 남기지 않는다
        self.assertNotIn("원고 문단", text)

    def test_rights_summary_keeps_verdict_and_counts(self):
        report = {"요약": {"판정": "부적합", "원고 그림": 12, "목록 행": 10, "학습모듈명": "m", "적합": 8, "부적합": 3, "판단불가": 1, "누락": 2, "확인 필요": 1},
                  "현황표": [{"그림": "[그림 1-1]", "출처": "누구"}], "지적사항": [{"내용": "비밀"}]}
        summary = summarize_rights(report)
        self.assertEqual((summary["판정"], summary["원고 그림"], summary["누락"]), ("부적합", 12, 2))
        self.assertNotIn("비밀", json.dumps(summary, ensure_ascii=False))
        self.assertNotIn("학습모듈명", summary)


class BuildTests(unittest.TestCase):
    def sources(self):
        counts = summarize_opinion(opinion_result())
        return {
            "reviews": {"count": 12, "first": "2026-11-01T00:00:00+00:00", "last": "2026-11-20T00:00:00+00:00"},
            "plan": {"count": 1, "last": "2026-10-20T00:00:00+00:00", "verdict": "적합"},
            "latest_checks": [
                {"id": "a", "check": "toc", "created_at": "2026-11-20", "verdict": "부적합",
                 "sheet": [{"번호": "①", "검수결과": "적합"}, {"번호": "②", "검수결과": "부적합"}, {"번호": "⑦", "검수결과": "미검사"}]},
                {"id": "b", "check": "position", "created_at": "2026-11-20", "verdict": "판단불가",
                 "sheet": [{"번호": "①", "검수결과": "적합"}, {"번호": "⑤", "검수결과": "판단불가"}]},
                {"id": "c", "check": "plan", "created_at": "2026-10-20", "verdict": "적합", "sheet": [{"번호": "①", "검수결과": "적합"}]},
            ],
            "last_group": {"group_id": "g", "created_at": "2026-11-20T00:00:00+00:00", "checks": ["toc", "position"], "verdict": "부적합"},
            "volume": {"id": "v", "created_at": "2026-11-21T00:00:00+00:00", "manuscript": "원고.hwpx", "pages": 80, "unit_price": 50000,
                       "fee": 4000000, "estimated": False},
            "volume_count": 2,
            "records": [record(RIGHTS, {"판정": "부적합", "원고 그림": 12, "누락": 2}, "2026-11-19T00:00:00+00:00"),
                        record(OPINION, counts, "2026-11-18T00:00:00+00:00"),
                        record(OPINION, {"차수별": {"1차": dict(counts["차수별"]["1차"], **{"총 의견": 99})}}, "2026-11-10T00:00:00+00:00")],
            "images": {"total": 12, "confirmed": 5},
        }

    def test_all_stages_recorded(self):
        result = build(CODE, self.sources(), name="AIoT 운영 플랫폼 요구사항 분석")
        self.assertEqual([s["번호"] for s in result["단계"]], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual({s["상태"] for s in result["단계"]}, {RECORDED})
        by = {s["번호"]: s for s in result["단계"]}
        self.assertEqual(by[2]["일시"], "2026-11-01T00:00:00+00:00")             # 초고본 검토 = 처음 검수한 날
        self.assertIn("의견 3개 중 반영 후보 1, 미반영 후보 1", by[3]["내용"])       # 1차 의견은 가장 최근 기록(99개짜리 옛 기록 아님)
        self.assertIn("확인 필요 1", by[4]["내용"])
        self.assertIn("부적합", by[6]["내용"])
        self.assertEqual(by[7]["일시"], "2026-11-21T00:00:00+00:00")
        self.assertIn("분량 80매", by[7]["내용"])
        self.assertEqual(result["학습모듈명"], "AIoT 운영 플랫폼 요구사항 분석")
        self.assertEqual(result["기록 수"], {"원고 검수": 12, "개발계획서 점검": 1, "의견 반영 검토": 2, "권리 증빙 점검": 1, "분량 산정": 2})

    def test_progress_numbers(self):
        progress = build(CODE, self.sources())["진행도"]
        editing = progress["편집 검수"]
        self.assertEqual([c["검수"] for c in editing["구성요소"]], ["toc", "position"])      # 개발계획서 점검은 편집 검수에 넣지 않는다
        self.assertEqual(editing["항목"], {"적합": 2, "부적합": 1, "판단불가": 1, "그 밖": 1})
        self.assertEqual(editing["적합 비율"], 50.0)
        content = progress["내용 검수"]
        self.assertEqual([r["차수"] for r in content["차수"]], ["1차", "2차", "심의", "차수 모름"])
        self.assertEqual((content["합계"]["총 의견"], content["합계"]["미반영 후보"]), (6, 1))
        self.assertEqual(progress["저작권 검수"]["권리 증빙"]["누락"], 2)
        self.assertEqual(progress["저작권 검수"]["이미지 저작권 DB"], {"그림": 12, "확정": 5})
        self.assertEqual(progress["분량"]["pages"], 80)

    def test_only_volume_record(self):
        result = build(CODE, {"volume": self.sources()["volume"], "volume_count": 1, "records": [], "images": {"total": 0, "confirmed": 0}})
        self.assertEqual([s["상태"] for s in result["단계"]], [EMPTY] * 6 + [RECORDED])
        self.assertIsNone(result["진행도"]["편집 검수"]["항목"])
        self.assertIsNone(result["진행도"]["내용 검수"]["합계"])
        self.assertIsNone(result["진행도"]["저작권 검수"]["권리 증빙"])
        self.assertEqual(content_progress([]), {"차수": [], "합계": None})
        self.assertEqual(editing_progress([])["적합 비율"], None)

    def test_stage_count_for_list(self):
        self.assertEqual(len(STAGES), 7)
        self.assertEqual(stages_recorded({"plan", "review", "group", "volume", "opinion", "opinion:1차", "opinion:2차", "opinion:심의"}), 7)
        self.assertEqual(stages_recorded({"review"}), 1)
        self.assertEqual(stages_recorded({"opinion", "opinion:1차 심의", "rights"}), 2)      # '1차 심의'는 심의 단계
        self.assertEqual(stages_recorded(set()), 0)


class WebWithoutDatabaseTests(unittest.TestCase):
    def test_routes_are_absent_and_checks_still_answer(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        with tempfile.TemporaryDirectory() as folder, TestClient(create_app(out_dir=folder)) as client:
            self.assertFalse(client.get("/api/health").json()["history"])
            self.assertEqual(client.get("/api/manuscripts").status_code, 404)      # 이력이 없는 저장소에는 붙지 않는다


if __name__ == "__main__":
    unittest.main()
