"""원고 문장 추천(ncs_suggest, REQ-02-004): 종류별 규정 꼴(출력 검증용), 참고 예문, AI 판정·후보 검증(가짜 응답 주입 — 순위 재부여·
버림·종결형 오지적의 사유 바꿈·번호 검증), AI 미설정(판단불가), 원고 전체(합성 hwpx), CLI,
문맥(자리·앞뒤 문장)과 참고 문장을 붙인 질문, 참고 문장 묶음(만들기·읽기·찾기)과 후보의 근거 문장·순위, 후보문장표.

실제 원고(samples/, git 제외)를 실제 LLM으로 돌린 결과는 README의 문장 추천 단락에 적는다. 테스트는 실제 호출을 하지 않는다.
"""

import contextlib
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape

from ncs_core.llm import LlmError
from ncs_suggest import KINDS, Corpus, Reference, candidate_table, suggest_manuscript, suggest_sentence
from ncs_suggest import corpus as corpus_module
from ncs_suggest.__main__ import main
from ncs_suggest.config import DEFAULT_CONFIG, NO_FINDING, SOURCE_AI, UNDECIDED
from ncs_suggest.examples import similar
from ncs_suggest.extract import split_prefix
from ncs_suggest.kinds import check
from ncs_suggest.llm_suggest import ask_lines, prompt, validate
from ncs_suggest.pipeline import table_columns

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
BOX1, BOX2 = "\U000F02B1", "\U000F02B2"   # 네모 번호 [1] [2] 글자


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
        self.assertTrue(check("평가 항목", "요구사항의 이해")[0])               # 그 밖의 명사형은 막지 않는다
        self.assertTrue(check("학습명", "요구사항 수집하기")[0])
        self.assertFalse(check("학습명", "요구사항 수집하기기")[0])
        self.assertTrue(check("학습 내용명", "요구사항 수집")[0])
        self.assertFalse(check("학습 내용명", "요구사항 수집하기")[0])
        self.assertIsNone(check("학습 내용명", "요구사항 성능")[0])               # 목록에 없는 낱말 — 확인 못 함
        with self.assertRaises(ValueError):
            check("없는 종류", "문장")

    def test_examples_and_prefix(self):
        pool = [("절차를 단계별로 설명한다.", "학습 1 교수 방법 2"), ("실습 장비를 준비한다.", "학습 1 교수 방법 3")]
        self.assertEqual(similar("절차를 단계별로 설명함.", pool)[0]["자리"], "학습 1 교수 방법 2")
        self.assertEqual(split_prefix(BOX1 + " 요구사항을 확인한다."), ("[1]", "요구사항을 확인한다."))
        self.assertEqual(split_prefix("• 사례를 설명한다."), ("•", "사례를 설명한다."))
        self.assertEqual(split_prefix("󰊱 요구사항을 확인한다."), ("[1]", "요구사항을 확인한다."))   # hwp 서로게이트
        self.assertEqual(set(KINDS), {"학습 목표", "수행 순서", "교수 방법", "학습 방법", "안전·유의 사항", "평가 항목", "학습명", "수행 내용 제목", "학습 내용명"})


class ValidateTests(unittest.TestCase):
    def test_bad_candidates_have_reasons(self):
        body = "사례 중심으로 절차를 설명함."
        cases = [
            ("사례 중심으로 절차를 설명함.", "같음"),                              # 원문 그대로
            ("사례 중심으로 절차를 설명할 수 있다.", "규정 꼴"),                     # 교수 방법은 '~한다.'만
            ("사례 중심으로 절차를 3단계로 설명한다.", "수치"),                    # 새 수치
            ("사례 중심으로 Agile 절차를 설명한다.", "영문"),                      # 새 영문
            ("학습자가 현장 전문가와 협업 프로젝트를 수행하도록 지도한다.", "너무 다름"),   # 내용을 바꿈
        ]
        for text, why in cases:
            with self.subTest(text=text):
                self.assertIn(why, validate("교수 방법", body, text))
        self.assertIsNone(validate("교수 방법", body, "사례 중심으로 절차를 설명한다."))

    def test_brand(self):
        self.assertIn("상호", validate("교수 방법", "프로그램으로 표를 작성함.", "엑셀로 표를 작성한다."))
        self.assertIsNone(validate("교수 방법", "프로그램으로 표를 작성함.", "프로그램으로 표를 작성한다."))


