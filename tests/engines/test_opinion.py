"""검토의견서 반영 여부 검토(REQ-02-003, ncs_opinion) — 의견서 읽기(PDF 줄·hwp 표), 원고 범위·보낼 문단 고르기, LLM 답 검증과 판정 정책,
LLM 미설정·실패, 오차율.

실물 의견서·원고는 저장소에 없으므로 PDF 추출 결과를 흉내 낸 줄 목록, 표 dict, 합성 원고 문단으로 검사한다.
LLM은 가짜 Claude(generate — ncs_llmreview.claude.generate_json과 같은 서명)로만 검사한다 — 실제 호출 없음. 테스트 환경은 tests/_env.py가 키를 비우므로 미설정 경로도 검사한다.
"""

import tempfile
import unittest
from pathlib import Path

from ncs_llmreview.claude import ClaudeError
from ncs_opinion import error_rate, review
from ncs_opinion.config import (CHECK, KIND_CONTENT, KIND_TERM, KIND_UNKNOWN, NO_ACTION, NO_PLACE, NOT_REFLECTED, REFLECTED, WHOLE,
                                OpinionConfig)
from ncs_opinion.judge import invented, judge
from ncs_opinion.keys import refs_of
from ncs_opinion.llm_check import _ranges, ask_all, build_prompt, build_request, build_system, out_schema, parse_answer
from ncs_opinion.regions import find, locate, map_manuscript, pick_paragraphs, ref_region
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

    def test_round_mark_in_table_wins_over_given_round(self):
        def table(rows):
            return {"cells": {(r, c): text for r, row in enumerate(rows) for c, text in enumerate(row)}}

        inner_first = table([["1차 검토", "초고본 검토의견서"], ["구분", "쪽수", "검토의견"], ["학습 1-1", "필요지식", "4", "- 용어 정의 보완 필요"]])
        second = table([["2차 검토", "완성본 검토의견서"], ["구분", "쪽수", "검토의견"], ["학습 1-1", "수행 내용", "9", "- 사례 추가 필요"]])
        sheet = parse_tables([inner_first, second], "2차_의견서.hwp", "2차")
        self.assertEqual([(o.round, o.text) for o in sheet.opinions], [("1차", "용어 정의 보완 필요"), ("2차", "사례 추가 필요")])
        self.assertEqual(sheet.round, "2차")
        unmarked = table([["구분", "쪽수", "검토의견"], ["기타", "", "", "- 참고자료 최신화 필요"]])
        self.assertEqual([o.round for o in parse_tables([unmarked], "x.hwp", "2차").opinions], ["2차"])   # 표기가 없으면 지정 차수
        self.assertEqual(parse_lines(PDF_LINES, "의견서.pdf", "1차").round, "2차")                         # PDF도 제목 표기가 앞선다
        self.assertEqual(parse_lines(PDF_LINES[4:], "의견서.pdf", "1차").round, "1차")

    def test_split_bullets_keeps_hyphen_words(self):
        self.assertEqual(split_bullets("- 교수-학습 방법이 적합함. - 표 1-3 수정 필요 -> 반영"),
                         ["교수-학습 방법이 적합함.", "표 1-3 수정 필요 -> 반영"])


def answer(no, type_="내용", verdict="반영", evidence=(), **more):
    item = {"no": no, "type": type_, "verdict": verdict, "evidence": list(evidence), "reason": more.pop("reason", "이유"),
            "suggestion": more.pop("suggestion", ""), "old_terms": more.pop("old_terms", []), "new_terms": more.pop("new_terms", [])}
    item.update(more)
    return item


def fake(*items, calls=None):
    """가짜 Claude(generate) — 받은 질문({'system','document','request'})을 calls에 남기고 items를 돌려준다.
    items 자리에 (질문 → 답 목록) 함수 하나를 줘도 된다."""
    def generate(system, document, request, *, task, tasks=None, out_schema=None):
        assert task == "opinion_reflection" and out_schema["required"] == ["opinions"]
        call = {"system": system, "document": document, "request": request}
        if calls is not None:
            calls.append(call)
        found = items[0](call) if items and callable(items[0]) else list(items)
        return {"data": {"opinions": found}, "model": "가짜", "cached": False, "usage": {"input": 1000, "output": 100}}
    return generate


def paragraph_lines(call):
    """원고 블록의 최종 원고 문단 줄들('[n] (위치) 글')."""
    return [line for line in call["document"].split("\n") if line.startswith("[") and not line.startswith(("[이전", "[원고"))]


