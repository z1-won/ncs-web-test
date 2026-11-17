"""원고의 그림 목록 읽기(ncs_core.figures) — 캡션·출처 줄·AI 활용 줄. F08 'AI 도구 사용 표기 예'의 다섯 꼴을 그대로 쓴다."""

import unittest
from datetime import date
from types import SimpleNamespace

from ncs_core.figures import manuscript_figures, parse_ai_mark, parse_label


def document(*sections, aside=()):
    return SimpleNamespace(sections=[list(s) for s in sections],
                           section_aside_paragraphs=lambda index: frozenset(aside) if index == 0 else frozenset())


class FigureTests(unittest.TestCase):
    def test_f08_marking_examples(self):
        doc = document([
            "1. 집필진이 내용을 작성하고 AI로 이미지를 만든 경우", "",
            "출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 7. 20.", "[그림 1-1] 생산 설비 주요 구성 요소",
            "3. 이미지를 보정한 경우",
            "출처: 교육부(2018). 공급망 공정계획(LM0204010404_16v2). 한국직업능력개발원. p.6.",
            "ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.", "[그림 1-2] 생산 성형 기간과 생산 수준.",
            "출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 7. 20.[그림 1-3] 고밀도 실장 영역 사례",   # 예 4: 한 문단에 붙음
            "출처: 집필진 제작(2026)", "ChatGPT를 활용하여 수정 보완함. 2026 .6. 23.", "[그림 1-] 제조실행시스템(MES) 추적성 연동",   # 예 5: 번호 미완성·띄어쓰기
        ])
        found = manuscript_figures(doc)
        self.assertEqual([(f.label, f.title) for f in found], [
            ("그림 1-1", "생산 설비 주요 구성 요소"), ("그림 1-2", "생산 성형 기간과 생산 수준"),
            ("그림 1-3", "고밀도 실장 영역 사례"), ("그림 1-", "제조실행시스템(MES) 추적성 연동")])
        self.assertEqual([(f.ai.tool, f.ai.mode, f.ai.on) for f in found], [
            ("ChatGPT", "generated", date(2026, 7, 20)), ("ChatGPT", "modified", date(2026, 7, 20)),
            ("ChatGPT", "generated", date(2026, 7, 20)), ("ChatGPT", "modified", date(2026, 6, 23))])
        self.assertTrue(found[1].source_line.startswith("출처: 교육부(2018)"))
        self.assertEqual((found[3].minor, found[0].para), (None, 4))

    def test_references_in_running_text_are_not_captions(self):
        doc = document(["구조는 [그림 1-1]과 같이 나타낸다.", "[그림 1-1]은 개념을 보여 준다.", "[그림 1-2] 참조",
                        "출처: 집필진 제작(2026)", "[그림 1-1] 개념도", "〈표 1-1〉 비교표"])
        self.assertEqual([(f.label, f.title, f.para) for f in manuscript_figures(doc)], [("그림 1-1", "개념도", 4)])

    def test_source_and_ai_lines_belong_to_the_nearest_caption_only(self):
        doc = document(["출처: 집필진 제작(2026)", "Gemini를 활용하여 생성함. 2026. 5. 1.", "[그림 1-1] 첫 그림",
                        "[그림 1-2] 출처 없는 그림",                                    # 위 그림의 출처·AI 줄을 가져오면 안 된다
                        "출처: 집필진 제작(2026)", "", "설명 한 줄", "설명 두 줄", "설명 세 줄", "설명 네 줄", "[그림 1-3] 출처가 멀리 있는 그림",
                        "이 그림은 도구를 활용하여 생성함을 밝힌 본문 문장이며 표기 줄이 아니다.", "[그림 1-4] 본문 문장 아래 그림"])
        found = manuscript_figures(doc)
        self.assertEqual([(f.label, bool(f.source_line), f.ai is not None) for f in found],
                         [("그림 1-1", True, True), ("그림 1-2", False, False), ("그림 1-3", False, False), ("그림 1-4", False, False)])

    def test_memo_and_header_paragraphs_are_skipped(self):
        doc = document(["[그림 9-9] 메모 안의 글", "출처: 집필진 제작(2026)", "[그림 1-1] 본문 그림"], aside=(0,))
        self.assertEqual([f.label for f in manuscript_figures(doc)], ["그림 1-1"])

    def test_parsers(self):
        self.assertEqual(parse_label("［그림 １－２］ 전각 번호"), None)          # 전각 괄호는 캡션 괄호가 아니다(F02 필요 지식 ⑦이 잡는다)
        self.assertEqual(parse_label("[그림 １－２] 전각 숫자"), (1, 2, "전각 숫자"))
        self.assertEqual(parse_label("[그림 3 – 10] 긴 줄표"), (3, 10, "긴 줄표"))
        self.assertIsNone(parse_label("그림 없는 글"))
        mark = parse_ai_mark("나노바나나 2를 활용하여 수정보완함. 2026. 2. 30.")      # 달력에 없는 날
        self.assertEqual((mark.tool, mark.mode, mark.on), ("나노바나나 2", "modified", None))
        self.assertIsNone(parse_ai_mark("출처: 집필진 제작(2026)"))
        self.assertEqual(parse_ai_mark("Copilot을 활용하여 생성함").on, None)


if __name__ == "__main__":
    unittest.main()