def finding(line, kind="종결형 위반", reason="종결이 규정과 다름", suggestions=()):
    return {"line": line, "kind": kind, "reason": reason, "suggestions": list(suggestions)}


def fake(findings=None, model="fake-model"):
    """가짜 LLM — findings가 함수면 (종류, 문장 목록) → 지적 목록, 아니면 그대로 돌려준다. 받은 질문을 calls에 남긴다."""
    calls = []

    def asker(kind, bodies):
        calls.append((kind, list(bodies)))
        found = findings(kind, bodies) if callable(findings) else list(findings or [])
        return {"data": {"findings": found}, "model": model}

    return asker, calls


class AiTests(unittest.TestCase):
    """AI 판정과 후보 검증 — 가짜 응답으로만 검사한다(실제 호출 없음)."""

    def test_prompt_has_kind_form_and_numbered_lines(self):
        text = prompt("교수 방법", ["절차를 설명함.", "사례를 든다."])
        self.assertIn("[문장 종류] 교수 방법 — 규정 꼴: ~한다.", text)
        self.assertIn("1. 절차를 설명함.\n2. 사례를 든다.", text)

    def test_candidates_are_screened_and_reranked(self):
        asker, calls = fake([finding(1, suggestions=["사례 중심으로 절차를 3단계로 설명한다.", "사례 중심으로 절차를 설명한다.",
                                                     "사례 중심으로 절차를 설명한다.", "사례를 중심으로 절차를 설명한다."])])
        result = suggest_sentence("• 사례 중심으로 절차를 설명함.", "교수 방법", asker=asker)
        self.assertEqual(calls, [("교수 방법", ["사례 중심으로 절차를 설명함."])])        # 번호·글머리 뗀 문장 줄만 보낸다
        self.assertEqual(result["상태"], "종결형 위반")
        self.assertEqual(result["앞 번호"], "•")
        self.assertEqual([(c["순위"], c["문장"]) for c in result["후보"]],
                         [(1, "사례 중심으로 절차를 설명한다."), (2, "사례를 중심으로 절차를 설명한다.")])   # 버린 1순위 뒤로 다시 매김
        self.assertEqual({c["출처"] for c in result["후보"]}, {SOURCE_AI})
        self.assertEqual(result["후보"][0]["근거"], ["종결이 규정과 다름", "규칙 재검사 통과"])
        self.assertIn("수치", result["버린 AI 후보"][0]["이유"])
        self.assertTrue(result["AI"].startswith("AI 사용(fake-model) · 호출 1번, 문장 1개"))

    def test_at_most_five_candidates(self):
        many = [f"절차를 단계별로 {word}." for word in ("설명한다", "안내한다", "제시한다", "정리한다", "소개한다", "시연한다")]
        asker, _ = fake([finding(1, "어색한 낱말", suggestions=many)])
        result = suggest_sentence("절차를 단계별로 저격한다.", "교수 방법", asker=asker)
        self.assertEqual(len(result["후보"]), DEFAULT_CONFIG.max_candidates)
        self.assertEqual(result["상태"], "어색한 낱말")

    def test_no_usable_candidate_is_honest(self):
        asker, _ = fake([finding(1, "어색한 낱말", suggestions=["절차를 5단계로 설명한다."])])
        result = suggest_sentence("절차를 단계별로 저격한다.", "교수 방법", asker=asker)
        self.assertEqual(result["후보"], [])
        self.assertTrue(result["추천 없음"].startswith("추천 없음(사람이 고쳐야 함)"))
        self.assertIn("수치", result["버린 AI 후보"][0]["이유"])

    def test_ending_claim_on_compliant_sentence_is_relabeled(self):
        asker, _ = fake([finding(1, reason="'명한다'는 끝말 오류", suggestions=["절차를 단계별로 설명한다."])])
        result = suggest_sentence("절차를 단계별로 명한다.", "교수 방법", asker=asker)
        self.assertEqual(result["상태"], "기타 표현")                            # 끝말은 '~한다.'로 규정 꼴에 맞다
        self.assertIn("끝말은 규정 꼴에 맞음", result["사유"][0])
        self.assertEqual([c["문장"] for c in result["후보"]], ["절차를 단계별로 설명한다."])

    def test_numbers_and_unknown_kind_are_checked(self):
        flagged, rejected, model = ask_lines("교수 방법", ["절차를 설명함.", "사례를 든다."], asker=fake([
            finding(9, suggestions=["x"]), finding("둘", suggestions=["x"]), {"line": 1, "kind": "이상한 유형", "reason": "", "suggestions": "절차를 설명한다."},
            finding(1, suggestions=["두 번째 답"])])[0])
        self.assertEqual(sorted(flagged), [0])
        self.assertEqual((flagged[0]["kind"], [c["문장"] for c in flagged[0]["후보"]]), ("기타 표현", ["절차를 설명한다."]))
        self.assertEqual((rejected, model), ([], "fake-model"))

    def test_no_finding_and_failure(self):
        asker, _ = fake([])
        self.assertEqual(suggest_sentence("절차를 단계별로 설명한다.", "교수 방법", asker=asker)["상태"], NO_FINDING)

        def broken(kind, bodies):
            raise LlmError("연결 실패")

        failed = suggest_sentence("절차를 설명함.", "교수 방법", asker=broken)
        self.assertEqual((failed["상태"], failed["후보"]), (UNDECIDED, []))
        self.assertIn("AI 호출 실패: 연결 실패", failed["사유"][0])

    def test_not_configured_is_undecided_without_rule_fallback(self):
        result = suggest_sentence("절차를 설명함.", "교수 방법")   # 테스트 환경에는 키·승인이 없다
        self.assertEqual((result["상태"], result["후보"]), (UNDECIDED, []))
        self.assertTrue(result["AI"].startswith("AI 미설정"), result["AI"])
        self.assertEqual(result["사유"], [result["AI"]])

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            suggest_sentence("문장", "없는 종류")
        with self.assertRaises(ValueError):
            suggest_sentence("  ", "교수 방법")


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