def number_of(call, text):
    """원고 블록에서 그 글이 든 최종 원고 문단의 번호(1부터)."""
    lines = [line for line in paragraph_lines(call) if text in line]
    return int(lines[0][1:lines[0].index("]")])


class RegionTests(unittest.TestCase):
    def setUp(self):
        self.ms = map_manuscript("원고.hwpx", MANUSCRIPT)

    def test_manuscript_map(self):
        self.assertFalse(any("양식 예시" in p.text for p in self.ms.paras))     # 차례 앞은 찾지 않는다
        where = {p.text: p.where for p in self.ms.paras}
        self.assertEqual(where["핵심 용어"], "학습모듈 개요")
        self.assertEqual(where["CSAP 인증"], "학습 1 필요 지식")
        self.assertEqual(where["[그림 2-1] 손익분기점 그래프"], "학습 2 수행 내용")
        self.assertEqual(where["∙SP인증관리포털(http://www.sp-info.or.kr/)에서 검색."], "기타")
        region = [self.ms.paras[i].text for i in ref_region(self.ms, refs_of("<표 1-3> 수정 필요")[0])]
        self.assertEqual(region[0], "<표 1-3> SW제품 관련 국내 인증")
        self.assertNotIn("ISO/IEC 27017", region)                                # 다음 캡션 앞까지

    def test_locate(self):
        _, where, _, caption = locate(opinion("<표 1-3>에 원격 접속 인증도 추가 필요"), self.ms)
        self.assertEqual((where, self.ms.paras[caption].text), ("<표 1-3> 캡션 주변", "<표 1-3> SW제품 관련 국내 인증"))
        _, where, notes, _ = locate(opinion("[그림 1-6] 실습 사진은 해당 내용을 표현하지 못함"), self.ms)
        self.assertEqual(where, "학습 1 필요 지식 구간")                          # 캡션이 없으면 학습·구성 구간
        self.assertIn("원고에 [그림 1-6] 캡션이 없음 — 번호가 바뀌었거나 빠졌을 수 있음", notes)
        self.assertEqual(locate(opinion("의견", group="종합 의견", lesson=None, part=None), self.ms)[:2], ([], NO_PLACE))
        self.assertEqual(locate(opinion("의견", group="개발계획서", lesson=None, part=None), self.ms)[1], NO_PLACE)
        self.assertEqual(locate(opinion("의견", group="학습 9", lesson=9, part=None), self.ms)[1], WHOLE)

    def test_pick_paragraphs_by_overlap(self):
        config = OpinionConfig(llm_per_opinion=3)
        region = self.ms.everything
        picked = [self.ms.paras[i].text for i in pick_paragraphs("CSAP 인증 내용이 보완되면 좋겠음", self.ms, region, config=config)]
        self.assertIn("CSAP 인증", picked)
        self.assertLess(len(picked), len(region))                                # 원고 전문은 보내지 않는다
        self.assertEqual(pick_paragraphs("아무 의견", self.ms, [1, 2], config=config), [1, 2])   # 범위가 작으면 그대로

    def test_find_counts_terms(self):
        self.assertEqual(len(find(self.ms, "한국인공지능·소프트웨어산업협회")), 1)
        self.assertEqual(find(self.ms, "한국소프트웨어산업협회"), [])
        self.assertEqual(find(self.ms, ""), [])


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.ms = map_manuscript("원고.hwpx", MANUSCRIPT)

    def test_prompt_numbers_paragraphs_once_and_lists_opinions(self):
        ops = [opinion("<표 1-3> 보안기능 확인서도 추가되면 좋을 것"), opinion("<표 1-3>에 원격 접속 인증도 추가 필요"),
               opinion("전체적으로 잘 작성됨", group="종합 의견", lesson=None, part=None)]
        prompt = build_prompt(ops, self.ms, None)
        document = prompt["document"]
        self.assertIn("[1] (학습 1 필요 지식) <표 1-3> SW제품 관련 국내 인증", document)
        self.assertEqual(document.count("보안기능 확인서"), 1)                    # 두 의견이 같은 문단을 봐도 글은 한 번
        self.assertNotIn("반영 전 원고 문단", document)
        self.assertNotIn("ISO/IEC 27017", document)                              # 범위 밖 문단은 보내지 않는다
        self.assertNotIn("원격 접속", document)                                  # 의견 글은 요청 블록에만
        request = build_request(prompt["lines"], [1, 2, 3])
        self.assertIn("의견 번호: 1, 2, 3", request)
        self.assertIn("2. (2차 · 학습 1 · 필요 지식 · 4쪽) [볼 문단: 1-", request)
        self.assertIn("<표 1-3>에 원격 접속 인증도 추가 필요", request)
        self.assertEqual(prompt["볼 문단"][3], [])
        self.assertIn("3. (2차 · 종합 의견 · 4쪽) [볼 문단: 없음 — 가리키는 자리가 없는 의견", request)
        with_before = build_prompt(ops[:1], self.ms, self.ms)
        self.assertIn("[이전 1] (학습 1 필요 지식) <표 1-3> SW제품 관련 국내 인증", with_before["document"])
        self.assertIn("| 반영 전: 이전 1-", build_request(with_before["lines"], [1]))
        self.assertEqual(_ranges([9, 3, 4, 5, 12, 13]), "3-5, 9, 12-13")

    def test_system_and_schema_from_prompt_file(self):
        system = build_system()
        self.assertIn("모든 의견에 대해 빠짐없이 하나씩 답합니다.", system)
        self.assertIn("표현이 달라도", system)
        self.assertIn("의견에 적힌 낱말과 요구만으로", system)
        schema = out_schema()
        item = schema["properties"]["opinions"]["items"]
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(set(item["required"]), set(item["properties"]))   # 구조화 출력: 모든 속성 required

    def test_parse_drops_unknown_numbers_and_bad_values(self):
        data = {"opinions": [answer(1, evidence=[2, 9, 2, 3]), answer(1, verdict="미반영"), answer(5), answer("x"),
                             answer(2, type_="모름", verdict="글쎄", old_terms="옛말")]}
        parsed, dropped = parse_answer(data, {1: [1, 2], 2: [3]}, {1: 10, 2: 11, 3: 12})
        self.assertEqual((sorted(parsed), dropped), ([1, 2], 3))
        # 3은 원고 블록에 있지만 의견 1의 볼 문단이 아니라 버린다
        self.assertEqual((parsed[1]["판정"], parsed[1]["근거"], parsed[1]["버린 근거 번호"]), ("반영", [11], 2))
        self.assertEqual((parsed[2]["유형"], parsed[2]["판정"], parsed[2]["옛 용어"]), ("", "", ["옛말"]))
        self.assertEqual(parse_answer({"opinions": "글"}, {1: []}, {}), ({}, 0))
        self.assertEqual(parse_answer({}, {1: []}, {}), ({}, 0))


