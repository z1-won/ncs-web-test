"""필요 지식 ⑧ 출처 표기: F14 출처 형식 14종 골격, 그림·표의 출처 줄 찾기, 위치."""

import unittest

from ncs_knowledge.figtab import _flatten, collect_labels
from ncs_knowledge.rules.sources import check_sources, source_check

F14_EXAMPLES = [  # F14 p.7 '출처' 예시 14종을 실제 값으로 채운 것
    "출처: 교육부(2021). 객실 예약 관리(LM1203020201_19v2). 한국직업능력연구원. p.50.",
    "출처: 김철수(2020). 『호텔 경영론』. 백산출판사. p.12.",
    "출처: 홍길동(2024. 3. 5.). “호텔 예약 급증”. 한국일보. https://www.hankookilbo.com/news/1.",
    "출처: 김철수(2019). 객실 운영 사례. 관광학 연구 자료집. p.33.",
    "출처: 이영희(2022). 「호텔 예약 시스템 연구」. 『관광학연구』. 46(3). p.101.",
    "출처: 박순희(2021). 「객실 요금 전략」. 석사학위 논문. 경희대학교 관광대학원. p.40.",
    "출처: 객실 점유율 통계(2025). 한국관광공사 홈페이지(https://kto.visitkorea.or.kr/stat)에서 2026. 1. 15. 검색.",
    "출처: 코틀러([2016] 2019). 『마케팅 관리(Marketing Management)』. 윤훈현(역). 피어슨에듀케이션. p.77.",
    "출처: 관광진흥법(2024. 2. 27. 제4조).",
    "출처: 국가기술표준원(2023). KS A 0001. 한국표준협회. p.5.",
    "출처: 공공누리 홈페이지(https://www.kogl.go.kr)에서 2026. 1. 15. 검색. 공공누리 제1유형.",
    "출처: 호텔 PMS 화면(https://www.example.com/pms)에서 2026. 1. 15. 스크린 숏.",
    "출처: 집필진 제작(2026)",
    "출처: 오페라 PMS. 2024. 8. 12. 스크린 숏.",
]


class SourceCheckTests(unittest.TestCase):
    def test_all_f14_templates_pass(self):
        for text in F14_EXAMPLES:
            with self.subTest(text=text):
                self.assertEqual(source_check(text)[0], "O", source_check(text))

    def test_failures_with_hints(self):
        self.assertEqual(source_check("교육부(2021). 제목. 발행처. p.1.")[1], '"출처:" 로 시작하지 않음')
        value, note = source_check("출처: 교육부(2021), 객실 예약 관리. 한국직업능력연구원. p.50.")
        self.assertEqual(value, "X")
        self.assertIn("쉼표", note)
        self.assertIn("끝에 마침표 없음", source_check("출처: 교육부(2021). 객실 예약 관리. 한국직업능력연구원. p.50")[1])
        self.assertIn("연도 괄호", source_check("출처: 교육부. 객실 예약 관리.")[1])
        self.assertEqual(source_check("출처: 집필진 제작 Google AI 활용 도식화 (2026)")[0], "△")


def run(body, table_rows=(), lesson_spans=None):
    sections = [["차례"], body]
    flat = _flatten(sections)
    caps, _, _ = collect_labels(flat)
    return check_sources(body, 1, caps, frozenset(table_rows), lookback=3, lookahead=80, lesson_spans=lesson_spans)


class CheckSourcesTests(unittest.TestCase):
    def test_figure_source_above_and_missing(self):
        body = ["학습 1", "출처: 집필진 제작(2026)", "[그림 1-1] 가", "본문", "[그림 1-2] 출처 없는 그림", "출처: 떠 있는 출처 줄"]
        rows = run(body, lesson_spans=[(1, 1, 7)])
        self.assertEqual([(r["region_path"].split(" > ")[-1], r["판정"]) for r in rows],
                         [("[그림 1-1]", "적합"), ("[그림 1-2]", "부적합"), ("p5", "판단불가")])
        self.assertEqual(rows[0]["위치"], "학습 1")
        self.assertEqual(rows[1]["체크"], {"출처 줄 존재": "X"})

    def test_table_source_inside_frame_and_not_the_next_figures(self):
        body = ["〈표 1-1〉 표", "셀", "셀", "출처: 집필진 제작(2026)",            # 틀(표) 안의 출처 → 표의 것
                "〈표 1-2〉 둘째 표", "셀", "출처: 집필진 제작(2026)", "[그림 1-1] 그림"]  # 이 출처는 바로 아래 그림의 것
        rows = run(body, table_rows={0, 1, 2, 3, 4, 5})
        by = {r["region_path"].split(" > ")[-1]: r for r in rows}
        self.assertEqual(by["〈표 1-1〉"]["체크"]["출처 줄 존재"], "O")
        self.assertEqual(by["〈표 1-2〉"]["체크"]["출처 줄 존재"], "-")
        self.assertEqual(by["[그림 1-1]"]["체크"]["출처 줄 존재"], "O")

    def test_old_agency_name_is_flagged(self):
        [row] = run(["출처: 교육부(2021). 모듈(LM1). 한국직업능력개발원. p.1.", "[그림 1-1] 가"])
        self.assertEqual(row["체크"]["기관명"], "△")


