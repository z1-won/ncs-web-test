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


if __name__ == "__main__":
    unittest.main()