class JudgeTests(unittest.TestCase):
    """LLM 답 → 판정 후보(정책과 검증). 가짜 응답만 쓴다."""

    def setUp(self):
        self.ms = map_manuscript("원고.hwpx", MANUSCRIPT)

    def run_one(self, op, reply, previous=None):
        calls = []
        _, where, notes, _ = locate(op, self.ms)
        asker = fake(reply, calls=calls) if callable(reply) else fake(*reply, calls=calls)
        answers, stats = ask_all([(op, where)], self.ms, previous, generate=asker)
        return judge(op, where, notes, answers[0], self.ms, previous=previous), calls, stats

    def test_reflected_needs_valid_evidence(self):
        op = opinion("<표 1-3> 보안기능 확인서도 추가되면 좋을 것")
        row, _, stats = self.run_one(op, lambda p: [answer(1, evidence=[number_of(p, "보안기능 확인서")])])
        self.assertEqual((row["판정"], row["유형"], row["근거"][0]["문단"]), (REFLECTED, KIND_CONTENT, "보안기능 확인서"))
        self.assertEqual((row["LLM"]["모델"], row["LLM"]["판정"]), ("가짜", "반영"))
        self.assertEqual((stats["호출"], stats["물은 의견"]), (1, 1))
        row, _, _ = self.run_one(op, [answer(1, evidence=[99])])                  # 없는 문단 번호 → 근거 없음
        self.assertEqual(row["판정"], CHECK)
        self.assertIn("유효한 근거 문단 번호가 없음", " ".join(row["비고"]))

    def test_not_reflected_keeps_suggestion_unless_invented(self):
        op = opinion("<표 1-3>에 원격 접속 인증도 추가 필요")
        row, _, _ = self.run_one(op, [answer(1, verdict="미반영", suggestion="<표 1-3>에 원격 접속 인증을 추가한다.")])
        self.assertEqual((row["판정"], row["수정 제안"]), (NOT_REFLECTED, "<표 1-3>에 원격 접속 인증을 추가한다."))
        row, _, _ = self.run_one(op, [answer(1, verdict="미반영", suggestion="원격 접속 인증(RAS)은 2019년에 도입되었다.")])
        self.assertEqual((row["판정"], row["수정 제안"]), (NOT_REFLECTED, ""))
        self.assertIn("의견에 없던 2019, ras", " ".join(row["비고"]))
        self.assertEqual(invented("CSAP 인증을 추가한다.", ["클라우드 보안 인증(CSAP) 추가"]), "")

    def test_previous_manuscript_downgrades_unchanged_evidence(self):
        op = opinion("<표 1-3> 보안기능 확인서도 추가되면 좋을 것")

        def reply(prompt):
            return [answer(1, evidence=[number_of(prompt, "보안기능 확인서")])]

        row, calls, _ = self.run_one(op, reply, previous=self.ms)                 # 반영 전 원고에도 같은 문단
        self.assertEqual(row["판정"], CHECK)
        self.assertIn("반영 전 원고에도 있던 내용", " ".join(row["비고"]))
        self.assertIn("반영 전 원고 문단:", calls[0]["document"])
        older = map_manuscript("초고.hwpx", [["차 례", "1-1.", "인증 조사", "필요 지식", "<표 1-3> SW제품 관련 국내 인증", "GS인증"]])
        row, _, _ = self.run_one(op, reply, previous=older)
        self.assertEqual(row["판정"], REFLECTED)
        self.assertIn("반영 전 원고에 없던 문단", " ".join(row["비고"]))
        row, _, _ = self.run_one(op, lambda p: [answer(1, evidence=[number_of(p, "보안기능 확인서")], already_before=True)], previous=older)
        self.assertEqual(row["판정"], CHECK)                                       # LLM이 반영 전에도 있었다고 하면

    def test_term_change_is_always_check_with_question(self):
        op = opinion("한국소프트웨어산업협회는 한국인공지능·소프트웨어산업협회로 명칭 변경됨", group="학습 2", lesson=2, part="필요 지식")
        row, _, _ = self.run_one(op, [answer(1, "용어 변경", "반영", old_terms=["한국소프트웨어산업협회"],
                                             new_terms=["한국인공지능·소프트웨어산업협회"])])
        self.assertEqual((row["판정"], row["유형"]), (CHECK, KIND_TERM))
        self.assertEqual(row["용어 변경"], {"옛": ["한국소프트웨어산업협회"], "새": ["한국인공지능·소프트웨어산업협회"]})
        self.assertIn("한국인공지능·소프트웨어산업협회", row["집필자 확인"])
        self.assertIn("옛 용어 '한국소프트웨어산업협회' 0곳", " ".join(row["비고"]))
        self.assertIn("새 용어 '한국인공지능·소프트웨어산업협회' 1곳", " ".join(row["비고"]))

    def test_form_figure_plan_summary_are_check_and_no_action(self):
        form, _, _ = self.run_one(opinion("제목 가운데 정렬 필요"), [answer(1, "형식", "반영", evidence=[1])])
        self.assertEqual(form["판정"], CHECK)
        figure_op = opinion("[그림 2-1] 순손실 구간 표시를 명확하게 하면 좋을 것 같음", group="학습 2", lesson=2, part="수행 내용")
        figure, _, _ = self.run_one(figure_op, [answer(1, "그림", "반영")])
        self.assertEqual((figure["판정"], figure["근거"][0]["문단"]), (CHECK, "[그림 2-1] 손익분기점 그래프"))
        plan_op = opinion("4.2항의 리셀러 선정 기준 명시가 필요함", group="개발계획서", lesson=None, part=None, page=None)
        plan, calls, _ = self.run_one(plan_op, [answer(1, "내용", "미반영", suggestion="문장")])
        self.assertEqual((plan["판정"], plan["찾은 범위"], paragraph_lines(calls[0])), (CHECK, NO_PLACE, []))
        self.assertIn("[볼 문단: 없음", calls[0]["request"])
        praise_op = opinion("전체적으로 적절하게 작성되어 있음", group="종합 의견", lesson=None, part=None, page=None)
        praise, _, _ = self.run_one(praise_op, [answer(1, "조치 불필요", "확인 필요")])
        self.assertEqual(praise["판정"], NO_ACTION)
        summary, _, _ = self.run_one(opinion("CSAP 내용 보완 필요", group="종합 의견", lesson=None, part=None, page=None),
                                     [answer(1, "내용", "반영", evidence=[1])])
        self.assertEqual(summary["판정"], CHECK)

    def test_whole_manuscript_is_check(self):
        op = opinion("CSAP 인증 내용이 보완되면 좋겠음", group="학습 9", lesson=9, part=None)
        row, calls, _ = self.run_one(op, lambda p: [answer(1, evidence=[number_of(p, "CSAP 인증")])])
        self.assertEqual((row["찾은 범위"], row["판정"]), (WHOLE, CHECK))
        self.assertLess(len(paragraph_lines(calls[0])), len(self.ms.paras))

    def test_unanswered_unknown_and_failure_are_check(self):
        op = opinion("<표 1-3>에 원격 접속 인증도 추가 필요")
        row, _, _ = self.run_one(op, [])
        self.assertEqual((row["판정"], row["유형"]), (CHECK, KIND_UNKNOWN))
        self.assertIn("LLM이 이 의견에 답하지 않음", " ".join(row["비고"]))
        row, _, _ = self.run_one(op, [answer(1, "모름", "반영", evidence=[1])])
        self.assertEqual((row["판정"], row["유형"]), (CHECK, KIND_UNKNOWN))

        def broken(system, document, request, *, task, tasks=None, out_schema=None):
            raise ClaudeError("Claude 연결 실패")

        _, where, notes, _ = locate(op, self.ms)
        answers, stats = ask_all([(op, where)], self.ms, None, generate=broken)
        row = judge(op, where, notes, answers[0], self.ms)
        self.assertEqual((row["판정"], stats["실패"]), (CHECK, 1))
        self.assertTrue(row["LLM"]["상태"].startswith("LLM 호출 실패"))

    def test_all_opinions_in_one_call_and_split_when_cut(self):
        ops = [opinion("<표 1-3> 보안기능 확인서도 추가되면 좋을 것"), opinion("<표 1-3>에 원격 접속 인증도 추가 필요"),
               opinion("제목 가운데 정렬 필요", group="학습모듈 개요", lesson=None, part=None)]
        calls = []
        items = [(op, locate(op, self.ms)[1]) for op in ops]
        _, stats = ask_all(items, self.ms, None, generate=fake(calls=calls))
        self.assertEqual((stats["호출"], stats["물은 의견"], stats["usage"]["calls"]), (1, 3, 1))   # 범위가 달라도 한 번에
        self.assertEqual((stats["usage"]["input"], stats["usage"]["new_calls"]), (1000, 1))

        seen = []

        def cut_when_many(system, document, request, *, task, tasks=None, out_schema=None):
            asked = [int(n) for n in request.split("의견 번호: ", 1)[1].split("\n", 1)[0].split(", ")]
            seen.append((document, asked))
            if len(asked) > 1:
                raise ClaudeError("출력이 max_tokens에서 잘림")
            return {"data": {"opinions": [answer(asked[0], "형식", "확인 필요")]}, "model": "가짜", "cached": False, "usage": {}}

        answers, stats = ask_all(items, self.ms, None, generate=cut_when_many)
        self.assertEqual([asked for _, asked in seen], [[1, 2, 3], [1], [2, 3], [2], [3]])   # 반으로 나눠 다시
        self.assertEqual(len({document for document, _ in seen}), 1)                         # 원고 블록은 같다(캐시 읽기)
        self.assertEqual((stats["호출"], stats["usage"]["calls"], stats["실패"]), (3, 5, 0))
        self.assertEqual([a["유형"] for a in answers], ["형식"] * 3)


