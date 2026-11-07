"""참고 자료 ①(본문 인용 수록)·②(F14 서지 양식 22종)·③(나열 순서)와 항목·출처 읽기."""

import unittest

from ncs_references.entries import collect_citations, collect_entries, key_of, script_of
from ncs_references.rules.coverage import check_coverage
from ncs_references.rules.format import check_format
from ncs_references.rules.order import check_order
from ncs_references.templates import hints, match_template

F14_DOMESTIC = [  # 참고자료.hwpx 국내 17종을 실제 값으로 채운 것
    "공공누리 홈페이지(https://www.kogl.go.kr/info/1)에서 2026. 1. 15. 검색. 공공누리 제1유형.",
    "관광진흥법(2024. 2. 27. 제4조).",
    "교육부(2021). 객실 예약 관리(LM1203020201_19v2). 한국직업능력연구원.",
    "국가기술표준원(2023). KS A 0001. 한국표준협회.",
    "홍길동(2024. 3. 5.). “호텔 예약 급증”. 한국일보. https://www.hankookilbo.com/news/1",
    "문화체육관광부(2025. 2. 1.). 관광 활성화 대책 발표.",
    "객실 점유율 통계(2025). 한국관광공사 홈페이지(https://kto.visitkorea.or.kr/stat)에서 2026. 1. 15. 검색.",
    "코틀러([2016] 2019). 『마케팅 관리(Marketing Management)』. 윤훈현(역). 피어슨에듀케이션.",
    "박순희(2021). 「객실 요금 전략」. 석사학위 논문. 경희대학교 관광대학원.",
    "이영희(2022). 「호텔 예약 시스템 연구」. 『관광학연구』. 46(3). 101-120.",
    "김철수(2020). 『호텔 경영론』. 백산출판사",
    "김철수(2020). 『호텔 경영론』. 백산출판사.",
    "한국관광공사(2024). 숙박업 실태 조사 보고서. 한국관광공사.",
    "김영희(2019). 객실 운영 사례. 관광학 연구 자료집.",
    "한국호텔협회(2023). 호텔경영 월보. 한국호텔협회.",
    "홍길동(2022). 객실 예약 장치(대한민국 특허 10-1234567). 서울.",
    "오페라 PMS. 2024. 8. 12. 스크린 숏.",
]
F14_FOREIGN = [
    "Smith, J. (2024. 3. 5.). Hotel bookings surge. The Times.",
    "Oracle Hospitality (2024). OPERA Cloud Property Management. Retrieved from(https://www.oracle.com/hospitality/opera).",
    "Kasavana, M. L. (2003). Managing Technology in the Hospitality Industry. Lansing, MI: Educational Institute.",
    "Murphy, J. (2011). Hotel data management. In P. Kokaz (Ed.), Hospitality Technology(pp. 4-15). Springer.",
    "Lee, S. (2020). Revenue management in hotels (Doctoral dissertation). Cornell University. Ithaca, NY.",
    "Murphy, J. (2011). Hotel data management via PMS systems. Journal of Hospitality and Tourism Technology. 2(1). 4-15.",
]


class TemplateTests(unittest.TestCase):
    def test_all_f14_templates_match(self):
        for text in F14_DOMESTIC:
            with self.subTest(text=text):
                self.assertIsNotNone(match_template(text, "국문"), text)
        for text in F14_FOREIGN:
            with self.subTest(text=text):
                self.assertIsNotNone(match_template(text, "영문"), text)

    def test_hints_for_common_violations(self):
        self.assertIn("국문 저자와 연도 괄호 사이를 띄움(붙여 씀)", hints("김민선 (2025). 『책』. 출판사.", "국문"))
        self.assertIn("《 》 사용(학술지·책명은 『 』)", hints("김민선(2025). 「제목」. 《학술지》. 1(2). 3-4.", "국문"))
        self.assertIn("제목 괄호 뒤 마침표 없이 바로 이어짐", hints("김성원(2022). 『호텔실무용어집』 백산출판사.", "국문"))
        self.assertIn("쉼표로 구분한 곳이 있음(마침표로 구분)", hints("송재영(2017). 「제목」. 『학술지』, 29(10), 385-403.", "국문"))
        self.assertIn("국외 전자 자료는 '… Retrieved from(URL).' 꼴", hints("Oracle (2024). Title. Report. https://x.y/z", "영문"))


