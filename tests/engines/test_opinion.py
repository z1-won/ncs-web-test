"""검토의견서 반영 여부 검토(REQ-02-003, ncs_opinion) — 의견서 읽기(PDF 줄·hwp 표), 의견 유형·핵심어, 판정 후보, LLM 2차 판정, 오차율.

실물 의견서·원고는 저장소에 없으므로 PDF 추출 결과를 흉내 낸 줄 목록, 표 dict, 합성 원고 문단으로 검사한다.
"""

import tempfile
import unittest
from pathlib import Path

from ncs_opinion import error_rate, review
from ncs_opinion.config import CHECK, KIND_FIGURE, KIND_FORM, KIND_NONE, KIND_TERM, NO_ACTION, NOT_REFLECTED, REFLECTED
from ncs_opinion.judge import judge
from ncs_opinion.keys import read_opinion
from ncs_opinion.llm_check import refine
from ncs_opinion.regions import find, map_manuscript, ref_region
from ncs_opinion.sheet import Opinion, flipped, parse_lines, parse_tables, split_bullets

# 실물 2차 의견서 PDF(한글 → PDF)를 ncs_core.pdf로 읽은 모양을 줄여 흉내 낸 것: 칸 글이 같은 높이면 한 줄로 붙고,
# 구분·쪽 칸 글은 칸 가운데에 끼며, 쪽 숫자가 의견 줄 머리에 붙기도 한다('527701(…)').
PDF_LINES = [
    "2차 검토 완성본 검토의견서",
    "세분류명 SW제품기획",
    "검토진 홍길동 (인)",
    "학습모듈명 SW제품 판매 계획 수립",
    "구분 쪽수 검토의견",
    "-기본 용어는 적절하나, SaaS, 구독 모델, 클라우드 마켓",
    "학습모듈 개요",
    "1플레이스 같은 최신 용어가 추가되면 보완될 것으로 생",
    "(선수학습, 내용체계)",
    "각됨",
    "-<표1-3>에는 클라우드 보안 인증(CSAP) 추가하면 내",
    "4",
    "용 보완 가능",
    "-<표1-4>에는 ISO/IEC 27017(클라우드 보안),",
    "527701(Privacy) 등 신설 국제표준 추가하면 내용 보완 가능",
    "필요지식",
    "학습1",
    "수행 내용 - -",
    "교수･학습 방법 - -",
    "평가 - -",
    "-한국소프트웨어산업협회는 한국인공지능·소프트웨어산업",
    "31",
    "협회로 명칭 변경됨",
    "수행 내용43",
    "-[그림 2-1] 순손실 구간 표시를 명확하게 하면 좋을 것 같음",
    "학습2",
    "평가 - -의견없음",
    "필요지식 67 -<표 4-1>디지털서비스이용지원시스템 내용 추가 필요",
    "학습4",
    "기타 - -",
    "※ 학습이 추가될 경우 셀을 추가해주세요.",
    "종합 의견",
    "-초고본 검토의견의 반영이되어 학습모듈 내용이 보완되었음",
    "※ 형식적 측면보다 내용적 측면을 구체적으로 작성해주시기 바랍니다.",
]

MANUSCRIPT = [
    ["NCS학습모듈의 이해", "1-1. 촬영 구성안 검토와 수정", "CSAP 예시 글(양식 예시라 찾지 않음)"],
    ["차 례", "학습모듈의 개요 1", "1-1. 제품 기능 도출 및 국내외 인증 조사 3", "학습모듈의 개요", "핵심 용어", "SaaS, 구독 판매",
     "1-1.", "제품 기능 도출 및 국내외 인증 조사", "필요 지식",
     "<표 1-3> SW제품 관련 국내 인증", "구분", "근거 법령", "GS인증", "소프트웨어 진흥법", "보안기능 확인서", "CSAP 인증",
     "<표 1-4> 국제 인증", "ISO/IEC 27017", "수행 내용", "[그림 1-1] 제품 기능 명세 매칭 다이어그램",
     "2-1.", "개발비용 도출", "필요 지식", "SW 기술자 평균임금은 매년 한국인공지능·소프트웨어산업협회에서 공표한다.",
     "<표 2-3> 라이선스 정책 종류", "구독형 라이선스", "수행 내용", "[그림 2-1] 손익분기점 그래프",
     "4-1.", "판매 및 유통 시스템 구축 전략 수립", "필요 지식", "<표 4-1> 공공조달 판매 방식", "조달청 디지털 서비스몰",
     "학습 4", "교수⋅학습 방법", "평 가", "국내 자료", "∙SP인증관리포털(http://www.sp-info.or.kr/)에서 검색."],
]


