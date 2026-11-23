"""REQ-02-008 출처 검토 — 합성 문서로 규칙(요건·AI 표기 형식·순서·생성/수정 구분·문장 단위 출처)과 최종본 한 편."""

import unittest
from pathlib import Path

from ncs_core import Document
from ncs_core.source_line import parse_ai_marker, parse_source
from ncs_sources.checks import check_entry
from ncs_sources.extract import table_sources
from ncs_sources.quotes import quote_candidates

ROOT = Path(__file__).resolve().parents[2]
FINAL = next(ROOT.glob("samples/최종본_SW제품기획/LM2001010407_19v4_*.hwpx"), None)


def entry(kind="그림", source=None, ai=None, s=10, a=11, c=12):
    return {"kind": kind, "source_line": source, "source": parse_source(source) if source else None,
            "ai": parse_ai_marker(ai) if ai else None, "ai_line": ai, "source_para": s if source else None,
            "ai_para": a if ai else None, "caption_para": c, "caption": "[그림 1-1] 가", "region": "학습 1"}


class RuleTests(unittest.TestCase):
    def test_figure_needs_source_table_does_not(self):
        self.assertEqual(check_entry(entry())[0]["출처 있음"], "X")
        self.assertEqual(check_entry(entry(kind="표"))[0]["출처 있음"], "-")

    def test_requirements_by_kind(self):
        web = check_entry(entry(source="출처: 한국관광공사 홈페이지(https://kto.or.kr)에서 2026. 1. 5. 검색."))[0]
        self.assertEqual(web["출처 요건(계약서 제4조)"], "O")
        no_page = check_entry(entry(source="출처: 홍길동(2020). 경영 전략. 한빛출판."))
        self.assertEqual(no_page[0]["출처 요건(계약서 제4조)"], "X")
        self.assertIn("쪽", no_page[1]["출처 요건(계약서 제4조)"])
        own = check_entry(entry(source="출처: 집필진 제작(2025)"))[0]
        self.assertEqual(own["출처 요건(계약서 제4조)"], "-")

    def test_ai_marker_format_order_and_verb(self):
        ok = check_entry(entry(source="출처: 집필진 제작(2025)", ai="ChatGPT를 활용하여 생성함. 2025. 3. 2."))[0]
        self.assertEqual((ok["AI 표기 형식"], ok["AI 표기 순서"], ok["생성·수정 구분"]), ("O", "O", "O"))
        no_date = check_entry(entry(source="출처: 집필진 제작(2025)", ai="ChatGPT를 활용하여 생성함."))[0]
        self.assertEqual(no_date["AI 표기 형식"], "X")
        wrong_order = check_entry(entry(source="출처: 집필진 제작(2025)", ai="ChatGPT를 활용하여 생성함. 2025. 3. 2.", s=11, a=10))[0]
        self.assertEqual(wrong_order["AI 표기 순서"], "X")
        third = check_entry(entry(source="출처: 홍길동(2020). 경영 전략. 한빛출판. p.3.", ai="Gemini를 활용하여 생성함. 2025. 3. 2."))[0]
        self.assertEqual(third["생성·수정 구분"], "△")                    # 원 출처가 있는데 '생성함'
        orphan = check_entry(entry(ai="Gemini를 활용하여 수정 보완함. 2025. 3. 2."))[0]
        self.assertEqual(orphan["AI 표기 순서"], "X")                     # 출처 줄 없이 AI 줄만

    def test_ai_mixed_into_source_line(self):
        mixed = check_entry(entry(source="출처: ChatGPT로 생성(2025)"))[0]
        self.assertEqual(mixed["AI 표기 위치"], "X")


class ExtractTests(unittest.TestCase):
    def test_table_source_below_caption(self):
        doc = Document(Path("x.hwpx"), "hwpx", [["앞"], ["<표 1-1> 가", "칸", "칸", "출처: 홍길동(2020). 나. 다. p.3.", "본문",
                                                          "<표 1-2> 라", "칸", "출처: 집필진 제작(2025)", "[그림 1-1] 그림"]])
        tables = table_sources(doc)
        self.assertEqual(tables[0]["source_para"], 3)
        self.assertIsNone(tables[1]["source_para"])                        # 바로 아래가 그림 캡션 — 그림의 출처

    def test_quote_without_source_is_candidate(self):
        quote = "그는 “품질은 우연히 만들어지는 것이 아니라 언제나 지적 노력의 결과이다”라고 말하였다."
        cited = "홍길동(2020)은 “품질은 우연히 만들어지는 것이 아니라 언제나 지적 노력의 결과이다”라고 하였다."
        doc = Document(Path("x.hwpx"), "hwpx", [["앞"], [quote, "다음 문단", cited, "끝"]])
        found = quote_candidates(doc)
        self.assertEqual([q["para"] for q in found], [0])


@unittest.skipIf(FINAL is None, "최종본 원고 없음")
class FinalTests(unittest.TestCase):
    def test_final_407(self):
        from ncs_sources import review_sources
        result = review_sources(FINAL)
        s = result["summary"]
        self.assertEqual(s["그림 출처"], 18)
        self.assertGreater(s["표"], 0)
        self.assertGreater(s["참고 자료 항목"], 0)
        self.assertTrue(result["llm_needed"])
        ieee = [r for r in result["rows"] if "IEEE" in (r["원고"] or "")]
        self.assertTrue(ieee and ieee[0]["체크"]["출처 요건(계약서 제4조)"] == "X")


if __name__ == "__main__":
    unittest.main()
