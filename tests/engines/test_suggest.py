"""원고 문장 추천(ncs_suggest, REQ-02-004): 종류별 규정 꼴(출력 검증용), 참고 예문, AI 판정·후보 검증(가짜 Claude 주입 — 순위 재부여·
버림·종결형 오지적의 사유 바꿈·번호 검증, 원고 블록 하나·잘리면 나눠 다시), AI 미설정(판단불가), 원고 전체(합성 hwpx), CLI.

실제 원고(samples/, git 제외)를 실제 LLM으로 돌린 결과는 README의 문장 추천 단락에 적는다. 테스트는 실제 호출을 하지 않는다.
"""

import contextlib
import io
import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from ncs_llmreview.claude import ClaudeError
from ncs_suggest import KINDS, suggest_manuscript, suggest_sentence
from ncs_suggest.__main__ import main
from ncs_suggest.config import DEFAULT_CONFIG, NO_FINDING, SOURCE_AI, UNDECIDED
from ncs_suggest.examples import similar
from ncs_suggest.extract import split_prefix
from ncs_suggest.kinds import check
from ncs_suggest.llm_suggest import build_request, build_system, document_text, out_schema, parse, validate

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


REQUEST_LINE = re.compile(r"^- (.+?) \(규정 꼴: .*\): 문장 \[(\d+)\](?:~\[(\d+)\])?$", re.M)


def asked_of(document, request):
    """요청 블록이 묻는 [(종류, [(문장 번호, 본문)])] — 본문은 원고 블록에서 찾는다."""
    bodies = {int(n): body for n, body in re.findall(r"^\[(\d+)\] (.*)$", document, re.M)}
    out = []
    for kind, first, last in REQUEST_LINE.findall(request):
        numbers = range(int(first), int(last or first) + 1)
        out.append((kind, [(n, bodies[n]) for n in numbers]))
    return out


def fake(findings=None, model="fake-model"):
    """가짜 Claude(generate) — findings가 함수면 종류마다 (종류, 문장 목록) → 그 목록 안 번호(1부터)의 지적 목록을 받아 원고 블록 번호로
    바꿔 돌려주고, 아니면 그대로 돌려준다. 호출마다 [(종류, 문장 목록)]을 calls에 남긴다."""
    calls = []

    def generate(system, document, request, *, task, tasks=None, out_schema=None):
        assert task == "sentence_suggest" and out_schema["required"] == ["findings"]
        asked = asked_of(document, request)
        calls.append([(kind, [body for _, body in pairs]) for kind, pairs in asked])
        if not callable(findings):
            return {"data": {"findings": list(findings or [])}, "model": model, "cached": False, "usage": {"input": 500, "output": 50}}
        found = []
        for kind, pairs in asked:
            for item in findings(kind, [body for _, body in pairs]):
                line = item["line"]
                found.append({**item, "line": pairs[line - 1][0] if isinstance(line, int) and 1 <= line <= len(pairs) else line})
        return {"data": {"findings": found}, "model": model, "cached": False, "usage": {"input": 500, "output": 50}}

    return generate, calls