# 합성 원고에서 가짜 LLM이 고칠 문장과 1순위 후보
FIXES = {
    "학습자는 요구사항을 수집하고 분석한다.": "요구사항을 수집하고 분석할 수 있다.",
    "요구사항 수집함": "요구사항 수집하기",
    "학습자는 이해관계자를 식별할 수 있다.": "이해관계자를 식별할 수 있다.",
    "요구사항을 확인": "요구사항을 확인한다.",
    "사례를 중심으로 설명함.": "사례를 중심으로 설명한다.",
    "직접 요구사항을 정리하세요.": "직접 요구사항을 정리한다.",
    "요구사항 수집 능력.": "요구사항 수집 능력",
}


def fixing(kind, bodies):
    return [finding(no, suggestions=[FIXES[body]]) for no, body in enumerate(bodies, 1) if body in FIXES]


class ManuscriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.path = write_manuscript(Path(cls.folder.name) / "원고_LM1203020201_24v3.hwpx")
        cls.asker, cls.calls = fake(fixing)
        cls.result = suggest_manuscript(cls.path, asker=cls.asker)
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
        self.assertEqual(self.first("1-1 학습 목표 2"), "이해관계자를 식별할 수 있다.")
        self.assertEqual(self.first("1-1 수행 내용 제목"), "요구사항 수집하기")
        self.assertEqual(self.first("1-1 수행 내용 수행 순서 1"), "요구사항을 확인한다.")
        self.assertEqual(self.cards["1-1 수행 내용 수행 순서 1"]["앞 번호"], "[1]")
        self.assertEqual(self.first("학습 1 교수 방법 1"), "사례를 중심으로 설명한다.")
        self.assertEqual(self.first("평가 표 요구사항 수집 · 평가 항목 1"), "요구사항 수집 능력")
        self.assertNotIn("차례 1-2", self.cards)                                  # AI가 지적하지 않은 문장은 카드가 없다

    def test_same_kind_batched_and_lines_only(self):
        self.assertEqual(self.result["AI"]["호출"], len(self.calls))
        self.assertEqual(self.result["AI"]["물은 문장 수"], self.result["요약"]["검사한 문장"])
        self.assertLess(len(self.calls), self.result["AI"]["물은 문장 수"])        # 같은 종류끼리 묶어 묻는다
        self.assertFalse(any("세부 설명" in b for _, bodies in self.calls for b in bodies))   # 하위 번호 줄은 보내지 않는다

    def test_examples_come_from_unflagged_sentences(self):
        examples = self.cards["학습 1 교수 방법 1"]["참고 예문"]
        self.assertEqual(examples[0]["문장"], "절차를 단계별로 설명한다.")

    def test_summary(self):
        summary = self.result["요약"]
        self.assertEqual((summary["고칠 문장"], summary["사유별"]), (len(FIXES) + 1, {"종결형 위반": len(FIXES) + 1}))   # 수행 내용 제목·차례가 같은 글
        self.assertEqual((summary["추천 있음"], summary["추천 없음"], summary["버린 AI 후보"]), (len(self.cards), 0, 0))
        self.assertEqual(len({c["번호"] for c in self.cards.values()}), len(self.cards))

    def test_budget_limits_sentences_sent(self):
        from ncs_suggest.config import SuggestConfig

        asker, calls = fake([])
        result = suggest_manuscript(self.path, asker=asker, config=SuggestConfig(llm_max_sentences=3, llm_batch=2))
        self.assertEqual(sum(len(bodies) for _, bodies in calls), 3)
        self.assertTrue(any("AI에 묻지 못한 문장" in note for note in result["알림"]))

    def test_not_configured_gives_no_cards(self):
        result = suggest_manuscript(self.path)                 # 테스트 환경에는 키·승인이 없다
        self.assertTrue(result["AI"]["상태"].startswith("AI 미설정"))
        self.assertEqual((result["구성"], result["AI"]["호출"]), ([], 0))
        self.assertGreater(result["요약"]["검사한 문장"], 0)
        self.assertTrue(any("판단불가" in note for note in result["알림"]))

    def test_cli(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(out):
            target = Path(folder) / "결과.json"
            self.assertEqual(main([str(self.path), "--json", str(target)]), 0)
            saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(saved["원고"], self.path.name)
        self.assertIn("AI 미설정", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--sentence", "절차를 설명함.", "--kind", "교수 방법"]), 0)
        self.assertIn("판단불가", out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(Path(self.folder.name) / "없는.hwpx")]), 1)


