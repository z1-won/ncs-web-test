"""원고 문장 추천(ncs_suggest, REQ-02-004): 종결형 활용(받침·불규칙·오변환 방지), 종류별 규정 판정, 표현 규칙, 순위, 참고 예문,
AI 후보(가짜 응답 주입 — 검증·버림·호출 차단), 원고 전체(합성 hwpx), CLI.

실제 원고(samples/, git 제외)로 돌린 조작본 대조 결과는 README의 문장 추천 단락에 적는다.
"""

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from ncs_suggest import KINDS, suggest_manuscript, suggest_sentence
from ncs_suggest.__main__ import main
from ncs_suggest.config import AI_STATUS, DEFAULT_CONFIG, SOURCE_AI, SOURCE_RULE
from ncs_suggest.endings import read_predicate
from ncs_suggest.examples import similar
from ncs_suggest.extract import split_prefix
from ncs_suggest.kinds import check
from ncs_suggest.llm_suggest import validate
from ncs_suggest.rewrite import candidates

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
BOX1, BOX2 = "\U000F02B1", "\U000F02B2"   # 네모 번호 [1] [2] 글자


def top(kind: str, text: str, extra=frozenset()) -> str | None:
    found = candidates(kind, text, extra=extra)
    return found[0]["문장"] if found else None


def forms(text: str, target: str) -> str | None:
    predicate = read_predicate(text)
    return predicate.form(target) if predicate else None


class EndingTests(unittest.TestCase):
    """서술어 읽기와 활용 — 받침 바꾸기, 불규칙은 건너뛰기."""

    def test_ha_family_all_targets(self):
        self.assertEqual(forms("요구사항을 정의합니다", "한다"), "요구사항을 정의한다")
        self.assertEqual(forms("요구사항을 정의함", "할 수 있다"), "요구사항을 정의할 수 있다")
        self.assertEqual(forms("요구사항 정의할 것", "하기"), "요구사항 정의하기")
        self.assertEqual(forms("요구사항 정의하기", "명사"), "요구사항 정의")
        self.assertEqual(forms("요구사항 분석한다", "능력"), "요구사항 분석 능력")
        self.assertIsNone(forms("요구사항을 분석한다", "능력"))            # 조사가 붙은 목적어는 '~ 능력'으로 줄이지 않는다
        self.assertEqual(forms("요구사항을 분석한다", "여부"), "요구사항을 분석하는지 여부")

    def test_doe_family(self):
        self.assertEqual(forms("자료가 수집됩니다", "한다"), "자료가 수집된다")
        self.assertEqual(forms("자료가 수집됨", "할 수 있다"), "자료가 수집될 수 있다")
        self.assertIsNone(read_predicate("이 방법은 안된다"))               # '안된다'는 한 낱말

    def test_vowel_stem_swaps_final_consonant(self):
        self.assertEqual(forms("기초를 배운다", "할 수 있다"), "기초를 배울 수 있다")
        self.assertEqual(forms("기초를 배울 수 있다", "한다"), "기초를 배운다")
        self.assertEqual(forms("기초를 배웁니다", "한다"), "기초를 배운다")
        self.assertEqual(forms("도구를 만든다", "할 수 있다"), "도구를 만들 수 있다")   # ㄹ 줄기도 같은 꼴
        self.assertEqual(forms("문제를 가르친다", "할 수 있다"), "문제를 가르칠 수 있다")
        self.assertIsNone(forms("도구를 만든다", "하기"))                  # 만들다/만드다를 가를 수 없어 '-기'는 만들지 않는다

    def test_consonant_stem(self):
        self.assertEqual(forms("문서를 읽습니다", "한다"), "문서를 읽는다")
        self.assertEqual(forms("문서를 읽는다", "할 수 있다"), "문서를 읽을 수 있다")
        self.assertEqual(forms("문서를 읽을 수 있다", "한다"), "문서를 읽는다")
        self.assertEqual(forms("자리에 앉는다", "할 수 있다"), "자리에 앉을 수 있다")

    def test_irregular_verbs_are_not_converted(self):
        self.assertIsNone(forms("설명을 듣는다", "할 수 있다"))   # ㄷ 불규칙(들을)
        self.assertIsNone(forms("동료를 돕는다", "할 수 있다"))   # ㅂ 불규칙(도울)
        self.assertIsNone(forms("집을 짓는다", "할 수 있다"))     # ㅅ 불규칙(지을)
        self.assertIsNone(read_predicate("설명을 들을 수 있다"))
        self.assertIsNone(read_predicate("동료를 도울 수 있다"))
        self.assertIsNone(read_predicate("집을 지을 수 있다"))
        self.assertEqual(forms("기초를 세울 수 있다", "한다"), "기초를 세운다")   # '우' 줄기 동사 목록은 바꾼다

    def test_adjectives_and_short_words_are_not_read_as_verbs(self):
        for text in ("절차가 간단한", "결과가 정확함", "자료가 많습니다", "데이터가 있습니다", "요소 하나", "범위의 제한", "결과에 결함"):
            with self.subTest(text=text):
                predicate = read_predicate(text)
                made = predicate.form("한다") if predicate else None
                self.assertNotIn(made, {"절차가 간단한다", "결과가 정확한다", "자료가 많는다", "데이터가 있는다", "요소 한다", "범위의 제한다", "결과에 결한다"})

    def test_bare_action_noun_and_junk(self):
        self.assertEqual(forms("수행절차를 확인", "한다"), "수행절차를 확인한다")
        self.assertEqual(forms("단계별로 설명다", "한다"), "단계별로 설명한다")
        self.assertEqual(forms("방법을 지도한다람쥐", "한다"), "방법을 지도한다")
        self.assertEqual(forms("데이터를 측정시킨다치이카와", "한다"), "데이터를 측정시킨다")
        self.assertEqual(forms("성능을 분석하도록", "한다"), "성능을 분석하도록 한다")
        self.assertIsNone(read_predicate("정량적인 기준으로 작성하도록 도지코인"))      # 모르는 낱말에 '하다'를 붙이지 않는다
        self.assertIsNone(read_predicate("권한을 매핑"))                             # 목록에 없는 외래어
        self.assertEqual(read_predicate("권한을 매핑", frozenset({"매핑"})).form("한다"), "권한을 매핑한다")   # 같은 원고의 용례