class AiTests(unittest.TestCase):
    """AI 판정과 후보 검증 — 가짜 응답으로만 검사한다(실제 호출 없음)."""

    def test_document_has_kinds_forms_and_numbered_lines_once(self):
        text = document_text({1: ("교수 방법", "절차를 설명함."), 2: ("교수 방법", "사례를 든다."), 3: ("평가 항목", "분석 능력.")})
        self.assertIn("## 교수 방법 (규정 꼴: ~한다.)\n[1] 절차를 설명함.\n[2] 사례를 든다.", text)
        self.assertIn("## 평가 항목 (규정 꼴: ~여부 / ~능력 / ~수준 / ~정도 (마침표 없이))\n[3] 분석 능력.", text)
        request = build_request([("교수 방법", [1, 2]), ("평가 항목", [3])])
        self.assertIn("- 교수 방법 (규정 꼴: ~한다.): 문장 [1]~[2]", request)
        self.assertTrue(request.endswith("문장 [3]"))
        self.assertIn("안긴 문장의 주어는 군더더기가 아닙니다", build_system())
        item = out_schema()["properties"]["findings"]["items"]
        self.assertEqual((set(item["required"]), item["additionalProperties"]), (set(item["properties"]), False))

    def test_candidates_are_screened_and_reranked(self):
        asker, calls = fake([finding(1, suggestions=["사례 중심으로 절차를 3단계로 설명한다.", "사례 중심으로 절차를 설명한다.",
                                                     "사례 중심으로 절차를 설명한다.", "사례를 중심으로 절차를 설명한다."])])
        result = suggest_sentence("• 사례 중심으로 절차를 설명함.", "교수 방법", generate=asker)
        self.assertEqual(calls, [[("교수 방법", ["사례 중심으로 절차를 설명함."])]])      # 번호·글머리 뗀 문장 줄만 보낸다
        self.assertEqual(result["상태"], "종결형 위반")
        self.assertEqual(result["앞 번호"], "•")
        self.assertEqual([(c["순위"], c["문장"]) for c in result["후보"]],
                         [(1, "사례 중심으로 절차를 설명한다."), (2, "사례를 중심으로 절차를 설명한다.")])   # 버린 1순위 뒤로 다시 매김
        self.assertEqual({c["출처"] for c in result["후보"]}, {SOURCE_AI})
        self.assertEqual(result["후보"][0]["근거"], ["종결이 규정과 다름", "규칙 재검사 통과"])
        self.assertIn("수치", result["버린 AI 후보"][0]["이유"])
        self.assertTrue(result["AI"].startswith("AI 사용(fake-model) · 호출 1번(새 호출 1번), 문장 1개 · 입력 500"), result["AI"])

    def test_at_most_five_candidates(self):
        many = [f"절차를 단계별로 {word}." for word in ("설명한다", "안내한다", "제시한다", "정리한다", "소개한다", "시연한다")]
        asker, _ = fake([finding(1, "어색한 낱말", suggestions=many)])
        result = suggest_sentence("절차를 단계별로 저격한다.", "교수 방법", generate=asker)
        self.assertEqual(len(result["후보"]), DEFAULT_CONFIG.max_candidates)
        self.assertEqual(result["상태"], "어색한 낱말")

    def test_no_usable_candidate_is_honest(self):
        asker, _ = fake([finding(1, "어색한 낱말", suggestions=["절차를 5단계로 설명한다."])])
        result = suggest_sentence("절차를 단계별로 저격한다.", "교수 방법", generate=asker)
        self.assertEqual(result["후보"], [])
        self.assertTrue(result["추천 없음"].startswith("추천 없음(사람이 고쳐야 함)"))
        self.assertIn("수치", result["버린 AI 후보"][0]["이유"])

    def test_ending_claim_on_compliant_sentence_is_relabeled(self):
        asker, _ = fake([finding(1, reason="'명한다'는 끝말 오류", suggestions=["절차를 단계별로 설명한다."])])
        result = suggest_sentence("절차를 단계별로 명한다.", "교수 방법", generate=asker)
        self.assertEqual(result["상태"], "기타 표현")                            # 끝말은 '~한다.'로 규정 꼴에 맞다
        self.assertIn("끝말은 규정 꼴에 맞음", result["사유"][0])
        self.assertEqual([c["문장"] for c in result["후보"]], ["절차를 단계별로 설명한다."])

    def test_numbers_and_unknown_kind_are_checked(self):
        asked = {4: ("교수 방법", "절차를 설명함."), 5: ("교수 방법", "사례를 든다.")}
        data = {"findings": [finding(9, suggestions=["x"]), finding("둘", suggestions=["x"]),
                             {"line": 4, "kind": "이상한 유형", "reason": "", "suggestions": "절차를 설명한다."},
                             finding(4, suggestions=["두 번째 답"])]}
        flagged, rejected, dropped = parse(data, asked, "fake-model")
        self.assertEqual((sorted(flagged), dropped), ([4], 3))                     # 묻지 않은 번호·글 번호·두 번째 답은 버림
        self.assertEqual((flagged[4]["kind"], [c["문장"] for c in flagged[4]["후보"]]), ("기타 표현", ["절차를 설명한다."]))
        self.assertEqual(rejected, [])

    def test_no_finding_and_failure(self):
        asker, _ = fake([])
        self.assertEqual(suggest_sentence("절차를 단계별로 설명한다.", "교수 방법", generate=asker)["상태"], NO_FINDING)

        def broken(system, document, request, *, task, tasks=None, out_schema=None):
            raise ClaudeError("Claude 연결 실패")

        failed = suggest_sentence("절차를 설명함.", "교수 방법", generate=broken)
        self.assertEqual((failed["상태"], failed["후보"]), (UNDECIDED, []))
        self.assertIn("AI 호출 실패: Claude 연결 실패", failed["사유"][0])

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
        cls.result = suggest_manuscript(cls.path, generate=cls.asker)
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

    def test_one_call_for_all_kinds_and_lines_only(self):
        self.assertEqual((self.result["AI"]["호출"], len(self.calls)), (1, 1))      # 종류 전부를 한 번에 묻는다
        self.assertEqual(self.result["AI"]["물은 문장 수"], self.result["요약"]["검사한 문장"])
        self.assertEqual(sum(len(bodies) for _, bodies in self.calls[0]), self.result["요약"]["검사한 문장"])
        self.assertGreater(len(self.calls[0]), 3)
        self.assertFalse(any("세부 설명" in b for _, bodies in self.calls[0] for b in bodies))   # 하위 번호 줄은 보내지 않는다
        usage = self.result["AI"]["usage"]
        self.assertEqual((usage["calls"], usage["new_calls"], usage["input"], usage["output"]), (1, 1, 500, 50))
        self.assertIn("호출 1번(새 호출 1번)", self.result["AI"]["상태"])

    def test_cut_output_is_split_by_kind_then_by_range(self):
        seen = []

        def cut(system, document, request, *, task, tasks=None, out_schema=None):
            asked = asked_of(document, request)
            seen.append((document, [(kind, [n for n, _ in pairs]) for kind, pairs in asked]))
            if len(asked) > 1 or len(asked[0][1]) > 1:
                raise ClaudeError("출력이 max_tokens에서 잘림")
            return {"data": {"findings": []}, "model": "fake-model", "cached": False, "usage": {}}

        result = suggest_manuscript(self.path, generate=cut)
        self.assertEqual(len({document for document, _ in seen}), 1)              # 원고 블록은 같다(캐시 읽기)
        answered = [group for _, group in seen if len(group) == 1 and len(group[0][1]) == 1]
        self.assertEqual(len(answered), result["요약"]["검사한 문장"])           # 결국 문장 하나씩까지 나눠 모두 물음
        self.assertEqual(result["AI"]["물은 문장 수"], result["요약"]["검사한 문장"])
        self.assertEqual(result["AI"]["실패"], 0)
        full = dict(seen[0][1])                                                   # 첫 호출 = 종류 전부, 범위 전부
        self.assertGreater(len(full), 1)
        self.assertEqual(seen[1][1], seen[0][1][: len(full) // 2])               # 먼저 종류 묶음을 반으로
        parts = [(kind, numbers) for _, group in seen if len(group) == 1 for kind, numbers in group]
        self.assertTrue(any(len(numbers) < len(full[kind]) for kind, numbers in parts))   # 종류 하나가 잘리면 그 종류의 범위를 반으로

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
        result = suggest_manuscript(self.path, generate=asker, config=SuggestConfig(llm_max_sentences=3))
        self.assertEqual(sum(len(bodies) for call in calls for _, bodies in call), 3)
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


if __name__ == "__main__":
    unittest.main()
