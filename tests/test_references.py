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

    def test_hints_name_the_real_problem(self):
        """테스트 데이터 원본 참고 자료 3~9번: 판정(X)은 맞지만 이유가 엉뚱했다 — URL 괄호·코드 괄호를 제목 괄호로 보고, 있는 날짜를 없다고 함."""
        no_site = "국가과학기술정보센터(2026).(https://scienceon.kisti.re.kr/main/mainForm.do?v=2)에서 2026. 8. 2. AIoT 검색."
        why = hints(no_site, "국문")
        self.assertNotIn("제목 괄호 뒤 마침표 없이 바로 이어짐", why)
        self.assertNotIn("URL이 있는데 검색 연월일(YYYY. MM. DD. 검색.)이 없음", why)
        self.assertIn("연도 뒤에 자료명·홈페이지명 없이 바로 (URL)이 옴 — '자료명(연도). 홈페이지명(URL)에서 …'", why)
        self.assertIn("검색 연월일(2026. 8. 2.)과 '검색' 사이에 「AIoT」이(가) 있음 — 'YYYY. MM. DD. 검색.' 꼴", why)
        self.assertIsNone(match_template(no_site, "국문"))  # 판정은 그대로 X
        spaced = "한국인터넷진흥원(2026). (https://www.kisa.or.kr/201)에서 2026. 8. 6. AIoT 검색."
        self.assertIn("연도 뒤에 자료명·홈페이지명 없이 바로 (URL)이 옴 — '자료명(연도). 홈페이지명(URL)에서 …'", hints(spaced, "국문"))
        code = "한국산업인력공단. NCS 정보통신 분야 AIoT 운영 플랫폼 구축(2001020417_20v1) 능력단위 정의서 및 학습모듈."
        self.assertEqual(hints(code, "국문"), ["연도 괄호 (YYYY) 없음"])
        self.assertEqual(hints("정보통신산업진흥원(https://www.nipa.kr).", "국문"),
                         ["연도 괄호 (YYYY) 없음", "URL이 있는데 검색 연월일(YYYY. MM. DD. 검색.)이 없음"])
        self.assertIn("검색 연월일 뒤에 '검색.'이 없음 — 'YYYY. MM. DD. 검색.' 꼴",
                      hints("자료(2020). 홈페이지(https://a.kr)에서 2020. 1. 2.", "국문"))
        # 바른 전자 자료는 이유가 없다(양식에 맞음)
        ok = "AIoT 안내(2026). 국가과학기술정보센터(https://scienceon.kisti.re.kr)에서 2026. 8. 2. 검색."
        self.assertIsNotNone(match_template(ok, "국문"))

    def test_hints_by_source_type(self):
        """최종본 10종에서 이유 없이 '골격이 다름'만 나오던 28건 — 유형별로 빠진 부분을 적는다(문장은 실제 원고)."""
        cases = {
            "행정안전부(2011). 과학적 조직 관리를 위한 조직 진단 매뉴얼.":
                "제목 뒤 발행 기관 없음 — 보고서·자료집은 '저자(연도). 제목. 발행 기관.'",
            "박상완(2012). 「특허 맵 활용을 통한 특허 기술의 사업화 전략」. 『POSRI 경영 경제 연구』.12권(2호).":
                "학술지 논문의 쪽수 없음 — '「제목」. 『학술지명』. 권(호). 쪽수.'",
            "이후재, 김두연, 최일우(2012). 「정량적인 OSS 선정을 위한 평가 지표 연구」. 『한국산학기술학회』.13권(4호).":
                "국문 공동 저자는 쉼표가 아니라 가운뎃점(·)으로 잇는다",
            "조달청(2024). 『공공정보화 사업유형별 제안요청서 작성 가이드』.": "책명 뒤 출판사 없음 — '저자(연도). 『책명』. 출판사.'",
            "스콧웨스트․미치 앤서니(김선호 역)(2012). 『평생 고객을 얻는 최고의 질문』. 에프피북스.":
                "번역서 꼴은 '저자([원서 연도] 번역 연도). 『번역서명(원서명)』. 번역자(역). 출판사.' — 역자는 저자 뒤가 아니라 책명 뒤",
            "정보통신산업진흥원(2021. 1). 공공SW사업 제안요청서 작성을 위한 요구사항 가이드.": "연도 괄호에 월까지 적음 — 연도만 '(YYYY)'",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIsNone(match_template(text, "국문"))  # 판정은 그대로 X
                self.assertIn(expected, hints(text, "국문"))
        self.assertIn("학술지 권·호는 숫자만 '12(2).' 꼴(권·호 글자 없이)", hints(next(iter(k for k in cases if "POSRI" in k)), "국문"))
        iso = hints("ISO(2001). ISO/IEC 9126-1.", "영문")
        self.assertEqual(iso, ["국외 자료는 저자와 연도 괄호 사이를 띄움 — '저자 (연도).'", "제목 뒤 발행처·출판사 없음"])
        # 연도 괄호가 없으면 URL 괄호를 연도 괄호로 보지 않는다
        self.assertNotIn("국외 자료는 저자와 연도 괄호 사이를 띄움 — '저자 (연도).'",
                         hints("A.M.Davis. A.M.Davis Inc(https://www.amdavislift.com/)에서 2025. 06. 06 검색.", "영문"))
        # 아는 위반에 안 맞아도 이유 칸은 비지 않는다
        self.assertTrue(hints("알 수 없는 꼴의 자료", "국문"))


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

    def test_guessed_region_extends_upward_and_skips_subheads(self):
        """제목이 이미지라 구역을 참고문헌 꼴 줄로 추정하면, 연도 표기가 다른 줄에서 끊겨 끝부분만 잡힌다(SW제품기획 0405)."""
        body = ["- 시험 점수가 낮은 학습자에게는 설명해 준다.", "", "국내 자료", "∙교육부(2015). SW제품 사양 정의(LM2001010405_14v2). 한국직업능력개발원.",
                "∙정보통신산업진흥원(2021. 1). 요구사항 가이드.", "", "국외 자료", "∙A.M.Davis. 「Software Requirements」, Prentice Hall.",
                "∙ISO(2001). ISO/IEC 9126-1.", "∙ISO(2011). ISO/IEC 25010."]
        presence = {"참고 자료": {"있음": True, "k": 8, "end": 9, "근거": "참고문헌 꼴 줄 2개 연속 — 제목은 텍스트가 아님(이미지일 가능성)"}}
        entries = collect_entries(body, presence)
        self.assertEqual([e["text"][:9] for e in entries], ["교육부(2015)", "정보통신산업진흥원", "A.M.Davis", "ISO(2001)", "ISO(2011)"])
        # 제목이 텍스트로 있으면(추정 아님) 넓히지 않는다
        self.assertEqual(len(collect_entries(body, {"참고 자료": {"있음": True, "k": 8, "end": 9}})), 2)
        # 피드백을 '•'로 쓴 원고: 서지 단서(연도·「」·URL·발행처) 없는 '•' 줄은 끌어오지 않는다
        body = ["• 평가자 체크리스트", "• 구두 발표", "∙ISO(2001). ISO/IEC 9126-1.", "∙ISO(2011). ISO/IEC 25010."]
        presence = {"참고 자료": {"있음": True, "k": 2, "end": 3, "근거": "참고문헌 꼴 줄 2개 연속 — 제목은 텍스트가 아님(이미지일 가능성)"}}
        self.assertEqual([e["text"][:9] for e in collect_entries(body, presence)], ["ISO(2001)", "ISO(2011)"])

    def test_latin_led_korean_source(self):
        """'AIoT 기술 가이드라인…'은 영문으로 시작하는 국문 자료 — 첫 글자대로 영문 목록(알파벳순)에 있어야 적합(완화 없음)."""
        text = "AIoT 기술 가이드라인 및 참조 아키텍처(2025), 한국지능형사물인터넷협회(AIoT Korea)."
        self.assertEqual(script_of(text), "국문")
        self.assertEqual(script_of("AIoT Data and Functional Viewpoint Guide(2026)."), "영문")
        korean = [entry(1, "교육부(2023). 「추진방안」. 교육부."), entry(2, "한국지능정보사회진흥원(2026). 자료.")]
        english = [entry(9, "Al-Fuqaha, A.(2015). Internet of Things.")]
        # 국문 다음·영문 맨 앞(aiot < al-fuqaha, 테스트 데이터 원본의 배치) = 영문 목록 알파벳 자리 → 적합
        [row] = check_order(korean + [entry(3, text)] + english)
        self.assertEqual(row["판정"], "적합", row["비고"])
        self.assertIn("영문 목록", row["비고"]["③ 나열 순서(참고)"])
        # 국문 맨 앞 → X (예전에는 세 배치 중 하나라 적합이었음)
        self.assertEqual(check_order([entry(3, text)] + korean + english)[0]["판정"], "부적합")
        # 영문 목록 안이지만 알파벳 자리가 아님(al-fuqaha 뒤) → X
        self.assertEqual(check_order(korean + english + [entry(3, text)])[0]["판정"], "부적합")
        # 국문 한가운데 → X
        self.assertEqual(check_order([korean[0], entry(3, text), korean[1]] + english)[0]["판정"], "부적합")

    def test_same_author_without_year_compares_author_only(self):
        """연도 없는 같은 저자 두 자료: 제목 기호(「)로 순서 위반을 내지 않는다(SW제품기획 0405)."""
        [row] = check_order([entry(1, "A.M.Davis. 「Software Requirements」, Prentice Hall."),
                             entry(2, "A.M.Davis. A.M.Davis Inc(https://www.amdavislift.com/)에서 2025. 06. 06. 검색."),
                             entry(3, "Benjamin L. Kovitz, 「Practical Software Requirements」.")])
        self.assertEqual(row["판정"], "적합", row["비고"])
        [row] = check_order([entry(1, "Kovitz, B. 「Practical」."), entry(2, "Davis, A. 「Software」.")])
        self.assertEqual(row["판정"], "부적합")  # 저자가 다르면 여전히 알파벳순을 본다
        [row] = check_order([entry(1, "Kovitz, B. 「Practical」."), entry(2, "Kovitz, A. 「Software」.")])
        self.assertEqual(row["판정"], "부적합")  # 성이 같아도 이름 이니셜까지 본다(쉼표에서 자르지 않음)


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