class KindTests(unittest.TestCase):
    def test_goal(self):
        self.assertEqual(check("학습 목표", "요구사항을 수집할 수 있다."), (True, []))
        ok, why = check("학습 목표", "학습자는 요구사항을 수집한다.")
        self.assertFalse(ok)
        self.assertEqual(len(why), 2)

    def test_action_sentences_follow_core_judge(self):
        self.assertTrue(check("수행 순서", "요구사항을 확인할 수 있다.")[0])      # 수행 ④는 '~할 수 있다.'도 적합
        self.assertFalse(check("교수 방법", "요구사항을 설명할 수 있다.")[0])     # 교수·학습 ②④는 부적합
        self.assertFalse(check("학습 방법", "요구사항을 정리한다")[0])            # 마침표 없음

    def test_eval_title_unit(self):
        self.assertTrue(check("평가 항목", "요구사항 분석 능력")[0])
        self.assertFalse(check("평가 항목", "요구사항 분석 능력.")[0])
        self.assertTrue(check("평가 항목", "요구사항의 이해")[0])               # 그 밖의 명사형은 추천하지 않는다
        self.assertTrue(check("학습명", "요구사항 수집하기")[0])
        self.assertFalse(check("학습명", "요구사항 수집하기기")[0])
        self.assertTrue(check("학습 내용명", "요구사항 수집")[0])
        self.assertFalse(check("학습 내용명", "요구사항 수집하기")[0])
        self.assertIsNone(check("학습 내용명", "요구사항 성능")[0])               # 목록에 없는 낱말 — 확인 필요
        with self.assertRaises(ValueError):
            check("없는 종류", "문장")