class PipelineTests(unittest.TestCase):
    def write(self, folder):
        import make_fixtures as mf

        final, sheet = Path(folder) / "최종_LM2001010409_19v4.hwpx", Path(folder) / "2차_의견서.hwpx"
        mf.write_hwpx(final, [[mf.p(t) for t in MANUSCRIPT[1]]])
        rows = [["2차 검토", "완성본 검토의견서", "", ""], ["학습모듈명", "SW제품 판매 계획 수립", "", ""],
                ["구분", "쪽수", "검토의견", ""],
                ["학습 1-1", "필요지식", "4", "- <표 1-3> 보안기능 확인서도 추가되면 좋을 것 - <표 1-3>에 원격 접속 인증도 추가 필요"],
                ["", "수행 내용", "17", "- 한국소프트웨어산업협회는 한국인공지능·소프트웨어산업협회로 명칭 변경됨"],
                ["기타", "", "-", "- 의견없음"], ["종합 의견", "", "", ""], ["- 적절하게 작성되어 있음", "", "", ""]]
        mf.write_hwpx(sheet, [[mf.table(rows)]])
        return final, sheet

    def test_review_with_injected_llm_and_error_rate(self):
        def reply(call):
            return [answer(1, evidence=[number_of(call, "보안기능 확인서")]),
                    answer(2, verdict="미반영", suggestion="원격 접속 인증을 추가한다."),
                    answer(3, "용어 변경", old_terms=["한국소프트웨어산업협회"], new_terms=["한국인공지능·소프트웨어산업협회"]),
                    answer(4, "조치 불필요", "확인 필요")]

        with tempfile.TemporaryDirectory() as folder:
            final, sheet = self.write(folder)
            result = review([sheet, sheet], final, generate=fake(reply))
        self.assertEqual(result["요약"], {"총 의견": 4, "조치 요구": 3, "반영 후보": 1, "미반영 후보": 1, "확인 필요": 1,
                                         "조치 불필요": 1, "용어 변경(집필자 확인)": 1})        # 같은 파일 두 번 → 한 번만
        self.assertTrue(result["LLM"].startswith("사용(가짜) · 호출 1번(새 호출 1번), 의견 4개 · 입력 1,000"), result["LLM"])
        self.assertEqual({k: result["usage"][k] for k in ("calls", "new_calls", "input", "output")},
                         {"calls": 1, "new_calls": 1, "input": 1000, "output": 100})
        self.assertEqual([r["판정"] for r in result["의견"]], [REFLECTED, NOT_REFLECTED, CHECK, NO_ACTION])
        self.assertEqual(result["의견"][0]["참조"], ["<표 1-3>"])
        rate = error_rate(result["의견"], {1: "반영", 2: "반영", 3: "미반영"})
        self.assertEqual((rate["판정 수"], rate["틀림"], rate["보류(확인 필요)"], rate["오차율"], rate["결과"]), (2, 1, 1, "50.0%", "미달"))
        self.assertEqual(error_rate(result["의견"], {})["결과"], "판단불가")

    def test_without_llm_everything_is_check_with_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            final, sheet = self.write(folder)
            result = review([sheet], final)                     # 테스트 환경에는 키·승인이 없다
        self.assertTrue(result["LLM"].startswith("LLM 미설정"), result["LLM"])
        self.assertIsNone(result["usage"])
        self.assertEqual(result["요약"]["확인 필요"], 4)
        row = result["의견"][0]
        self.assertEqual((row["판정"], row["유형"], row["근거"]), (CHECK, KIND_UNKNOWN, []))
        self.assertTrue(row["비고"][-1].startswith("LLM 미설정"))
        self.assertEqual(row["LLM"]["상태"], result["LLM"])

    def test_given_rounds_do_not_count_first_round_table_twice(self):
        import make_fixtures as mf

        head1 = [["1차 검토", "초고본 검토의견서", "", ""], ["구분", "쪽수", "검토의견", ""]]
        rows1 = head1 + [["학습 1-1", "필요지식", "4", "- <표 1-3> 보안기능 확인서도 추가되면 좋을 것"]]
        rows2 = [["2차 검토", "완성본 검토의견서", "", ""], ["구분", "쪽수", "검토의견", ""],
                 ["학습 1-1", "수행 내용", "17", "- [그림 1-1] 범례 추가 필요"]]
        with tempfile.TemporaryDirectory() as folder:
            final, _ = self.write(folder)
            first, second = Path(folder) / "1차.hwpx", Path(folder) / "2차.hwpx"
            mf.write_hwpx(first, [[mf.table(rows1)]])
            mf.write_hwpx(second, [[mf.table(rows1), mf.table(rows2)]])       # 2차 파일 안에 1차 표가 함께 든 실물 모양
            given = review([first, second], final, rounds=["1차", "2차"])
            auto = review([first, second], final)
        self.assertEqual(given["요약"]["총 의견"], 2)
        self.assertEqual([(r["차수"], r["의견서"]) for r in given["의견"]], [("1차", "1차.hwpx"), ("2차", "2차.hwpx")])
        self.assertEqual(given["요약"], auto["요약"])

    def test_no_opinions_is_error(self):
        with self.assertRaises(ValueError):
            review([], "원고.hwpx")


if __name__ == "__main__":
    unittest.main()