REFS = Corpus([
    Reference("교수 방법", "사례를 중심으로 절차를 설명한다.", "기존모듈A.hwpx", "학습 1 교수 방법 1"),
    Reference("교수 방법", "실습 장비의 사용법을 시연한다.", "기존모듈A.hwpx", "학습 2 교수 방법 3"),
    Reference(corpus_module.ACTION_COMMON, "점검표를 작성하여 결과를 기록한다.", "우수사례집.hwp", "구역 1"),
    Reference("학습 목표", "요구사항을 수집할 수 있다.", "기존모듈B.hwpx", "1-1 학습 목표 1"),
], name="테스트 묶음")


class ContextPromptTests(unittest.TestCase):
    """문맥(자리·앞뒤 문장)과 참고 문장이 질문에 붙는가 — 요구사항 '문맥의 흐름을 고려하여'."""

    def test_prompt_adds_context_and_reference_lines(self):
        text = prompt("교수 방법", ["절차를 설명함.", "사례를 든다."],
                      contexts=[{"자리": "학습 1 교수 방법 1", "앞": "", "뒤": "사례를 든다."}, {"자리": "", "앞": "", "뒤": ""}],
                      references=[[{"문장": "사례를 중심으로 절차를 설명한다."}], []])
        self.assertIn("1. 절차를 설명함.\n   문맥 — 자리: 학습 1 교수 방법 1 | 뒤 문장: 사례를 든다.\n   참고 문장 — 「사례를 중심으로 절차를 설명한다.」\n2. 사례를 든다.", text)
        self.assertTrue(text.endswith("2. 사례를 든다."))                         # 빈 문맥·참고 문장은 줄을 만들지 않는다

    def test_context_is_cut_and_can_be_turned_off(self):
        from ncs_suggest.config import SuggestConfig

        contexts = [{"자리": "학습 1", "앞": "가" * 300, "뒤": ""}]
        self.assertIn("앞 문장: " + "가" * 120 + "…", prompt("교수 방법", ["절차를 설명함."], contexts=contexts))
        self.assertNotIn("문맥", prompt("교수 방법", ["절차를 설명함."], contexts=contexts, config=SuggestConfig(context_chars=0)))

    def test_pipeline_sends_neighbours_and_references(self):
        seen = []

        def spy(kind, bodies, **kwargs):
            seen.append((kind, bodies, kwargs["contexts"], kwargs["references"]))
            return {}, [], "spy"

        with tempfile.TemporaryDirectory() as folder, mock.patch("ncs_suggest.pipeline.ask_lines", spy):
            suggest_manuscript(write_manuscript(Path(folder) / "원고_LM1203020201_24v3.hwpx"), asker=lambda *a: None, corpus=REFS)
        kind, bodies, contexts, references = next(item for item in seen if item[0] == "교수 방법")
        self.assertEqual(bodies, ["사례를 중심으로 설명함.", "절차를 단계별로 설명한다."])
        self.assertEqual(contexts, [{"자리": "학습 1 교수 방법 1", "앞": "", "뒤": ""}, {"자리": "학습 1 교수 방법 2", "앞": "", "뒤": ""}])   # 이웃이 같은 질문에 있으면 자리만
        self.assertEqual(references[0][0]["출처"], "기존모듈A.hwpx")

    def test_neighbours_are_written_when_the_batch_splits_them(self):
        from ncs_suggest.config import SuggestConfig

        seen = []

        def spy(kind, bodies, **kwargs):
            seen.append((kind, bodies, kwargs["contexts"]))
            return {}, [], "spy"

        with tempfile.TemporaryDirectory() as folder, mock.patch("ncs_suggest.pipeline.ask_lines", spy):
            suggest_manuscript(write_manuscript(Path(folder) / "원고_LM1203020201_24v3.hwpx"), asker=lambda *a: None, corpus=REFS,
                               config=SuggestConfig(llm_batch=1))
        teach = [contexts[0] for kind, _, contexts in seen if kind == "교수 방법"]
        self.assertEqual(teach[0], {"자리": "학습 1 교수 방법 1", "앞": "", "뒤": "절차를 단계별로 설명한다."})   # 글머리는 뗀다
        self.assertEqual(teach[1]["앞"], "사례를 중심으로 설명함.")
        steps = [contexts[0] for kind, _, contexts in seen if kind == "수행 순서"]
        self.assertEqual(steps[0]["뒤"], "이해관계자를 식별한다.")                 # 하위 번호 줄이 아니라 다음 네모 번호 줄(번호 글자는 뗀다)

    def test_direct_input_has_no_place_context(self):
        seen = []

        def spy(kind, bodies, **kwargs):
            seen.append(kwargs["contexts"])
            return {}, [], "spy"

        with mock.patch("ncs_suggest.pipeline.ask_lines", spy):
            suggest_sentence("절차를 설명함.", "교수 방법", asker=lambda *a: None, corpus=REFS)
        self.assertEqual(seen, [[{"자리": "", "앞": "", "뒤": ""}]])