class CandidateTests(unittest.TestCase):
    def test_typical_fixes(self):
        cases = [
            ("학습 목표", "학습자가 요구사항을 수집하고 명세화한다.", "요구사항을 수집하고 명세화할 수 있다."),
            ("학습명", "요구사항 수집함", "요구사항 수집하기"),
            ("학습명", "요구사항 정의할까", "요구사항 정의하기"),
            ("수행 내용 제목", "요구사항 검증하기..!", "요구사항 검증하기"),
            ("학습 내용명", "요구사항 수집하기", "요구사항 수집"),
            ("수행 순서", "요구사항 분석 절차를 확인", "요구사항 분석 절차를 확인한다."),
            ("교수 방법", "사례를 중심으로 설명하자.", "사례를 중심으로 설명한다."),
            ("교수 방법", "명세서를 작성하도록 해라.", "명세서를 작성하도록 한다."),
            ("학습 방법", "확인할 수 있도록다.", "확인할 수 있도록 한다."),
            ("학습 방법", "결과를 정리.", "결과를 정리한다."),
            ("평가 항목", "요구사항 수집 계획 수립 능력.", "요구사항 수집 계획 수립 능력"),
            ("교수 방법", "교수자는 사례를 설명한다.", "사례를 설명한다."),
        ]
        for kind, text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(top(kind, text), expected)

    def test_expression_rules(self):
        self.assertEqual(top("교수 방법", "결과가 미리 예측되어지도록 지도한다."), "결과가 예측되도록 지도한다.")
        self.assertEqual(top("학습 방법", "요구사항을를 정리한다 ."), "요구사항을 정리한다.")
        self.assertEqual(top("학습 방법", "사례를 다시 재확인한다."), "사례를 재확인한다.")
        self.assertIsNone(top("학습 방법", "마을을 조사한다."))      # '을을'은 '마을을'과 겹쳐 겹친 조사로 보지 않는다
        self.assertIsNone(top("학습 방법", "아이가 발표한다."))

    def test_no_candidate_when_unsure(self):
        for kind, text in [("교수 방법", "기준으로 작성하도록 도지코인."), ("학습 방법", "동료를 도울 수 있다."),
                           ("학습 내용명", "요구사항 방법"), ("교수 방법", "절차가 간단한."), ("수행 순서", "결과를 포함")]:
            with self.subTest(text=text):
                self.assertEqual(candidates(kind, text), [])

    def test_correct_sentence_has_no_candidate(self):
        for kind, text in [("교수 방법", "사례를 중심으로 설명한다."), ("학습 목표", "요구사항을 수집할 수 있다."), ("학습명", "요구사항 수집하기")]:
            self.assertEqual(candidates(kind, text), [])

    def test_ranking_and_fields(self):
        found = candidates("수행 순서", "요구사항 분석 절차를 확인")
        self.assertEqual([c["문장"] for c in found], ["요구사항 분석 절차를 확인한다.", "요구사항 분석 절차를 확인할 수 있다."])
        self.assertEqual([c["출처"] for c in found], [SOURCE_RULE, SOURCE_RULE])
        self.assertGreater(found[0]["점수"], found[1]["점수"])
        self.assertTrue(found[0]["근거"] and found[0]["바뀐 곳"])
        # 표현 규칙을 다 적용한 후보가 일부만 적용한 후보보다 위
        mixed = candidates("교수 방법", "결과가 미리 예측되어지도록 지도함.")
        self.assertEqual(mixed[0]["문장"], "결과가 예측되도록 지도한다.")
        self.assertLessEqual(len(mixed), DEFAULT_CONFIG.max_candidates)
        self.assertTrue(all(check("교수 방법", c["문장"])[0] for c in mixed))   # 모든 후보는 규정을 지킨다

    def test_eval_offers_two_forms(self):
        self.assertEqual([c["문장"] for c in candidates("평가 항목", "요구사항 분석한다.")], ["요구사항 분석 능력", "요구사항 분석하는지 여부"])

    def test_examples_and_prefix(self):
        pool = [("절차를 단계별로 설명한다.", "학습 1 교수 방법 2"), ("실습 장비를 준비한다.", "학습 1 교수 방법 3")]
        self.assertEqual(similar("절차를 단계별로 설명함.", pool)[0]["자리"], "학습 1 교수 방법 2")
        self.assertEqual(split_prefix(BOX1 + " 요구사항을 확인한다."), ("[1]", "요구사항을 확인한다."))
        self.assertEqual(split_prefix("• 사례를 설명한다."), ("•", "사례를 설명한다."))
        self.assertEqual(split_prefix("󰊱 요구사항을 확인한다."), ("[1]", "요구사항을 확인한다."))   # hwp 서로게이트