def opinion(text, group="학습 1", lesson=1, part="필요 지식", page="4"):
    return Opinion("2차", "의견서.pdf", group, lesson, part, page, text)


class SheetTests(unittest.TestCase):
    def setUp(self):
        self.sheet = parse_lines(PDF_LINES, "의견서.pdf")
        self.items = {o.text[:12]: o for o in self.sheet.opinions}

    def test_head_and_counts(self):
        self.assertEqual(self.sheet.round, "2차")
        self.assertEqual(self.sheet.module_name, "SW제품 판매 계획 수립")
        texts = [o.text for o in self.sheet.opinions]
        self.assertEqual(len(texts), 7, texts)                 # '- -', '의견없음'은 의견이 아니다
        self.assertFalse(any("홍길동" in t for t in texts))

    def test_wrapped_lines_are_joined_and_glued_page_is_split(self):
        first = self.sheet.opinions[0]
        self.assertIn("클라우드 마켓플레이스 같은 최신 용어가", first.text)   # '마켓' + '1플레이스' → 쪽 1 + 이어 붙임
        self.assertEqual((first.group, first.page), ("학습모듈 개요", "1"))
        iso = next(o for o in self.sheet.opinions if o.text.startswith("<표1-4>"))
        self.assertIn("27701(Privacy)", iso.text)
        self.assertEqual(iso.page, "5")

    def test_part_lesson_and_page_from_centered_labels(self):
        csap = next(o for o in self.sheet.opinions if "CSAP" in o.text)
        self.assertEqual((csap.lesson, csap.part, csap.page), (1, "필요 지식", "4"))
        self.assertIn("구성: 표 위치로 추정", csap.notes)
        overview_ref = parse_lines(["구분 쪽수 검토의견", "학습모듈 개요", "-<표 2-3>에 사례 추가 필요", "※ 학습이 추가될"], "x.pdf")
        self.assertEqual(overview_ref.opinions[0].group, "학습 2")                 # 개요 칸에 붙었어도 표 번호로 학습을 정한다
        self.assertIn("학습 번호: <표 2-3>의 번호로 정함", overview_ref.opinions[0].notes)
        term = next(o for o in self.sheet.opinions if "명칭 변경" in o.text)
        self.assertEqual((term.group, term.part, term.page), ("학습 2", "수행 내용", "31"))  # '- -'로 끝난 칸에는 붙이지 않는다
        figure = next(o for o in self.sheet.opinions if "[그림 2-1]" in o.text)
        self.assertEqual((figure.part, figure.page), ("수행 내용", "43"))
        table = next(o for o in self.sheet.opinions if "<표 4-1>" in o.text)
        self.assertEqual((table.group, table.part, table.page), ("학습 4", "필요 지식", "67"))

    def test_summary_opinion(self):
        summary = [o for o in self.sheet.opinions if o.group == "종합 의견"]
        self.assertEqual(len(summary), 1)
        self.assertTrue(summary[0].text.startswith("초고본 검토의견"))

    def test_flipped_page_order(self):
        self.assertFalse(flipped(PDF_LINES))
        self.assertTrue(flipped(list(reversed(PDF_LINES))))

    def test_no_table_is_error(self):
        with self.assertRaises(ValueError):
            parse_lines(["아무 글"], "메모.pdf")

    def test_hwp_tables_with_round_change_and_page_lists(self):
        def table(rows):
            return {"cells": {(r, c): text for r, row in enumerate(rows) for c, text in enumerate(row)}}

        tables = [
            table([["1차 검토", "개발계획서 및 초고본 검토의견서"], ["학습모듈명", "SW제품 시장성 분석"], ["개발계획서", "검토의견"],
                   ["- 수행준거가 잘 준용되어 있음. - 학습명 종결 수정 필요"], ["※ 학습 구성 …"], ["구분", "쪽수", "검토의견"],
                   ["학습 1-1", "필요지식", "5 9", "- <표 1-3> 보안기능 확인서 추가 필요 - 출처 없음"], ["", "수행 내용", "-", "없음"]]),
            table([["학습1", "교수･학습 방법", "23", "- 적합하게 작성되어 있음을 확인함."], ["기타", "", "", "- 참고자료 최신화 필요"],
                   ["종합 의견"], ["- 전체적으로 잘 작성되어 있음"],
                   ["2차 검토", "완성본 검토의견서"], ["구분", "쪽수", "검토의견"], ["학습 2-1", "수행 내용", "31-32", "- 표 2-2 오타 수정 필요"]]),
        ]
        sheet = parse_tables(tables, "의견서.hwp")
        rows = [(o.round, o.group, o.part, o.page, o.text) for o in sheet.opinions]
        self.assertIn(("1차", "개발계획서", None, None, "학습명 종결 수정 필요"), rows)
        self.assertIn(("1차", "학습 1", "필요 지식", "5,9", "<표 1-3> 보안기능 확인서 추가 필요"), rows)
        self.assertIn(("1차", "학습 1", "교수·학습 방법", "23", "적합하게 작성되어 있음을 확인함."), rows)
        self.assertIn(("1차", "기타", None, None, "참고자료 최신화 필요"), rows)
        self.assertIn(("1차", "종합 의견", None, None, "전체적으로 잘 작성되어 있음"), rows)
        self.assertIn(("2차", "학습 2", "수행 내용", "31-32", "표 2-2 오타 수정 필요"), rows)
        self.assertFalse(any(text == "없음" for *_, text in rows))
        self.assertEqual(sheet.module_name, "SW제품 시장성 분석")

    def test_split_bullets_keeps_hyphen_words(self):
        self.assertEqual(split_bullets("- 교수-학습 방법이 적합함. - 표 1-3 수정 필요 -> 반영"),
                         ["교수-학습 방법이 적합함.", "표 1-3 수정 필요 -> 반영"])


class ReadingTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(read_opinion("평가 항목이 작성 가이드에 준하여 작성되어 있음을 확인함.").kind, KIND_NONE)
        self.assertEqual(read_opinion("SW 제품 기획 조직 분석에 필요한 필요 지식이 학습 목표에 부합되는 내용들로 구성되어 있음.").kind, KIND_NONE)
        self.assertEqual(read_opinion("제목 가운데 정렬 필요").kind, KIND_FORM)
        self.assertEqual(read_opinion("[그림 1-6]인증 프로세스 확인 실습 사진은 해당 내용을 표현하지 못한다고 생각됨").kind, KIND_FIGURE)

    def test_term_changes(self):
        reading = read_opinion("한국소프트웨어산업협회는 한국인공지능·소프트웨어산업협회로 명칭 변경됨")
        self.assertEqual((reading.kind, reading.old_terms, reading.new_terms),
                         (KIND_TERM, ["한국소프트웨어산업협회"], ["한국인공지능·소프트웨어산업협회"]))
        quoted = read_opinion("표 5-2의 구분에서 '재무적','정성적' 표현을 '정량적','정성적'으로 수정할 것을 권고함.")
        self.assertEqual((quoted.kind, quoted.old_terms, quoted.new_terms), (KIND_TERM, ["재무적"], ["정량적"]))
        arrow = read_opinion("<표 3-6> 명칭변경(SW기술자 노임대가 ⇒ SW기술자 평균임금) 개선 필요")
        self.assertEqual(arrow.kind, KIND_TERM)
        self.assertIn("SW기술자 평균임금", arrow.new_terms)
        law = read_opinion("<표 1-3> GS인증의 근거법령도 소프트웨어 진흥법으로 개정됨")
        self.assertEqual((law.kind, law.new_terms, [r.label for r in law.refs]), (KIND_TERM, ["소프트웨어 진흥법"], ["<표 1-3>"]))

    def test_add_keys(self):
        self.assertEqual(read_opinion("<표1-3>에는 클라우드 보안 인증(CSAP) 추가하면 내용 보완 가능").keys, ["CSAP"])
        oss = read_opinion("공개 여부 보완: 오픈소스 라이선스(GPL, MIT, Apache 등)도 중요한 학습 요소로 포함될 필요 있음")
        self.assertTrue({"GPL", "MIT", "Apache"} <= set(oss.keys), oss.keys)
        self.assertIn("디지털서비스이용지원시스템", read_opinion("<표 4-1>디지털서비스이용지원시스템 내용 추가 필요").keys)
        self.assertIn("구독형 라이선스", read_opinion("<표 2-4> 구독형 라이선스 등 최신 트렌드 반영되면 좋을 것 같음").keys)
        self.assertIn("sp-info.or.kr", read_opinion("참고자료 최신화가 필요해 보임 예시) http://www.sp-info.or.kr/ 존재").keys)

    def test_sentence_change(self):
        reading = read_opinion('학습목표가 불일치함. "분석된 경영 전략에 맞는 기술 동향을 파악할 수 있다." -> '
                               '"SW제품 기슬 추세와 조직의 비즈니스 전략의 적정성을 판단할 수 있다." 로 수정이 필요함.')
        self.assertEqual(reading.sentences, ["SW제품 기슬 추세와 조직의 비즈니스 전략의 적정성을 판단할 수 있다."])


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.ms = map_manuscript("원고.hwpx", MANUSCRIPT)

    def run_judge(self, text, **kwargs):
        op = opinion(text, **kwargs)
        return judge(op, read_opinion(op.text), self.ms)

    def test_manuscript_map(self):
        self.assertFalse(any("양식 예시" in p.text for p in self.ms.paras))     # 차례 앞은 찾지 않는다
        where = {p.text: p.where for p in self.ms.paras}
        self.assertEqual(where["핵심 용어"], "학습모듈 개요")
        self.assertEqual(where["CSAP 인증"], "학습 1 필요 지식")
        self.assertEqual(where["[그림 2-1] 손익분기점 그래프"], "학습 2 수행 내용")
        self.assertEqual(where["∙SP인증관리포털(http://www.sp-info.or.kr/)에서 검색."], "기타")
        region = [self.ms.paras[i].text for i in ref_region(self.ms, read_opinion("<표 1-3> 수정 필요").refs[0])]
        self.assertEqual(region[0], "<표 1-3> SW제품 관련 국내 인증")
        self.assertNotIn("ISO/IEC 27017", region)                                # 다음 캡션 앞까지

    def test_find_multiword_and_fuzzy(self):
        self.assertTrue(find(self.ms, "조달청 디지털서비스몰"))
        self.assertTrue(find(self.ms, "구독형 라이선스"))
        long_ms = map_manuscript("원고", [["차 례", "•SW제품 기술 추세와 조직의 비즈니스 전략의 적정성을 판별할 수 있다."]])
        self.assertTrue(find(long_ms, "SW제품 기슬 추세와 조직의 비즈니스 전략의 적정성을 판단할 수 있다."))

    def test_reflected_candidate_with_evidence(self):
        row = self.run_judge("<표 1-3> 추가내용으로 보안기능 확인서도 추가되면 좋을 것으로 생각됨")
        self.assertEqual(row["판정"], REFLECTED)
        self.assertEqual(row["근거"][0]["문단"], "보안기능 확인서")
        self.assertEqual(row["찾은 범위"], "<표 1-3> 캡션 주변")

    def test_not_reflected_candidate(self):
        row = self.run_judge("<표 1-3>에 원격 접속 인증도 추가 필요")
        self.assertEqual(row["판정"], NOT_REFLECTED)
        self.assertTrue(row["수정 제안"])

    def test_partial_or_elsewhere_is_check(self):
        row = self.run_judge("오픈소스 라이선스(GPL, MIT, Apache 등)도 포함될 필요 있음", lesson=2, page="39")
        self.assertEqual(row["판정"], NOT_REFLECTED)            # 셋 다 원고에 없음
        row = self.run_judge("<표 1-4>에는 ISO/IEC 27017, ISO/IEC 42001 등 추가하면 내용 보완 가능")
        self.assertEqual(row["판정"], CHECK)                    # 하나만 있음
        self.assertIn("원고에서 찾지 못함: ISO/IEC 42001", row["비고"])

    def test_term_change_is_always_check_with_question(self):
        row = self.run_judge("한국소프트웨어산업협회는 한국인공지능·소프트웨어산업협회로 명칭 변경됨", lesson=2, part="수행 내용")
        self.assertEqual(row["판정"], CHECK)
        self.assertIn("집필자", " ".join(row["비고"]))
        self.assertIn("한국인공지능·소프트웨어산업협회", row["집필자 확인"])
        self.assertIn("옛 용어 '한국소프트웨어산업협회' 0곳", " ".join(row["비고"]))

    def test_form_figure_plan_summary_are_check(self):
        self.assertEqual(self.run_judge("제목 가운데 정렬 필요")["판정"], CHECK)
        figure = self.run_judge("[그림 2-1] 순손실 구간 표시를 명확하게 하면 좋을 것 같음", lesson=2, part="수행 내용")
        self.assertEqual(figure["판정"], CHECK)
        self.assertEqual(figure["근거"][0]["문단"], "[그림 2-1] 손익분기점 그래프")
        missing = self.run_judge("[그림 1-6] 실습 사진은 해당 내용을 표현하지 못한다고 생각됨")
        self.assertIn("원고에 [그림 1-6] 캡션이 없음 — 번호가 바뀌었거나 빠졌을 수 있음", missing["비고"])
        plan = self.run_judge("4.2항의 리셀러 선정 기준 명시가 필요함", group="개발계획서", lesson=None, part=None, page=None)
        self.assertEqual(plan["판정"], CHECK)
        summary = self.run_judge("CSAP 인증 내용이 보완되면 좋을 것으로 생각됨", group="종합 의견", lesson=None, part=None, page=None)
        self.assertEqual((summary["판정"], summary["찾은 범위"]), (CHECK, "원고 전체"))

    def test_no_action(self):
        self.assertEqual(self.run_judge("평가 항목이 작성 가이드에 준하여 작성되어 있음을 확인함.")["판정"], NO_ACTION)

    def test_previous_manuscript_downgrades_unchanged_text(self):
        op = opinion("<표 1-3> 추가내용으로 보안기능 확인서도 추가되면 좋을 것으로 생각됨")
        row = judge(op, read_opinion(op.text), self.ms, previous=self.ms)
        self.assertEqual(row["판정"], CHECK)
        self.assertIn("반영 전 원고에도", " ".join(row["비고"]))


