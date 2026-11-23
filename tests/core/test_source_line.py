"""ncs_core.source_line: 출처 줄 찾기·해석과 AI 활용 표기(직능연 「AI활용기준_도구사용표기예」 2026-09) 읽기."""

import unittest

from ncs_core.source_line import (
    ai_type_candidates,
    find_ai_marker,
    find_source_line,
    parse_ai_marker,
    parse_source,
    source_check,
)


class FindSourceLineTests(unittest.TestCase):
    def test_finds_line_above_and_stops_at_previous_figure(self):
        paras = ["출처: 집필진 제작(2025)", "[그림 1-1] 가", "본문", "[그림 1-2] 나"]
        self.assertEqual(find_source_line(paras, 1), 0)
        self.assertIsNone(find_source_line(paras, 3))          # 위로 가다 [그림 1-1]을 만나면 멈춤

    def test_ai_line_between_source_and_caption(self):
        paras = ["출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 7. 20.", "[그림 1-1] 생산 설비"]
        self.assertEqual(find_source_line(paras, 2), 0)
        self.assertEqual(find_ai_marker(paras, 2, 0), 1)


class ParseSourceTests(unittest.TestCase):
    def test_old_module_citation(self):
        info = parse_source("출처: 교육부(2015). 기업 내부 환경 분석(LM2001010401_14v2). 한국직업능력개발원. p.25.")
        self.assertEqual(info.kind, "기존 학습모듈")
        self.assertEqual(info.cited_module, "LM2001010401_14v2")
        self.assertEqual(info.cited_page, 25)
        self.assertEqual((info.author, info.year), ("교육부", "2015"))
        self.assertEqual(info.format_issues, ())

    def test_format_issues_from_real_finals(self):
        # 사람 검수를 통과한 최종본에 있던 꼴: '출처:' 뒤 띄어쓰기 없음. 옛 판본의 8자리 모듈 코드는 정상(오류 아님)
        info = parse_source("출처:교육부(2015). SW제품 판매 계획 수립(LM20010409_14v2). 한국직업능력연구원. p.8.")
        self.assertEqual((info.kind, info.cited_module), ("기존 학습모듈", "LM20010409_14v2"))
        self.assertEqual(len(info.format_issues), 1)
        self.assertIn("띄어쓰기", info.format_issues[0])
        self.assertEqual(parse_source("출처: 교육부(2015). 판매 계획(LM20010409_14v2). 한국직업능력개발원. p.8.").format_issues, ())

    def test_kinds(self):
        self.assertEqual(parse_source("출처: 집필진 제작(2025)").kind, "집필진 제작")
        kogl = parse_source("출처: 공공누리 홈페이지(https://www.kogl.go.kr)에서 2026. 1. 15. 검색. 공공누리 제1유형.")
        self.assertEqual((kogl.kind, kogl.kogl_type, kogl.checked_date), ("공공누리", "1", "2026. 1. 15."))
        self.assertEqual(kogl.url, "https://www.kogl.go.kr")
        self.assertEqual(parse_source("출처: 호텔 PMS 화면(https://www.example.com/pms)에서 2026. 1. 15. 스크린 숏.").kind, "스크린숏")
        self.assertEqual(parse_source("출처: 김철수(2020). 『호텔 경영론』. 백산출판사. p.12.").kind, "문헌")
        self.assertEqual(parse_source("출처: 무엇인지 모를 줄").kind, "알 수 없음")

    def test_source_check_unchanged(self):
        self.assertEqual(source_check("출처: 집필진 제작(2026)"), ("O", "집필진 제작"))


class AiMarkerTests(unittest.TestCase):
    def test_f08_examples(self):
        made = parse_ai_marker("ChatGPT를 활용하여 생성함. 2026. 7. 20.")
        self.assertEqual((made.tool, made.action, made.date), ("ChatGPT", "생성", "2026.7.20."))
        edited = parse_ai_marker("ChatGPT를 활용하여 수정 보완함. 2026 .6. 23.")       # 예 5: 날짜 띄어쓰기가 어긋난 원문
        self.assertEqual((edited.action, edited.date), ("수정 보완", "2026.6.23."))
        glued = parse_ai_marker("ChatGPT를 활용하여 생성함. 2026. 7. 20.[그림 1-] 고밀도 실장 영역 사례")  # 예 4: 캡션이 붙음
        self.assertEqual(glued.action, "생성")
        self.assertIsNone(parse_ai_marker("출처: 집필진 제작(2026)"))

    def test_type_candidates(self):
        own = parse_source("출처: 집필진 제작(2026)")
        third = parse_source("출처: 교육부(2018). 공급망 공정계획(LM0204010404_16v2). 한국직업능력개발원. p.6.")
        edit = parse_ai_marker("ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.")
        make = parse_ai_marker("ChatGPT를 활용하여 생성함. 2026. 7. 20.")
        self.assertEqual(ai_type_candidates(third, edit), (3,))      # 제3자 원본 보정 — 005 ⑨ 대상
        self.assertEqual(ai_type_candidates(own, edit), (2, 5))
        self.assertEqual(ai_type_candidates(own, make), (1, 2, 4))
        self.assertEqual(ai_type_candidates(own, None), ())


if __name__ == "__main__":
    unittest.main()