class SentenceModeTests(unittest.TestCase):
    def test_direct_input(self):
        result = suggest_sentence("• 사례를 중심으로 설명함.", "교수 방법")
        self.assertEqual(result["상태"], "규칙 위반")
        self.assertEqual(result["앞 번호"], "•")
        self.assertEqual(result["후보"][0]["순위"], 1)
        self.assertEqual(result["후보"][0]["문장"], "사례를 중심으로 설명한다.")
        self.assertEqual(suggest_sentence("사례를 설명한다.", "교수 방법")["상태"], "규정에 맞음")
        unsure = suggest_sentence("요구사항 성능", "학습 내용명")
        self.assertEqual(unsure["상태"], "확인 필요")
        self.assertIn("추천 없음", unsure["추천 없음"])
        self.assertEqual(set(KINDS), {"학습 목표", "수행 순서", "교수 방법", "학습 방법", "안전·유의 사항", "평가 항목", "학습명", "수행 내용 제목", "학습 내용명"})

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            suggest_sentence("문장", "없는 종류")
        with self.assertRaises(ValueError):
            suggest_sentence("  ", "교수 방법")

    def test_no_suggestion_is_honest(self):
        result = suggest_sentence("기준으로 작성하도록 도지코인.", "교수 방법")
        self.assertEqual(result["후보"], [])
        self.assertTrue(result["추천 없음"].startswith("추천 없음(사람이 고쳐야 함)"))


def fake(fix=(), wording=(), model="fake-model"):
    """가짜 LLM — 규칙에 걸린 문장 줄을 받으면 fix, 규정에 맞는 문장 줄을 받으면 wording 지적을 돌려준다."""
    calls = []

    def asker(lines):
        calls.append(list(lines))
        violating = any(check(kind, line)[0] is not True for line in lines for kind in ("교수 방법",))
        return {"data": {"findings": list(fix if violating else wording)}, "model": model}

    return asker, calls


class AiTests(unittest.TestCase):
    """AI 후보는 가짜 응답으로만 검사한다(실제 호출 없음). 수행 ③·평가 ④와 같은 줄 번호 방식(line_findings)."""

    def test_valid_candidate_is_rechecked_and_marked(self):
        asker, calls = fake(fix=[{"line": 1, "reason": "종결 교정", "suggestion": "사례를 중심으로 절차를 설명한다."}])
        result = suggest_sentence("사례 중심으로 절차를 설명함.", "교수 방법", use_llm=True, asker=asker)
        self.assertEqual([c["출처"] for c in result["후보"]], [SOURCE_RULE, SOURCE_AI])
        ai = result["후보"][1]
        self.assertEqual((ai["모델"], ai["근거"]), ("fake-model", ["종결 교정", "규칙 재검사 통과"]))
        self.assertEqual(calls, [["사례 중심으로 절차를 설명함."]])          # 문장 줄만 보낸다(앞뒤 문단 없음)
        self.assertTrue(result["AI"].startswith("AI 사용(fake-model)"))

    def test_bad_ai_candidates_are_dropped_with_reasons(self):
        cases = [
            ("사례 중심으로 절차를 설명함.", "같음"),                              # 규정 위반(그대로)
            ("사례 중심으로 절차를 3단계로 설명한다.", "수치"),                    # 새 수치
            ("사례 중심으로 Agile 절차를 설명한다.", "영문"),                      # 새 영문
            ("학습자가 현장 전문가와 협업 프로젝트를 수행하도록 지도한다.", "너무 다름"),   # 내용을 바꿈
            ("사례 중심으로 절차를 설명한다.", "이미 있는 후보"),                  # 규칙 후보와 같음
        ]
        for text, why in cases:
            asker, _ = fake(fix=[{"line": 1, "suggestion": text}])
            result = suggest_sentence("사례 중심으로 절차를 설명함.", "교수 방법", use_llm=True, asker=asker)
            self.assertEqual([c["출처"] for c in result["후보"]], [SOURCE_RULE], text)
            self.assertIn(why, result["버린 AI 후보"][0]["이유"], text)

    def test_validate_brand(self):
        self.assertIn("상호", validate("교수 방법", "프로그램으로 표를 작성함.", "엑셀로 표를 작성한다."))
        self.assertIsNone(validate("교수 방법", "프로그램으로 표를 작성함.", "프로그램으로 표를 작성한다."))

    def test_wording_card_for_rule_compliant_sentence(self):
        finding = {"line": 1, "kind": "어색한 낱말", "reason": "'저격한다'는 문맥에 맞지 않음", "suggestion": "절차를 단계별로 설명한다."}
        asker, calls = fake(wording=[finding])
        result = suggest_sentence("절차를 단계별로 저격한다.", "교수 방법", use_llm=True, asker=asker)
        self.assertEqual(calls, [["절차를 단계별로 저격한다."]])
        self.assertEqual((result["상태"], result["사유"]), (AI_STATUS, ["어색한 낱말 — '저격한다'는 문맥에 맞지 않음"]))
        self.assertEqual([(c["문장"], c["출처"]) for c in result["후보"]], [("절차를 단계별로 설명한다.", SOURCE_AI)])

    def test_wording_without_usable_sentence_is_honest(self):
        asker, _ = fake(wording=[{"line": 1, "kind": "어색한 낱말", "reason": "낱말이 어색함", "suggestion": "절차를 5단계로 설명한다."}])
        result = suggest_sentence("절차를 단계별로 저격한다.", "교수 방법", use_llm=True, asker=asker)
        self.assertEqual((result["상태"], result["후보"]), (AI_STATUS, []))
        self.assertTrue(result["추천 없음"].startswith("추천 없음(사람이 고쳐야 함)"))
        self.assertIn("수치", result["버린 AI 후보"][0]["이유"])

    def test_no_wording_finding_stays_compliant(self):
        asker, _ = fake()
        result = suggest_sentence("절차를 단계별로 설명한다.", "교수 방법", use_llm=True, asker=asker)
        self.assertEqual(result["상태"], "규정에 맞음")

    def test_blocked_call_reports_reason(self):
        result = suggest_sentence("절차를 설명함.", "교수 방법", use_llm=True)   # 키·승인 없음
        self.assertTrue(result["AI"].startswith("AI 미사용"))
        self.assertEqual([c["출처"] for c in result["후보"]], [SOURCE_RULE])