class LlmTests(unittest.TestCase):
    def setUp(self):
        self.ms = map_manuscript("원고.hwpx", MANUSCRIPT)
        self.op = opinion("<표 1-3>에 원격 접속 인증도 추가 필요")
        self.reading = read_opinion(self.op.text)

    def row(self):
        return judge(self.op, self.reading, self.ms)

    def test_llm_reflected_needs_real_evidence_line(self):
        def asker(lines, user):
            self.assertIn("[의견]", user)
            n = lines.index("CSAP 인증") + 1
            return {"data": {"판정": "반영", "근거_줄": [n, 999], "근거_문장": "CSAP 인증", "이유": "인증 행이 있음"}, "model": "가짜"}

        row = refine(self.row(), self.op, self.reading, self.ms, asker=asker)
        self.assertEqual(row["판정"], CHECK)       # 규칙(미반영 후보)과 엇갈리면 확인 필요
        self.assertEqual([e["문단"] for e in row["LLM"]["근거"]], ["CSAP 인증"])   # 없는 줄 999는 버린다

    def test_llm_hallucinated_quote_is_not_used(self):
        def asker(lines, user):
            return {"data": {"판정": "반영", "근거_줄": [1], "근거_문장": "원고에 없는 문장"}, "model": "가짜"}

        op = opinion("<표 1-3>에 원격 접속 인증도 추가 필요")
        row = judge(op, self.reading, self.ms)
        row["판정"] = CHECK
        row = refine(row, op, self.reading, self.ms, asker=asker)
        self.assertEqual(row["판정"], CHECK)
        self.assertIn("근거 줄을 대지 못해", row["LLM"]["알림"])

    def test_llm_not_reflected_gives_sentence(self):
        def asker(lines, user):
            return {"data": {"판정": "미반영", "근거_줄": [], "수정_문장": "원격 접속 인증은 … 제도이다."}, "model": "가짜"}

        row = refine(self.row(), self.op, self.reading, self.ms, asker=asker)
        self.assertEqual((row["판정"], row["수정 제안"]), (NOT_REFLECTED, "원격 접속 인증은 … 제도이다."))

    def test_without_settings_rules_stay(self):
        row = refine(self.row(), self.op, self.reading, self.ms)   # 키·승인·허용 목록 없음 → LlmError
        self.assertEqual(row["판정"], NOT_REFLECTED)
        self.assertTrue(row["LLM"]["상태"].startswith("LLM 미사용"))