class CorpusTests(unittest.TestCase):
    """참고 문장 묶음 — 요구사항 수행예시 (1-3) '근거 있는 문장(기존 학습모듈·공공저작물) 기반 정정 후보'."""

    def test_find_same_kind_and_common_action_sentences(self):
        found = REFS.find("교수 방법", "사례 중심으로 절차를 설명한다.", limit=2, minimum=0.35)
        self.assertEqual((found[0]["문장"], found[0]["출처"], found[0]["자리"]), ("사례를 중심으로 절차를 설명한다.", "기존모듈A.hwpx", "학습 1 교수 방법 1"))
        self.assertGreater(found[0]["유사도"], 0.9)
        self.assertEqual(REFS.find("학습 방법", "점검표를 작성하여 결과를 기록한다.", limit=1, minimum=0.5)[0]["출처"], "우수사례집.hwp")   # 종류 모르는 '~한다.' 문장
        self.assertEqual(REFS.find("학습 목표", "점검표를 작성하여 결과를 기록한다.", limit=1, minimum=0.5), [])                       # 다른 종류에는 쓰지 않는다
        self.assertEqual(REFS.find("평가 항목", "요구사항 수집 능력", limit=1, minimum=0.1), [])
        self.assertEqual(len(REFS), 4)

    def test_candidates_get_basis_and_grounded_ones_rank_first(self):
        from ncs_suggest.config import SuggestConfig

        asker, _ = fake([finding(1, suggestions=["사례 중심으로 절차를 안내한다.", "사례 중심으로 절차를 설명한다."])])
        result = suggest_sentence("사례 중심으로 절차를 설명함.", "교수 방법", asker=asker, corpus=REFS, config=SuggestConfig(ground_min=0.9))
        first, second = result["후보"]
        self.assertEqual((first["순위"], first["문장"]), (1, "사례 중심으로 절차를 설명한다."))      # AI는 2순위로 냈지만 근거 문장이 있어 앞으로
        self.assertEqual(first["근거 문장"]["출처"], "기존모듈A.hwpx")
        self.assertEqual((second["순위"], second["근거 문장"]), (2, None))                         # 비슷한 참고 문장이 없으면 근거 없음
        self.assertEqual(first["출처"], SOURCE_AI)                                                # 후보를 쓴 것은 여전히 AI
        self.assertTrue(result["참고 문장"].startswith("참고 문장 4개(테스트 묶음)"))

    def test_without_corpus_order_is_unchanged_and_noted(self):
        asker, _ = fake([finding(1, suggestions=["사례 중심으로 절차를 안내한다.", "사례 중심으로 절차를 설명한다."])])
        result = suggest_sentence("사례 중심으로 절차를 설명함.", "교수 방법", asker=asker)
        self.assertEqual([c["문장"] for c in result["후보"]], ["사례 중심으로 절차를 안내한다.", "사례 중심으로 절차를 설명한다."])
        self.assertEqual([c["근거 문장"] for c in result["후보"]], [None, None])
        self.assertTrue(result["참고 문장"].startswith("참고 문장 묶음 없음"))

    def test_build_from_manuscript_keeps_only_compliant_sentences(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out:
            source = write_manuscript(Path(folder) / "원고_LM1203020201_24v3.hwpx")
            target = Path(folder) / "기준정보" / corpus_module.REFS_FILE
            self.assertEqual(corpus_module.main([str(source), "--out", str(target)]), 0)
            built = corpus_module.load(target)
            texts = {ref.text for pool in built.by_kind.values() for ref, _ in pool}
            self.assertIn("절차를 단계별로 설명한다.", texts)                 # 규정 꼴을 지킨 교수 방법
            self.assertIn("요구사항을 수집할 수 있다.", texts)
            self.assertNotIn("사례를 중심으로 설명함.", texts)                # 어긴 문장은 싣지 않는다
            self.assertNotIn("학습자는 이해관계자를 식별할 수 있다.", texts)
            self.assertNotIn(corpus_module.ACTION_COMMON, built.by_kind)     # --loose 없이는 구조로 읽은 문장만
            count = len(built)
            self.assertEqual(corpus_module.main([str(source), "--out", str(target), "--loose"]), 0)   # 다시 넣어도 같은 문장은 한 번만
            again = corpus_module.load(target)
            self.assertEqual(sum(n for kind, n in again.counts().items() if kind != corpus_module.ACTION_COMMON), count)
            self.assertIn("요구사항을 분류한다.", {ref.text for ref, _ in again.by_kind[corpus_module.ACTION_COMMON]})   # 구조 밖 '~한다.' 문단
            self.assertEqual(again.name, corpus_module.REFS_FILE)
        self.assertIn("저장:", out.getvalue())

    def test_load_reads_env_file_and_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "refs.tsv"
            target.write_text("# 주석\n교수 방법\t절차를 설명한다.\t모듈.hwpx\t학습 1\n없는 종류\t문장\t\t\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"NCS_SUGGEST_REFS": str(target)}):
                self.assertEqual(corpus_module.load().counts(), {"교수 방법": 1})
            with mock.patch.dict("os.environ", {"NCS_SUGGEST_REFS": str(Path(folder) / "없음.tsv")}):
                self.assertEqual(len(corpus_module.load()), 0)
        self.assertEqual(len(corpus_module.load()), 0)                       # 테스트 환경에는 기준정보 폴더가 없다
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(corpus_module.main(["없는.hwpx"]), 1)            # 쓸 곳이 없음


class CandidateTableTests(unittest.TestCase):
    """산출물 '문장 정정 필요 후보문장표' — (변경 필요 원본 문장) ⇄ (문장 정정 후보군) 5순위까지."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.path = write_manuscript(Path(cls.folder.name) / "원고_LM1203020201_24v3.hwpx")
        cls.result = suggest_manuscript(cls.path, asker=fake(fixing)[0], corpus=REFS)
        cls.rows = candidate_table(cls.result)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_one_row_per_card_with_five_ranked_columns(self):
        self.assertEqual(len(self.rows), self.result["요약"]["고칠 문장"])
        row = next(r for r in self.rows if r["자리"] == "1-1 수행 내용 수행 순서 1")
        self.assertEqual((row["변경 필요 원본 문장"], row["정정 후보 1순위"]), ("[1] 요구사항을 확인", "[1] 요구사항을 확인한다."))   # 앞 번호를 다시 붙인다
        self.assertEqual([row[f"정정 후보 {n}순위"] for n in range(2, 6)], ["", "", "", ""])
        self.assertEqual((row["원고"], row["사유 유형"], row["규정 꼴"]), (self.path.name, "종결형 위반", KINDS["수행 순서"]))
        teach = next(r for r in self.rows if r["자리"] == "학습 1 교수 방법 1")
        self.assertIn("기존모듈A.hwpx", teach["근거 문장 1순위"])                # '사례를 중심으로 절차를 설명한다.'와 비슷
        goal = next(r for r in self.rows if r["자리"] == "1-1 학습 목표 2")
        self.assertEqual(goal["근거 문장 1순위"], "")                            # 비슷한 참고 문장이 없으면 빈칸
        self.assertEqual(self.result["요약"]["후보"], len(self.rows))
        self.assertGreaterEqual(self.result["요약"]["근거 문장 있는 후보"], 1)
        self.assertEqual(self.result["참고 문장"]["문장 수"], 4)

    def test_single_card_and_cli_csv(self):
        card = suggest_sentence("• 사례 중심으로 절차를 설명함.", "교수 방법", corpus=REFS,
                                asker=fake([finding(1, suggestions=["사례 중심으로 절차를 설명한다."])])[0])
        (row,) = candidate_table(card)
        self.assertEqual((row["원고"], row["정정 후보 1순위"]), ("", "• 사례 중심으로 절차를 설명한다."))
        self.assertIn("「사례를 중심으로 절차를 설명한다.」 (기존모듈A.hwpx, 학습 1 교수 방법 1, 유사도", row["근거 문장 1순위"])
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out:
            target = Path(folder) / "표" / "후보문장표.csv"
            self.assertEqual(main([str(self.path), "--csv", str(target)]), 0)   # AI 미설정 — 행 없이 머리글만
            self.assertEqual(target.read_text(encoding="utf-8-sig").strip().split(","), table_columns())
        self.assertIn("후보문장표 0행", out.getvalue())

    def test_csv_columns_open_in_spreadsheet(self):
        self.assertEqual(list(self.rows[0]), table_columns())
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=table_columns())
        writer.writeheader()
        writer.writerows(self.rows)
        head = buffer.getvalue().splitlines()[0].split(",")
        self.assertEqual(head[:9], ["번호", "원고", "구성", "자리", "종류", "규정 꼴", "변경 필요 원본 문장", "사유 유형", "사유"])
        self.assertEqual(head[9:], [f"{name} {n}순위" for n in range(1, 6) for name in ("정정 후보", "근거 문장")] + ["비고"])


if __name__ == "__main__":
    unittest.main()
