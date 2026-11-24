"""원고 진행 현황(REQ-02-007, ncs_service.workflow.progress) — 개수만 남기는 요약, 기록 → 단계 7개와 진행도, 목록의 단계 수, DB 없는 서버."""

import json
import tempfile
import unittest

from ncs_service.workflow.progress import (EMPTY, FIGURES, OPINION, RECORDED, RIGHTS, SOURCES, STAGES, build, content_progress, editing_progress,
                                  stages_recorded, summarize_figures, summarize_opinion, summarize_rights, summarize_sources)

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
        self.assertEqual(result["기록 수"], {"원고 검수": 12, "개발계획서 점검": 1, "의견 반영 검토": 2, "권리 증빙 점검": 1, "그림 검수": 0, "출처 검토": 0, "분량 산정": 2})

    def test_done_is_marked_by_a_person_not_inferred_from_records(self):
        """기록이 있어도 완료가 아니다. 완료는 담당자가 표시한 단계만이고, 기록이 없는 단계도 완료로 표시할 수 있다."""
        sources = self.sources()
        result = build(CODE, sources)
        self.assertEqual((result["완료 단계 수"], [s["완료"] for s in result["단계"]]), (0, [False] * 7))
        sources["done"] = {1: {"by": "김에디터", "at": "2026-10-21T00:00:00+00:00", "note": "직능연 승인"}, 4: {"by": "김에디터", "at": "2026-11-20T00:00:00+00:00", "note": ""}}
        sources["history"] = [{"stage": 4, "action": "done", "by": "김에디터", "at": "2026-11-20T00:00:00+00:00", "note": ""}]
        result = build(CODE, sources)
        by = {s["번호"]: s for s in result["단계"]}
        self.assertEqual(result["완료 단계 수"], 2)
        self.assertEqual((by[1]["완료"], by[1]["완료한 사람"], by[1]["메모"]), (True, "김에디터", "직능연 승인"))
        self.assertEqual((by[2]["완료"], by[2]["상태"]), (False, RECORDED))
        self.assertEqual(len(result["이력"]), 1)
        empty = build(CODE, {"done": {3: {"by": "가", "at": "2026-11-20T00:00:00+00:00", "note": ""}}})      # 기록이 하나도 없는 원고
        self.assertEqual([(s["완료"], s["상태"]) for s in empty["단계"]][2], (True, EMPTY))

    def test_reviews_tagged_with_a_stage_show_at_that_stage(self):
        sources = self.sources()
        self.assertIn("단계를 고르지 않은 기록", {s["번호"]: s for s in build(CODE, sources)["단계"]}[2]["내용"])
        sources["staged_reviews"] = {2: {"count": 3, "last": "2026-11-02T00:00:00+00:00", "verdict": "부적합"},
                                     3: {"count": 1, "last": "2026-11-11T00:00:00+00:00", "verdict": "판단불가"},
                                     6: {"count": 2, "last": "2026-11-20T00:00:00+00:00", "verdict": "적합"}}
        by = {s["번호"]: s for s in build(CODE, sources)["단계"]}
        self.assertEqual((by[2]["내용"], by[2]["일시"]), ("초고본으로 표시한 원고 검수 3건, 최근 판정 부적합", "2026-11-02T00:00:00+00:00"))
        self.assertTrue(by[3]["내용"].startswith("수정본으로 표시한 원고 검수 1건, 최근 판정 판단불가. 의견 3개 중"))
        self.assertEqual(by[6]["내용"], "최종본으로 표시한 원고 검수 2건, 최근 판정 적합")

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

    def test_remaining_work_is_counted_the_same_way_for_all_three(self):
        """목록과 상세가 함께 쓰는 '남은 일' — 편집·내용·저작권 검수를 모두 '남은 것 / 전체'로(정의서 REQ-02-007 사람 작업 1~3)."""
        left = build(CODE, self.sources())["남은 일"]
        self.assertEqual(left["편집 검수"], {"남음": 1, "전체": 4, "판단불가": 1})          # 부적합 1 / 판정한 4항목('그 밖'은 뺀다)
        self.assertEqual((left["내용 검수"]["남음"], left["내용 검수"]["전체"], left["내용 검수"]["확정"]), (1, 6, False))   # 미반영 후보 1 / 의견 6
        empty = build(CODE, {})["남은 일"]
        self.assertEqual(empty, {"편집 검수": None, "내용 검수": None, "저작권 검수": None})

    def test_figure_and_source_reviews_are_counted_in_copyright_progress(self):
        """그림 검수(REQ-02-005)와 출처 검토(REQ-02-008)의 결과도 저작권 검수 진행도에 모은다 — 정의서: 002·003·005·008을 종합, 집계 누락 0건."""
        figures = summarize_figures({"review": {"summary": {"그림": 20, "검수 대상": 17, "위험도": {"문제없음": 10, "확인 필요": 5, "고위험": 2},
                                                            "체크별 X/△": {"① 출처": [3, 1]}}, "rows": [{"원고": "비밀"}]}})
        self.assertEqual(figures, {"그림": 20, "검수 대상": 17, "문제없음": 10, "확인 필요": 5, "고위험": 2, "정정 필요": 7})
        sources_counts = summarize_sources({"summary": {"그림 출처": 17, "표": 28, "표 중 출처 있음": 3, "본문 출처 줄": 1, "참고 자료 항목": 4,
                                                        "문장 단위 출처 후보": 2, "판정": {"적합": 43, "부적합": 2, "판단불가": 1}, "AI 표기": 3}, "rows": [{"원고": "비밀"}]})
        self.assertEqual(sources_counts, {"총 출처": 46, "적합": 43, "부적합": 2, "판단불가": 1, "정정 필요": 3, "참고 자료 항목": 4,
                                         "문장 단위 출처 후보": 2, "AI 표기": 3})
        self.assertNotIn("비밀", json.dumps([figures, sources_counts], ensure_ascii=False))
        sources = self.sources()
        sources["records"] = [record(FIGURES, figures, "2026-11-22T00:00:00+00:00"), record(SOURCES, sources_counts, "2026-11-22T01:00:00+00:00"),
                              record(FIGURES, {"그림": 1, "정정 필요": 1}, "2026-11-01T00:00:00+00:00")] + sources["records"]
        result = build(CODE, sources)
        rights = result["진행도"]["저작권 검수"]
        self.assertEqual((rights["그림 검수"]["그림"], rights["그림 검수"]["정정 필요"], rights["그림 검수"]["일시"]), (20, 7, "2026-11-22T00:00:00+00:00"))
        self.assertEqual((rights["출처 검토"]["총 출처"], rights["출처 검토"]["정정 필요"]), (46, 3))
        self.assertEqual(rights["합계"], {"총 개수": 66, "정정 필요": 10})          # 사람 작업 3: 총 저작권 개수 / 정정 필요 개수
        self.assertEqual((result["기록 수"]["그림 검수"], result["기록 수"]["출처 검토"]), (2, 1))
        self.assertIsNone(build(CODE, self.sources())["진행도"]["저작권 검수"]["그림 검수"])      # 기록이 없으면 None
        self.assertIsNone(build(CODE, self.sources())["진행도"]["저작권 검수"]["합계"])

    def test_confirmed_decisions_show_in_content_progress(self):
        """의견 반영 검토의 담당자 확정(REQ-02-003 사람 작업 4)이 내용 검수 진행도에 나온다 — 가장 최근에 확정을 적은 기록."""
        sources = self.sources()
        confirmed = {"의견별": {"1": "반영", "2": "미반영"}, "확정": 2, "반영": 1, "미반영": 1, "후보와 다름": 0, "보류였던 것": 0, "오차율": "0.0%",
                     "결과": "통과", "확정 시각": "2026-11-23T00:00:00+00:00"}
        sources["records"][1]["counts"] = {**sources["records"][1]["counts"], "확정": confirmed}
        content = build(CODE, sources)["진행도"]["내용 검수"]
        self.assertEqual((content["확정"]["확정"], content["확정"]["반영"], content["확정"]["미반영"], content["확정"]["오차율"]), (2, 1, 1, "0.0%"))
        self.assertNotIn("의견별", content["확정"])
        self.assertIsNone(build(CODE, self.sources())["진행도"]["내용 검수"]["확정"])

    def test_only_volume_record(self):
        result = build(CODE, {"volume": self.sources()["volume"], "volume_count": 1, "records": [], "images": {"total": 0, "confirmed": 0}})
        self.assertEqual([s["상태"] for s in result["단계"]], [EMPTY] * 6 + [RECORDED])
        self.assertIsNone(result["진행도"]["편집 검수"]["항목"])
        self.assertIsNone(result["진행도"]["내용 검수"]["합계"])
        self.assertIsNone(result["진행도"]["저작권 검수"]["권리 증빙"])
        self.assertEqual(content_progress([]), {"차수": [], "합계": None, "확정": None})
        self.assertEqual(editing_progress([])["적합 비율"], None)

    def test_stage_count_for_list(self):
        self.assertEqual(len(STAGES), 7)
        self.assertEqual(stages_recorded({"plan", "review", "group", "volume", "opinion", "opinion:1차", "opinion:2차", "opinion:심의"}), 7)
        self.assertEqual(stages_recorded({"review"}), 1)
        self.assertEqual(stages_recorded({"opinion", "opinion:1차 심의", "rights"}), 2)      # '1차 심의'는 심의 단계
        self.assertEqual(stages_recorded(set()), 0)
        from ncs_service.workflow.progress import stages_done
        self.assertEqual(stages_done({"review", "done:1", "done:6"}), 2)
        self.assertEqual(stages_recorded({"done:1", "done:6"}), 0)      # 완료 표시는 기록이 아니다