class PipelineTests(unittest.TestCase):
    def test_review_hwpx_files_and_error_rate(self):
        import make_fixtures as mf

        with tempfile.TemporaryDirectory() as folder:
            final, sheet = Path(folder) / "최종_LM2001010409_19v4.hwpx", Path(folder) / "2차_의견서.hwpx"
            mf.write_hwpx(final, [[mf.p(t) for t in MANUSCRIPT[1]]])
            rows = [["2차 검토", "완성본 검토의견서", "", ""], ["학습모듈명", "SW제품 판매 계획 수립", "", ""],
                    ["구분", "쪽수", "검토의견", ""],
                    ["학습 1-1", "필요지식", "4", "- <표 1-3> 보안기능 확인서도 추가되면 좋을 것 - <표 1-3>에 원격 접속 인증도 추가 필요"],
                    ["", "수행 내용", "17", "- 한국소프트웨어산업협회는 한국인공지능·소프트웨어산업협회로 명칭 변경됨"],
                    ["기타", "", "-", "- 의견없음"], ["종합 의견", "", "", ""], ["- 적절하게 작성되어 있음", "", "", ""]]
            mf.write_hwpx(sheet, [[mf.table(rows)]])
            result = review([sheet, sheet], final, use_llm=True)
        self.assertEqual(result["요약"], {"총 의견": 4, "조치 요구": 3, "반영 후보": 1, "미반영 후보": 1, "확인 필요": 1,
                                         "조치 불필요": 1, "용어 변경(집필자 확인)": 1})        # 같은 파일 두 번 → 한 번만
        self.assertIn("ALLOWED_TASKS", result["LLM"])
        verdicts = [r["판정"] for r in result["의견"]]
        self.assertEqual(verdicts, [REFLECTED, NOT_REFLECTED, CHECK, NO_ACTION])
        rate = error_rate(result["의견"], {1: "반영", 2: "반영", 3: "미반영"})
        self.assertEqual((rate["판정 수"], rate["틀림"], rate["보류(확인 필요)"], rate["오차율"], rate["결과"]), (2, 1, 1, "50.0%", "미달"))
        self.assertEqual(error_rate(result["의견"], {})["결과"], "판단불가")

    def test_no_opinions_is_error(self):
        with self.assertRaises(ValueError):
            review([], "원고.hwpx")


if __name__ == "__main__":
    unittest.main()