class AiMarkTests(unittest.TestCase):
    """AI 활용 표기(REQ-02-008): 출처 줄 → 'OO를 활용하여 생성함/수정 보완함. 일자' → 그림 번호 순서와 꼴, 생성함/수정 보완함 구분."""

    def figure(self, *lines):
        [row] = run(["학습 1", *lines, "[그림 1-1] 개념도"])
        return row

    def test_well_formed_mark_passes_and_is_not_an_odd_paragraph(self):
        for source, line in (("출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 7. 20."),
                             ("출처: 집필진 제작(2026)", "Gemini 3을 활용하여 수정 보완함. 2026. 11. 23."),
                             ("출처: 김철수(2020). 『호텔 경영론』. 백산출판사. p.12.", "ChatGPT 6.0을 활용하여 수정 보완함. 2026. 7. 20.")):
            row = self.figure(source, line)
            self.assertEqual((row["판정"], row["체크"]["AI 활용 줄 형식"], row["체크"]["AI 활용 방식 구분"]), ("적합", "O", "O"), line)
            self.assertNotIn("출처 줄 위치", row["비고"])          # 출처 줄과 캡션 사이의 AI 활용 줄은 '다른 문단'이 아니다

    def test_missing_date_and_wrong_order_are_form_errors(self):
        no_date = self.figure("출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함.")
        self.assertEqual((no_date["판정"], no_date["체크"]["AI 활용 줄 형식"]), ("부적합", "X"))
        self.assertIn("일자", no_date["비고"]["AI 활용 줄 형식"])
        self.assertIn("「ChatGPT를 활용하여 생성함.」", no_date["비고"]["AI 활용 줄 형식"])
        bad_day = self.figure("출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 2. 30.")
        self.assertEqual(bad_day["체크"]["AI 활용 줄 형식"], "X")
        above = self.figure("ChatGPT를 활용하여 생성함. 2026. 7. 20.", "출처: 집필진 제작(2026)")
        self.assertEqual((above["판정"], above["체크"]["AI 활용 줄 형식"]), ("부적합", "X"))
        self.assertIn("출처 줄 아래", above["비고"]["AI 활용 줄 형식"])
        self.assertIsNotNone(above["수정 제안"])

    def test_spacing_or_extra_words_are_not_form_errors(self):
        """띄어쓰기·마침표 차이, 뒤에 붙은 글은 형식 오류로 보지 않는다 — 요구사항(REQ-02-008)은 도구·'생성함/수정 보완함'·일자와 순서만 정하고,
        직능연 표기 예(F08) 원문도 날짜 띄어쓰기가 어긋나거나 캡션이 붙은 예가 있다. 출처 검토(ncs_sources)와 같은 기준."""
        for line in ("ChatGPT를 활용하여 수정보완함. 2026. 7. 20.", "ChatGPT를 활용하여 생성함 2026.7.20", "ChatGPT를 활용하여 생성함. 2026. 7. 20. (초안)",
                     "ChatGPT를 활용하여 수정 보완함. 2026 .6. 23."):
            row = self.figure("출처: 집필진 제작(2026)", line)
            self.assertEqual((row["판정"], row["체크"]["AI 활용 줄 형식"]), ("적합", "O"), line)

    def test_generated_with_someone_elses_source_is_a_candidate(self):
        row = self.figure("출처: 김철수(2020). 『호텔 경영론』. 백산출판사. p.12.", "ChatGPT를 활용하여 생성함. 2026. 7. 20.")
        self.assertEqual((row["판정"], row["체크"]["AI 활용 줄 형식"], row["체크"]["AI 활용 방식 구분"]), ("판단불가", "O", "△"))
        self.assertIn("수정 보완함", row["비고"]["AI 활용 방식 구분"])

    def test_mark_without_a_source_line_and_ai_words_without_a_mark(self):
        alone = self.figure("ChatGPT를 활용하여 생성함. 2026. 7. 20.")
        self.assertEqual((alone["체크"]["출처 줄 존재"], alone["체크"]["AI 활용 줄 형식"], alone["판정"]), ("X", "O", "부적합"))
        hint = self.figure("출처: 집필진 제작(2026)", "생성형 AI로 그린 그림")
        self.assertEqual((hint["판정"], hint["체크"]["AI 활용 줄 형식"]), ("판단불가", "△"))
        # 출처 줄 안에 AI 활용을 섞어 쓴 것: 도구 이름·'AI 활용'처럼 분명하면 형식 오류(X) — AI 활용 줄은 출처 줄과 따로 적는다(REQ-02-008 ①②).
        old = self.figure("출처: 집필진 제작 Google AI 활용 도식화 (2026)")
        self.assertEqual((old["판정"], old["체크"]["AI 활용 줄 형식"]), ("부적합", "X"))
        self.assertIn("출처 줄 안에", old["비고"]["AI 활용 줄 형식"])
        # '생성'·'도식화' 같은 낱말뿐이면 제목일 수 있다 — 후보(△)로만
        weak = self.figure("출처: 김철수(2020) 보고서 생성 기법, 백산출판사")
        self.assertNotIn("AI 활용 줄 형식", weak["체크"])

    def test_figures_without_ai_are_untouched(self):
        row = self.figure("출처: 집필진 제작(2026)")
        self.assertEqual(row["체크"], {"출처 줄 존재": "O", "출처 형식 골격": "O"})
        far = self.figure("출처: 집필진 제작(2026)", "그림을 설명하는 본문 문장이다.")
        self.assertEqual(far["체크"], {"출처 줄 존재": "O", "출처 형식 골격": "O"})
        self.assertIn("출처 줄 위치", far["비고"])
        sentence = self.figure("출처: 집필진 제작(2026)", "실습에서는 ChatGPT를 활용하여 생성함으로써 시간을 줄인다고 설명한다.")
        self.assertNotIn("AI 활용 줄 형식", sentence["체크"])       # 본문 문장 속 표현은 AI 활용 줄이 아니다


if __name__ == "__main__":
    unittest.main()