class WebWithoutDatabaseTests(unittest.TestCase):
    def test_routes_are_absent_and_checks_still_answer(self):
        from fastapi.testclient import TestClient
        from ncs_web.server import create_app

        with tempfile.TemporaryDirectory() as folder, TestClient(create_app(out_dir=folder)) as client:
            self.assertFalse(client.get("/api/health").json()["history"])
            self.assertEqual(client.get("/api/manuscripts").status_code, 404)      # 이력이 없는 저장소에는 붙지 않는다


class PageProgressTests(unittest.TestCase):
    """편집 검수 진행도의 쪽 수(REQ-02-007 사람 작업 1번 '진행완료 페이지 / 총 페이지')."""

    def test_pages_are_merged_across_checks(self):
        from ncs_service.workflow.progress import editing_progress, page_progress, remaining

        checks = [{"check": "toc", "created_at": "2026-11-24T00:00:00", "verdict": "부적합", "sheet": [{"검수결과": "부적합"}],
                   "pages": {"총 쪽": 40, "지적 쪽": [3, 7], "못 찾은 항목": 1}},
                  {"check": "overview", "created_at": "2026-11-24T00:00:00", "verdict": "부적합", "sheet": [{"검수결과": "적합"}],
                   "pages": {"총 쪽": 40, "지적 쪽": [7, 12, 99], "못 찾은 항목": 0}},
                  {"check": "misc", "created_at": "2026-11-24T00:00:00", "verdict": "적합", "sheet": [], "pages": None},      # hwp 원고, 옛 기록
                  {"check": "plan", "created_at": "2026-11-24T00:00:00", "verdict": "적합", "sheet": [], "pages": {"총 쪽": 5, "지적 쪽": [1]}}]
        pages = page_progress(checks)
        self.assertEqual(pages, {"전체": 40, "남음": 3, "완료": 37, "못 찾은 항목": 1, "센 구성요소": 2})       # 같은 쪽은 한 번, 총 쪽을 넘는 값은 뺀다
        editing = editing_progress(checks)
        self.assertEqual(editing["쪽"], pages)
        left = remaining({"편집 검수": editing, "내용 검수": {}, "저작권 검수": {}})
        self.assertEqual(left["편집 검수"]["쪽"]["완료"], 37)

    def test_no_pages_when_no_run_counted_them(self):
        from ncs_service.workflow.progress import page_progress

        self.assertIsNone(page_progress([{"check": "toc", "pages": None}, {"check": "misc"}]))

    def test_manuscript_without_layout_has_no_pages(self):
        from pathlib import Path

        from ncs_service.annotate import page_progress

        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "원고_ok_LM1203020201_24v3.hwpx"
        self.assertIsNone(page_progress(fixture.read_bytes(), []))      # 한글이 저장하지 않은 파일(배치 정보 없음)


if __name__ == "__main__":
    unittest.main()