def _p(text: str) -> str:
    return f'<hp:p><hp:run><hp:t>{escape(text)}</hp:t></hp:run></hp:p>'


def _table(rows: list[list[str]]) -> str:
    cells = "".join("<hp:tr>" + "".join(f'<hp:tc><hp:subList>{_p(t)}</hp:subList><hp:cellAddr rowAddr="{r}" colAddr="{c}"/></hp:tc>'
                                        for c, t in enumerate(row)) + "</hp:tr>" for r, row in enumerate(rows))
    return f'<hp:p><hp:run><hp:t></hp:t><hp:tbl rowCnt="{len(rows)}" colCnt="{len(rows[0])}">{cells}</hp:tbl></hp:run></hp:p>'


def write_manuscript(path: Path) -> Path:
    front = ["차 례", "학습 1. 요구사항 수집함 1", "1-1. 요구사항 수집하기 3", "1-2. 요구사항 분석 7", "• 교수·학습 방법 10", "• 평가 12",
             "학습모듈의 개요", "학습모듈의 목표", "학습자는 요구사항을 수집하고 분석한다.", "학습모듈의 내용 체계", "핵심 용어"]
    body = ["학습 1", "요구사항 수집하기", "1-1. 요구사항 수집", "학습 목표", "• 요구사항을 수집할 수 있다.", "• 학습자는 이해관계자를 식별할 수 있다.",
            "필요 지식", "요구사항은 시스템이 갖춰야 할 조건이다.", "수행 내용", "요구사항 수집함", "재료·자료", "• 회의록", "수행 순서",
            BOX1 + " 요구사항을 확인", "1. 세부 설명이다", BOX2 + " 이해관계자를 식별한다.",
            "1-2. 요구사항 분석", "요구사항을 분류한다.",
            "교수·학습 방법", "교수 방법", "• 사례를 중심으로 설명함.", "• 절차를 단계별로 설명한다.", "학습 방법", "• 직접 요구사항을 정리하세요.",
            "• 체크리스트를 작성한다.", "평 가"]
    eval_table = _table([["학습 내용", "평가 항목", "성취수준"], ["", "", "상"], ["요구사항 수집", "요구사항 수집 능력.", ""], ["", "이해관계자 식별 능력", ""]])
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/header.xml", '<?xml version="1.0" encoding="UTF-8"?><hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"/>')
        for index, parts in enumerate((front, body)):
            xml = "".join(_p(t) for t in parts) + (eval_table if index == 1 else "")
            z.writestr(f"Contents/section{index}.xml", f'<?xml version="1.0" encoding="UTF-8"?><hp:sec xmlns:hp="{HP}">{xml}</hp:sec>')
    return path


class ManuscriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.path = write_manuscript(Path(cls.folder.name) / "원고_LM1203020201_24v3.hwpx")
        cls.result = suggest_manuscript(cls.path)
        cls.cards = {c["자리"]: c for part in cls.result["구성"] for c in part["문장"]}

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def first(self, where: str) -> str:
        return self.cards[where]["후보"][0]["문장"]

    def test_cards_by_part_in_order(self):
        self.assertEqual([p["구성"] for p in self.result["구성"]], ["학습모듈의 개요", "차례", "필요 지식", "수행 내용", "교수·학습 방법", "평가"])
        self.assertEqual(self.first("학습모듈의 목표"), "요구사항을 수집하고 분석할 수 있다.")
        self.assertEqual(self.first("차례 학습 1"), "요구사항 수집하기")
        self.assertEqual(self.first("차례 1-1"), "요구사항 수집")
        self.assertNotIn("차례 1-2", self.cards)
        self.assertEqual(self.first("1-1 학습 목표 2"), "이해관계자를 식별할 수 있다.")
        self.assertEqual(self.first("1-1 수행 내용 제목"), "요구사항 수집하기")
        self.assertEqual(self.first("1-1 수행 내용 수행 순서 1"), "요구사항을 확인한다.")
        self.assertEqual(self.cards["1-1 수행 내용 수행 순서 1"]["앞 번호"], "[1]")
        self.assertEqual(self.first("학습 1 교수 방법 1"), "사례를 중심으로 설명한다.")
        self.assertEqual(self.first("학습 1 학습 방법 1"), "직접 요구사항을 정리한다.")
        self.assertEqual(self.first("평가 표 요구사항 수집 · 평가 항목 1"), "요구사항 수집 능력")

    def test_only_level1_steps_and_examples(self):
        self.assertFalse(any("세부 설명" in c["원문"] for c in self.cards.values()))   # 하위 번호 줄은 보지 않는다
        examples = self.cards["학습 1 교수 방법 1"]["참고 예문"]
        self.assertEqual(examples[0]["문장"], "절차를 단계별로 설명한다.")

    def test_summary_and_ai_state(self):
        summary = self.result["요약"]
        self.assertEqual(summary["규칙 위반"], len(self.cards))
        self.assertEqual(summary["추천 없음"], 0)
        self.assertEqual(self.result["AI"]["상태"], "AI 미사용 — 요청하지 않음")
        self.assertEqual(len({c["번호"] for c in self.cards.values()}), len(self.cards))

    def test_ai_requested_but_blocked_asks_nothing(self):
        result = suggest_manuscript(self.path, use_llm=True)
        self.assertTrue(result["AI"]["상태"].startswith("AI 미사용"))
        self.assertEqual((result["AI"]["물은 문장 수"], result["AI"]["호출"]), (0, 0))
        self.assertEqual(result["요약"]["규칙 위반"], len(self.cards))            # 규칙 결과는 그대로

    def test_ai_injected_for_manuscript(self):
        asker, calls = fake()
        result = suggest_manuscript(self.path, use_llm=True, asker=asker)
        self.assertEqual(result["AI"]["물은 문장 수"], result["요약"]["검사한 문장"] - result["요약"]["확인 필요"])   # 걸린 문장 + 규정에 맞는 문장
        self.assertEqual(result["AI"]["호출"], len(calls))
        self.assertLess(len(calls), result["AI"]["물은 문장 수"])                # 같은 종류끼리 묶어 묻는다
        self.assertEqual(result["요약"]["표현 확인(AI)"], 0)

    def test_cli(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(out):
            target = Path(folder) / "결과.json"
            self.assertEqual(main([str(self.path), "--json", str(target)]), 0)
            saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(saved["원고"], self.path.name)
        self.assertIn("요구사항 수집하기", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--sentence", "절차를 설명함.", "--kind", "교수 방법"]), 0)
        self.assertIn("1. 절차를 설명한다.", out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(Path(self.folder.name) / "없는.hwpx")]), 1)


if __name__ == "__main__":
    unittest.main()