class EntryTests(unittest.TestCase):
    def test_key_and_script(self):
        self.assertEqual(key_of("김성원·노선희(2022). 『책』. 출판사.")["author"], "김성원노선희")
        self.assertEqual(key_of("코틀러([2016] 2019). 『책』. 역자(역). 출판사.")["year"], "2016")
        self.assertEqual(key_of("Kasavana, M. L., & Cahill, J. J. (2003). Title.")["year"], "2003")
        self.assertIsNone(key_of("오페라 PMS. 2024. 8. 12. 스크린 숏."))
        self.assertEqual([script_of(t) for t in ("김철수(2020)", "Smith (2020)", "山田(2020). ホテル経営.", "王明(2020). 酒店管理.")], ["국문", "영문", "일문", "중문"])

    def test_collect_entries_merges_wrapped_lines_and_citations(self):
        body = ["본문", "출처: 집필진 제작(2026)", "출처: 교육부(2021). 객실 예약 관리(LM1203020201_19v2). 한국직업능력연구원. p.20.",
                "참고 자료", "• 김철수(2020). 『호텔 경영론』.", "백산출판사.", "• Smith, J. (2020). Title. NY: Pub.", "", "활용 서식", "서식 1"]
        presence = {"참고 자료": {"있음": True, "k": 3}}
        entries = collect_entries(body, presence)
        self.assertEqual([(e["n"], e["text"], e["script"]) for e in entries],
                         [(1, "김철수(2020). 『호텔 경영론』. 백산출판사.", "국문"), (2, "Smith, J. (2020). Title. NY: Pub.", "영문")])
        citations = collect_citations(body, 3)
        self.assertEqual([(c["literature"], c["lm_code"]) for c in citations], [(False, None), (True, "LM1203020201_19v2")])

    def test_bullet_operator_and_old_8_digit_code(self):
        """실데이터(SW제품기획 최종본): 글머리가 ∙(U+2219), 옛 판본 코드는 8자리(LM20010410_14v2)."""
        body = ["출처: 교육부(2015). SW제품 마케팅 계획 수립(LM20010410_14v2). 한국직업능력개발원. p.25.",
                "참고 자료", "∙교육부(2015). SW제품 마케팅 계획 수립(LM20010410_14v2). 한국직업능력개발원.",
                "∙권금택(2014). 『전략적 고객 관계 관리』. 피앤씨미디어.", "● Smith, J. (2020). Title. NY: Pub."]
        entries = collect_entries(body, {"참고 자료": {"있음": True, "k": 1}})
        self.assertEqual([(e["text"][:9], e["key"]["author"], e["script"]) for e in entries],
                         [("교육부(2015)", "교육부", "국문"), ("권금택(2014)", "권금택", "국문"), ("Smith, J.", "smithj.", "영문")])
        [cite] = collect_citations(body, 1)
        self.assertEqual(cite["lm_code"], "LM20010410_14v2")
        self.assertEqual(check_coverage(entries, [cite])[0]["판정"], "적합")



def entry(n, text):
    return {"n": n, "idx": n, "raw": "• " + text, "text": text, "key": key_of(text), "script": script_of(text),
            "translated": text.count("([") > 0}


def citation(text, literature=True):
    import re
    code = re.search(r"LM\d{10}_\d{2}v\d+", text)
    return {"idx": 0, "text": text, "key": key_of(text), "literature": literature, "lm_code": code.group() if code else None}


class RuleTests(unittest.TestCase):
    def test_coverage(self):
        entries = [entry(1, "교육부(2021). 객실 예약 관리(LM1203020201_19v2). 한국직업능력연구원."), entry(2, "김철수·이영희·박순희·홍길동(2022). 『책』. 출판사.")]
        cites = [citation("교육부(2021). 객실 예약 관리(LM1203020201_19v2). 한국직업능력연구원. p.20."),
                 citation("김철수·이영희·박순희 외(2022). 『책』. 출판사. p.3."),   # 3인 외 ↔ 전원: 앞부분 일치
                 citation("집필진 제작(2026)", literature=False)]
        [row] = check_coverage(entries, cites)
        self.assertEqual(row["판정"], "적합", row["비고"])
        [row] = check_coverage(entries, cites + [citation("이몽룡(2019). 『다른 책』. 출판사. p.1.")])
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("이몽룡(2019)", row["비고"]["① 본문 인용 문헌의 참고 자료 수록"])
        self.assertEqual(check_coverage([], cites)[0]["판정"], "부적합")
        self.assertEqual(check_coverage(entries, [citation("집필진 제작(2026)", literature=False)])[0]["체크"], {"① 본문 인용 문헌의 참고 자료 수록": "-"})

    def test_format_rows(self):
        entries = [entry(1, "김철수(2020). 『호텔 경영론』. 백산출판사."), entry(2, "김민선 (2025). 『책』. 출판사."),
                   entry(3, "교육부(2015). 객실 예약 관리(LM1203020201_24v3). 한국직업능력개발원.")]
        rows = check_format(entries, [])
        self.assertEqual([r["판정"] for r in rows], ["적합", "부적합", "판단불가"])
        self.assertEqual(rows[1]["위치"], "2번")
        self.assertEqual(rows[0]["체크"]["② 본문 출처 기재(참고)"], "-")
        self.assertEqual(rows[2]["체크"]["② 기관명"], "△")

    def test_order(self):
        ok = [entry(1, "김철수(2020). 『책』. 출판사."), entry(2, "이영희(2019a). 『책』. 출판사."), entry(3, "이영희(2019b). 『책』. 출판사."),
              entry(4, "코틀러([2016] 2019). 『번역서』. 역자(역). 출판사."), entry(5, "Adams, J. (2020). Title. NY: Pub."), entry(6, "Brown, K. (2018). Title. NY: Pub.")]
        [row] = check_order(ok)
        self.assertEqual(row["판정"], "적합", row["비고"])
        self.assertEqual(row["원고"], {"국문": 3, "국문 번역": 1, "영문": 2})
        bad = [entry(1, "Adams, J. (2020). Title. NY: Pub."), entry(2, "이영희(2019). 『책』. 출판사."), entry(3, "김철수(2020). 『책』. 출판사."),
               entry(4, "이영희(2019). 『다른 책』. 출판사.")]
        [row] = check_order(bad)
        note = row["비고"]["③ 나열 순서"]
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("2번(국문)이 1번(영문) 뒤에 옴", note)
        self.assertIn("가나다순", note)
        self.assertIn("a/b/c", note)


if __name__ == "__main__":
    unittest.main()
