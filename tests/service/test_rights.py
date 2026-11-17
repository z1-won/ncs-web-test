"""권리 증빙 제출 현황 점검(ncs_rights, REQ-02-014) — 서류 읽기, 대조·판정, 기한, 기관별 알림, 출력본 쪽수 대조, 현황표, 웹 API. DB 없이 돈다."""

import io
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

import rights_samples as S
from ncs_core.documents import load_document
from ncs_rights.check import Options
from ncs_rights.forms import read_forms
from ncs_rights.pages import figure_pages, page_numbers
from ncs_rights.report import build_xlsx
from ncs_rights.service import run
from ncs_web.server import create_app

COMPLETE = dict(first_review_on=date(2026, 10, 1), submitted_on=date(2026, 10, 20), today=date(2026, 11, 17),
                transfer_author=True, transfer_maker=True, portrait="none", pledge=True)
M = S.M
PRINT_COPY = Path(__file__).resolve().parents[1] / "fixtures" / "출력본_ok_LM1203020201_24v3.pdf"   # [그림 1-1]이 4쪽에 있다


class RightsCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def check(self, forms=None, figures=S.FIGURES, print_copy=None, **options) -> dict:
        forms = S.full_forms(self.folder) if forms is None else forms
        return run(S.manuscript(self.folder, figures), forms, Options(**{**COMPLETE, **options}), print_copy=print_copy)

    def row(self, report: dict, label: str) -> dict:
        return next(row for row in report["현황표"] if row["그림 번호"] == label)

    def kinds(self, report: dict, label: str) -> list[str]:
        return [issue["종류"] for issue in self.row(report, label)["지적"]]

    def form(self, name: str, *tables: str) -> Path:
        return S.form(self.folder, name, *tables)


class FormReadingTests(RightsCase):
    def test_forms_are_found_by_table_not_by_file(self):
        """계약서 한 파일에 붙임 2·3이 함께 있어도, 파일 이름이 무엇이든 표의 머리 글로 양식을 알아낸다."""
        forms = read_forms([(path.name, load_document(path)) for path in S.full_forms(self.folder)])
        self.assertEqual(forms.sources, {
            "사진·삽화 수록 현황 목록": ["원고집필계약서_붙임.hwpx"], "지식재산권 이용허락 동의서": ["원고집필계약서_붙임.hwpx"],
            "사진·삽화 제작 목록": ["사진삽화_제작목록.hwpx"], "생성형 AI 결과물 현황": ["AI서약서.hwpx"]})
        table = forms.inclusion[0]
        self.assertEqual((table["module"], len(table["rows"])), ("객실 예약 관리", 8))
        first = table["rows"][0]
        self.assertEqual((first["label"], first["title"], first["methods"], first["subs"]["author_made"]),
                         ("그림 1-1", "NCS학습모듈 개념도", ["author_made", "ai"], "사진"))
        self.assertEqual([row["methods"] for row in table["rows"][1:7]],
                         [["blanket_license"], ["author_made"], ["author_made"], ["commissioned"], ["public_license"], ["prior_module"]])
        self.assertEqual((table["rows"][4]["subs"], table["rows"][3]["subs"]), ({"commissioned": "삽화"}, {"author_made": "삽화"}))
        self.assertEqual([(r["label"], r["type"]) for r in forms.production], [("그림 2-2", "삽화")])
        self.assertEqual(forms.license[0]["source"], "홍길동(2024). 직업교육 사례집. 한국출판. p.12.")
        # 양식의 예시 행('그림 OOOO')은 읽지 않고, 괄호 없이 적은 번호도 읽는다
        self.assertEqual([(r["label"], r["title"], r["tool"], r["page"]) for r in forms.ai_results],
                         [("그림 1-1", "NCS학습모듈 개념도", "ChatGPT 6.0", "p.12")])

    def test_other_check_marks_and_unrelated_tables(self):
        rows = [["1", "[그림 1-1] 가", "V", "", "", "", "", "", "", "", ""], ["2", "[그림 1-2] 나", "", "", "", "", "○", "", "", "", ""],
                ["3", "[그림 1-3] 다", "", "", "", "", "", "", "", "해당", ""], ["", "", "", "", "", "", "", "", "", "", ""]]
        other = S.table([["구분", "내용"], ["순번", "아무 표"]])
        forms = read_forms([("a.hwpx", load_document(self.form("a.hwpx", other, S.inclusion_table(rows, module=""))))])
        self.assertEqual([row["methods"] for row in forms.inclusion[0]["rows"]], [["author_made"], ["public_license"], []],
                         "✓ 대신 V·○도 표시로 읽고, 글자가 든 칸('해당')은 표시로 보지 않는다")
        self.assertEqual((forms.inclusion[0]["module"], list(forms.sources)), ("", ["사진·삽화 수록 현황 목록"]))


class CheckTests(RightsCase):
    def test_complete_set_leaves_only_real_gaps(self):
        report = self.check()
        self.assertEqual({key: report["요약"][key] for key in ("판정", "원고 그림", "목록 행", "적합", "부적합", "판단불가", "누락")},
                         {"판정": "부적합", "원고 그림": 8, "목록 행": 8, "적합": 7, "부적합": 2, "판단불가": 0, "누락": 2})
        self.assertEqual([(f["그림"], f["종류"]) for f in report["지적사항"]],
                         [("[그림 2-5] 목록에 없는 그림", "목록 누락"), ("[그림 3-1] 원고에 없는 그림", "원고에 없음")])
        first = self.row(report, "그림 1-1")
        self.assertEqual([(e["증빙"], e["상태"]) for e in first["증빙"]],
                         [("양도 동의서(집필자)", "제출"), ("초상권 동의서", "해당 없음"), ("AI 서약서", "제출")])
        self.assertEqual((first["AI 표기"], first["제작 방식"], first["목록"]),
                         ("ChatGPT · 생성함 · 2026-07-20", ["집필자 직접제작(사진)", "AI 활용"], True))
        self.assertEqual([(e["증빙"], e["상태"], e["근거"]) for e in self.row(report, "그림 2-2")["증빙"]],
                         [("제작 목록", "제출", "사진삽화_제작목록.hwpx"), ("양도 동의서(제작자)", "제출", "")])
        self.assertEqual((self.row(report, "그림 3-1")["원고"], self.row(report, "그림 2-5")["목록"]), (False, False))

    def test_each_missing_evidence_is_reported(self):
        """증빙을 하나씩 빼면 그 증빙이 필요한 그림만 부적합이 된다(검증 기준: 증빙 누락 탐지)."""
        base = self.folder / "base"
        base.mkdir()
        cases = [
            ("집필자 양도 동의서", dict(transfer_author=False), None, {"그림 1-1", "그림 1-3", "그림 2-1", "그림 3-1"}, "증빙 누락"),
            ("제작자 양도 동의서", dict(transfer_maker=False), None, {"그림 2-2"}, "증빙 누락"),
            ("AI 서약서", dict(pledge=False), None, {"그림 1-1"}, "증빙 누락"),
            ("제작 목록", {}, ["계약서", "서약서"], {"그림 2-2"}, "증빙 누락"),
            ("이용허락 동의서", {}, ["목록만", "제작", "서약서"], {"그림 1-2"}, "증빙 누락"),
            ("AI 결과물 현황", {}, ["계약서", "제작"], {"그림 1-1"}, "현황 누락"),
        ]
        expected_always = {"그림 2-5", "그림 3-1"}        # 목록 누락·원고에 없음은 모든 경우에 있다
        for name, options, parts, failing, kind in cases:
            with self.subTest(missing=name):
                folder = base / name
                folder.mkdir()
                pieces = {"계약서": lambda: S.form(folder, "c.hwpx", S.inclusion_table(), S.license_table()),
                          "목록만": lambda: S.form(folder, "c.hwpx", S.inclusion_table()),
                          "제작": lambda: S.form(folder, "p.hwpx", S.production_table()),
                          "서약서": lambda: S.form(folder, "a.hwpx", S.ai_table())}
                forms = S.full_forms(folder) if parts is None else [pieces[part]() for part in parts]
                report = run(S.manuscript(folder), forms, Options(**{**COMPLETE, **options}))
                failed = {row["그림 번호"] for row in report["현황표"] if row["판정"] == "부적합"}
                self.assertEqual(failed, failing | expected_always)
                for label in failing - expected_always:
                    self.assertIn(kind, [i["종류"] for i in self.row(report, label)["지적"]])

    def test_portrait_needs_a_person_to_look(self):
        report = self.check(portrait="unknown")
        photos = {row["그림 번호"] for row in report["현황표"] if "초상권 확인" in [i["종류"] for i in row["지적"]]}
        self.assertEqual(photos, {"그림 1-1", "그림 1-3"}, "사진으로 표시된 그림만 — 삽화(2-1, 2-2)는 묻지 않는다")
        self.assertEqual(self.row(report, "그림 1-3")["판정"], "판단불가")
        submitted = self.check(portrait="submitted")
        self.assertIn(("초상권 동의서", "제출"), [(e["증빙"], e["상태"]) for e in self.row(submitted, "그림 1-3")["증빙"]])

    def test_ai_marking_must_agree_across_manuscript_list_and_pledge(self):
        figures = list(S.FIGURES)
        figures[0] = (*figures[0][:3], "")                                                   # 1-1: 목록은 AI인데 원고 표기 없음
        figures[2] = (*figures[2][:3], "Gemini를 활용하여 수정 보완함. 2026. 8. 1.")          # 1-3: 원고 표기는 있는데 목록·현황에 없음
        figures[3] = (*figures[3][:3], "ChatGPT를 활용하여 생성함")                          # 2-1: 일자 없음
        rows = S.inclusion_rows()
        rows[3][9] = M                                                                       # 2-1: 목록에 AI 표시
        forms = [self.form("c.hwpx", S.inclusion_table(rows), S.license_table()), self.form("p.hwpx", S.production_table()),
                 self.form("a.hwpx", S.ai_table([["1", "[그림 1-1] NCS학습모듈 개념도", "p.12", "ChatGPT", ""],
                                                 ["2", "[그림 2-1] NCS학습모듈 활용 통계", "", "Midjourney", ""],
                                                 ["3", "[그림 2-4] 능력단위 구성", "p.40", "ChatGPT", ""],
                                                 ["4", "[그림 7-7] 어디에도 없는 결과물", "p.1", "ChatGPT", ""]]))]
        report = self.check(forms, figures)
        self.assertEqual(self.kinds(report, "그림 1-1"), ["AI 표기 누락"])
        self.assertEqual(self.kinds(report, "그림 1-3"), ["AI 표시 불일치", "현황 누락"])
        self.assertEqual(self.kinds(report, "그림 2-1"), ["활용 AI 다름", "쪽수 미기재", "AI 표기 일자"])
        self.assertEqual(self.kinds(report, "그림 2-4"), ["AI 표시 확인"])
        self.assertEqual((self.row(report, "그림 2-1")["판정"], self.row(report, "그림 1-3")["판정"]), ("판단불가", "부적합"))
        self.assertIn(("[그림 7-7] 어디에도 없는 결과물", "현황에만 있음"), [(f["그림"], f["종류"]) for f in report["지적사항"]])

    def test_list_problems_number_title_method_and_source(self):
        figures = [("그림 1-1", "개념도", "출처: 집필진 제작(2026)", ""), ("그림 1-2", "흐름도", "출처: 집필진 제작(2026)", ""),
                   ("그림 1-3", "공공 자료", "", ""), ("그림 1-4", "옛 모듈 그림", "출처: 어느 블로그(2020).", ""),
                   ("그림 1-5", "방식 없는 그림", "출처: 집필진 제작(2026)", ""), ("그림 1-6", "방식 둘", "출처: 집필진 제작(2026)", ""),
                   ("그림 1-7", "띄어 쓴 제목", "출처: 집필진 제작(2026)", "")]

        def row(no, title, *marked):
            return [str(no), title] + [M if col in marked else "" for col in range(2, 11)]

        rows = [row(1, "[그림 1-1] 개념 구성도", 3), row(2, "[그림 1-9] 흐름도", 3), row(3, "[그림 1-3] 공공 자료", 6),
                row(4, "[그림 1-4] 옛 모듈 그림", 8), row(5, "[그림 1-5] 방식 없는 그림"), row(6, "[그림 1-6] 방식 둘", 3, 5),
                row(7, "[그림 1-7] 띄어쓴  제목.", 3)]
        report = self.check([self.form("c.hwpx", S.inclusion_table(rows)), self.form("p.hwpx", S.production_table([["1", "[그림 1-6] 방식 둘", M, ""]]))], figures)
        self.assertEqual(self.kinds(report, "그림 1-1"), ["제목 다름"])
        self.assertEqual(self.kinds(report, "그림 1-2"), ["번호 다름"])
        self.assertEqual(self.kinds(report, "그림 1-3"), ["출처 미표기"])
        self.assertEqual(self.kinds(report, "그림 1-4"), ["출처 확인"])
        self.assertEqual(self.kinds(report, "그림 1-5"), ["제작 방식 미표시"])
        self.assertEqual(self.kinds(report, "그림 1-6"), ["제작 방식 중복", "유형 다름"])
        self.assertEqual(self.row(report, "그림 1-7")["판정"], "적합", "띄어쓰기·마침표만 다른 제목은 같은 그림")
        self.assertEqual(len(report["현황표"]), 7, "번호나 제목으로 짝지은 행을 '원고에 없음'으로 한 번 더 세지 않는다")

    def test_without_the_list_one_finding_not_one_per_figure(self):
        report = self.check([self.form("p.hwpx", S.production_table())])
        # 목록이 없다는 것은 한 번만 말한다. 원고만으로 알 수 있는 것(AI 표기가 있는데 결과물 현황이 없음)은 그대로 나온다
        self.assertEqual([(f["그림"], f["종류"], f["수준"]) for f in report["지적사항"]],
                         [("수록 현황 목록", "목록 미제출", "부적합"), ("[그림 1-1] NCS학습모듈 개념도", "현황 누락", "부적합")])
        self.assertNotIn("목록 누락", [f["종류"] for f in report["지적사항"]])
        # 목록이 없으면 필요한 증빙을 따질 수 없으므로 문제가 안 보여도 적합으로 두지 않는다
        self.assertEqual((report["요약"]["적합"], report["요약"]["판단불가"], report["요약"]["부적합"]), (0, 7, 1))
        self.assertIn("대조하지 못했습니다", self.row(report, "그림 1-3")["비고"][0])
        self.assertEqual((report["요약"]["목록 행"], {row["목록"] for row in report["현황표"]}, report["요약"]["원고 그림"]), (None, {None}, 8))

    def test_module_lists_pick_the_one_for_this_manuscript(self):
        other = S.inclusion_table([["1", "[그림 1-1] 다른 모듈의 그림", "", M, "", "", "", "", "", "", ""]], module="객실 판매 관리")
        report = self.check([self.form("c.hwpx", other, S.inclusion_table(), S.license_table()), self.form("p.hwpx", S.production_table()),
                             self.form("a.hwpx", S.ai_table())])
        self.assertEqual((report["요약"]["학습모듈명"], report["요약"]["목록 행"]), ("객실 예약 관리", 8))
        self.assertIn("2개 중", report["안내"][0])

    def test_unreadable_inputs(self):
        junk = self.folder / "메모.txt"
        junk.write_text("표가 아님", encoding="utf-8")
        broken = self.folder / "깨진.hwpx"
        broken.write_bytes(b"not a zip")
        report = self.check([junk, broken, self.form("빈.hwpx")])
        self.assertEqual(len(report["안내"]), 3)
        self.assertTrue(any("메모.txt" in note for note in report["안내"]) and any("깨진.hwpx" in note for note in report["안내"]))
        self.assertIn("찾지 못했습니다", report["안내"][-1])
        with self.assertRaises(ValueError) as caught:
            run(broken, [])
        self.assertIn("깨진.hwpx", str(caught.exception))
        no_figures = self.check(figures=[])
        self.assertIn(("원고", "그림 없음"), [(f["그림"], f["종류"]) for f in no_figures["지적사항"]])


class DeadlineTests(RightsCase):
    """원고 집필 계약서 제5조 1항: 1차 검토 이후 4주 이내. 기한 항목은 어떤 입력에서도 결과에 있다(알림 누락 0건)."""

    def deadline(self, with_list: bool = True, **options) -> dict:
        forms = None if with_list else [self.form("p.hwpx", S.production_table())]
        return self.check(forms, **options)

    def test_every_case_reports_the_deadline(self):
        cases = [
            (dict(submitted_on=date(2026, 10, 29)), True, "적합", "기한(2026-10-29) 안에"),          # 기한 당일
            (dict(submitted_on=date(2026, 10, 30)), True, "부적합", "1일 늦게"),
            (dict(submitted_on=None), True, "판단불가", "제출일을 입력하지 않아"),
            (dict(submitted_on=None, today=date(2026, 10, 29)), False, "판단불가", "남은 날 0일"),
            (dict(submitted_on=None, today=date(2026, 11, 17)), False, "부적합", "19일 지났습니다"),
            (dict(first_review_on=None), True, "판단불가", "1차 검토일을 입력하지 않아"),
            (dict(submitted_on=date(2026, 9, 1)), True, "판단불가", "1차 검토일(2026-10-01)보다 앞섭니다"),
        ]
        for options, with_list, verdict, text in cases:
            with self.subTest(options=options, with_list=with_list):
                report = self.deadline(with_list, **options)
                self.assertEqual(report["기한"]["판정"], verdict)
                self.assertIn(text, report["기한"]["내용"])
                listed = [f for f in report["지적사항"] if f["그림"] == "제출 기한"]
                self.assertEqual(len(listed), 0 if verdict == "적합" else 1, "적합이 아니면 지적사항에 반드시 한 건")
        self.assertEqual(self.deadline()["기한"]["기한"], "2026-10-29")


class MatchingTests(RightsCase):
    """실제 원고에서 나온 경우 — 같은 제목이 다른 번호로 또 나오고, 뒤 번호를 비운 캡션의 제목이 숫자로 시작한다(tests/eval_rights.py가 찾음)."""

    def test_same_title_under_another_number_does_not_lend_its_evidence(self):
        figures = [("그림 1-10", "객실 전화 예약 흐름도", "출처: 홍길동(2024). 사례집.", ""), ("그림 1-13", "객실 전화 예약 흐름도", "출처: 홍길동(2024). 사례집.", "")]
        listed = S.inclusion_table([["1", "[그림 1-10] 객실 전화 예약 흐름도", "", "", "", "", "", M, "", "", ""],
                                    ["2", "[그림 1-13] 객실 전화 예약 흐름도", "", "", "", "", "", M, "", "", ""]])
        only_first = S.license_table([["1", "[그림 1-10] 객실 전화 예약 흐름도", "홍길동(2024). 사례집.", "객실 예약 관리"]])
        report = self.check([self.form("c.hwpx", listed, only_first)], figures)
        self.assertEqual((self.kinds(report, "그림 1-10"), self.kinds(report, "그림 1-13")), ([], ["증빙 누락"]),
                         "그림 1-10의 동의서 행을 그림 1-13의 것으로 보지 않는다")

    def test_list_rows_go_to_the_figure_they_name(self):
        figures = [("그림 1-10", "객실 전화 예약 흐름도", "출처: 집필진 제작(2026)", ""), ("그림 1-13", "객실 전화 예약 흐름도", "출처: 집필진 제작(2026)", "")]
        listed = S.inclusion_table([["1", "[그림 1-13] 객실 전화 예약 흐름도", "", M, "", "", "", "", "", "", ""]])     # 그림 1-10이 목록에 없다
        report = self.check([self.form("c.hwpx", listed)], figures)
        self.assertEqual((self.kinds(report, "그림 1-10"), self.kinds(report, "그림 1-13")), (["목록 누락"], []),
                         "앞 그림이 제목만 같은 뒤 그림의 행을 가져가지 않는다")

    def test_same_number_used_twice_is_paired_by_title(self):
        figures = [("그림 2-2", "객실 타입별 요금 조회 화면", "출처: 집필진 제작(2026)", ""), ("그림 2-2", "초과 예약 접수하기", "출처: 집필진 제작(2026)", "")]
        listed = S.inclusion_table([["1", "[그림 2-2] 초과 예약 접수하기", "", M, "", "", "", "", "", "", ""]])
        report = self.check([self.form("c.hwpx", listed)], figures)
        self.assertEqual([(row["그림명"], [issue["종류"] for issue in row["지적"]]) for row in report["현황표"]],
                         [("객실 타입별 요금 조회 화면", ["목록 누락"]), ("초과 예약 접수하기", [])])

    def test_blank_minor_with_a_title_that_starts_with_a_digit(self):
        figures = [("그림 2-", "6LoWPAN 프로토콜 스택", "출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 7. 20.")]
        forms = [self.form("c.hwpx", S.inclusion_table([["1", "[그림 2-] 6LoWPAN 프로토콜 스택", "", M, "", "", "", "", "", M, ""]])),
                 self.form("a.hwpx", S.ai_table([["1", "그림 2- 6LoWPAN 프로토콜 스택", "p.12", "ChatGPT", ""]]))]
        report = self.check(forms, figures)
        self.assertEqual([issue["종류"] for issue in report["현황표"][0]["지적"] if issue["수준"] == "부적합"], [],
                         "결과물 현황의 '그림 2- 6LoWPAN …'에서 6을 뒤 번호로 읽지 않는다")
        read = read_forms([("a.hwpx", load_document(self.form("b.hwpx", S.ai_table([
            ["1", "그림 1-2 개념도", "", "", ""], ["2", "그림 1 - 3. 구성도", "", "", ""], ["3", "그림 2- 6LoWPAN", "", "", ""]]))))])
        self.assertEqual([(row["label"], row["title"]) for row in read.ai_results],
                         [("그림 1-2", "개념도"), ("그림 1-3", "구성도"), ("그림 2-", "6LoWPAN")])


class NoticeTests(RightsCase):
    def test_each_finding_names_who_has_to_act(self):
        """서류를 내거나 고칠 것은 개발기관, 같은 것인지 사람이 가릴 것은 에디팅 기관이 받는다."""
        forms = [self.form("c.hwpx", S.inclusion_table([
            ["1", "[그림 1-1] NCS학습모듈 개념도", M, "", "", "", "", "", "", M, ""],      # 직접제작(사진) + AI
            ["2", "[그림 1-2] 다른 제목", "", "", "", "", "", M, "", "", ""],              # 번호는 같고 제목이 다름
        ]), S.license_table())]
        report = self.check(forms, S.FIGURES[:2], transfer_author=False, pledge=False, portrait="unknown")
        to = {(finding["그림"].split("]")[0].lstrip("["), finding["종류"]): finding["받는 곳"] for finding in report["지적사항"]}
        self.assertEqual(to[("그림 1-1", "증빙 누락")], "개발기관")
        self.assertEqual(to[("그림 1-1", "초상권 확인")], "에디팅 기관")
        self.assertEqual(to[("그림 1-2", "제목 다름")], "에디팅 기관")
        self.assertTrue(all(finding["받는 곳"] in ("개발기관", "에디팅 기관") for finding in report["지적사항"]))

        developer, editor = report["알림"]
        self.assertEqual((developer["받는 곳"], editor["받는 곳"]), ("개발기관", "에디팅 기관"))
        self.assertEqual(developer["건수"] + editor["건수"], len(report["지적사항"]), "지적은 빠짐없이 한 곳에만 간다")
        self.assertEqual(developer["부적합"], report["요약"]["누락"], "서류로 확인된 누락은 모두 개발기관에 간다")
        self.assertIn(f"보완할 것이 {developer['건수']}건", developer["글"])
        self.assertIn("집필자 직접제작인데 지식재산권 양도 동의서가 제출되지 않았습니다", developer["글"])
        self.assertIn(f"개발기관에 보완을 요청한 것은 {developer['건수']}건", editor["글"], "에디팅 기관도 누락 건수를 안다")

    def test_deadline_goes_to_whoever_can_fix_it(self):
        late = self.check(submitted_on=date(2026, 11, 10))
        self.assertEqual([f["받는 곳"] for f in late["지적사항"] if f["종류"] == "기한"], ["개발기관"])
        unsent = self.check([], first_review_on=date(2026, 11, 10), submitted_on=None)      # 아직 기한 안 — 내야 하는 쪽에 알린다
        self.assertEqual([f["받는 곳"] for f in unsent["지적사항"] if f["종류"] == "기한"], ["개발기관"])
        undated = self.check(first_review_on=None, submitted_on=None)                       # 날짜를 안 넣은 것은 점검하는 쪽의 일
        self.assertEqual([f["받는 곳"] for f in undated["지적사항"] if f["종류"] == "기한"], ["에디팅 기관"])

    def test_nothing_to_send(self):
        figures = [S.FIGURES[2]]
        report = self.check([self.form("c.hwpx", S.inclusion_table([["1", "[그림 1-3] NCS학습모듈 개발 프로세스", "", M, "", "", "", "", "", "", ""]]))], figures)
        self.assertEqual([(notice["건수"], notice["글"].splitlines()[1]) for notice in report["알림"]],
                         [(0, "보완할 것이 없습니다."), (0, "확인할 것이 없습니다. 개발기관에 보완을 요청한 것은 0건입니다.")])


class PrintCopyTests(RightsCase):
    def test_page_numbers_from_the_form(self):
        self.assertEqual([page_numbers(text) for text in ("p.12", "pp. 12~13", "12쪽, 15쪽", "p. 7-9", "p.00", "", "본문", "12~300")],
                         [[12], [12, 13], [12, 15], [7, 8, 9], [], [], [], [12, 300]])

    def test_captions_are_located_in_the_print_copy(self):
        from ncs_core.pdf import load_pdf

        self.assertEqual(figure_pages(load_pdf(PRINT_COPY)), {"그림 1-1": [{"쪽": "4", "추정": False, "물리 쪽": 7}]})

    def ai_forms(self, page: str) -> list[Path]:
        return [self.form("c.hwpx", S.inclusion_table(), S.license_table()), self.form("p.hwpx", S.production_table()),
                self.form("a.hwpx", S.ai_table([["1", "그림 1-1 NCS학습모듈 개념도", page, "ChatGPT 6.0", ""]]))]

    def test_page_in_the_ai_results_is_compared_with_the_print_copy(self):
        same = self.check(self.ai_forms("p.4"), print_copy=PRINT_COPY)
        row = self.row(same, "그림 1-1")
        self.assertEqual((row["쪽"], row["쪽 번호"], row["쪽수 대조"], row["판정"]), ("4쪽", ["4"], "일치", "적합"))
        self.assertEqual(same["출력본"], {"파일": PRINT_COPY.name, "쪽": 45, "캡션 찾은 그림": 1, "모듈 코드": "LM1203020201_24v3"})
        self.assertEqual(self.row(same, "그림 1-2")["쪽"], "", "출력본에서 찾지 못한 그림은 쪽이 비어 있다(지적은 내지 않는다)")

        wide = self.check(self.ai_forms("pp. 3~5"), print_copy=PRINT_COPY)
        self.assertEqual(self.row(wide, "그림 1-1")["쪽수 대조"], "일치", "적힌 범위 안에 있으면 맞는 것으로 본다")

        other = self.check(self.ai_forms("p.12"), print_copy=PRINT_COPY)
        row = self.row(other, "그림 1-1")
        self.assertEqual((self.kinds(other, "그림 1-1"), row["판정"], row["지적"][0]["받는 곳"]), (["쪽수 다름"], "판단불가", "에디팅 기관"))
        self.assertIn("「p.12」인데 출력본에서는 이 그림이 4쪽에", row["비고"][0])

        unread = self.check(self.ai_forms("본문 참조"), print_copy=PRINT_COPY)
        self.assertEqual(self.kinds(unread, "그림 1-1"), ["쪽 확인"])

    def test_figure_missing_from_the_print_copy(self):
        figures = [("그림 4-1", "출력본에 없는 그림", "출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 7. 20.")]
        forms = [self.form("c.hwpx", S.inclusion_table([["1", "[그림 4-1] 출력본에 없는 그림", "", M, "", "", "", "", "", M, ""]])),
                 self.form("a.hwpx", S.ai_table([["1", "그림 4-1 출력본에 없는 그림", "p.30", "ChatGPT", ""]]))]
        report = self.check(forms, figures, print_copy=PRINT_COPY)
        self.assertEqual(self.kinds(report, "그림 4-1"), ["쪽 확인"])
        self.assertIn("캡션을 찾지 못해", self.row(report, "그림 4-1")["비고"][0])

    def test_without_or_with_an_unreadable_print_copy_pages_are_not_compared(self):
        plain = self.check(self.ai_forms("p.12"))
        self.assertEqual((plain["출력본"], self.kinds(plain, "그림 1-1"), self.row(plain, "그림 1-1")["쪽"]), (None, [], ""))
        broken = self.folder / "깨진.pdf"
        broken.write_bytes(b"not a pdf")
        report = self.check(self.ai_forms("p.12"), print_copy=broken)
        self.assertEqual((report["출력본"], self.kinds(report, "그림 1-1")), (None, []))
        self.assertTrue(any("깨진.pdf: 출력본을 읽지 못해 쪽수를 대조하지 않았습니다" in note for note in report["안내"]))


class OutputTests(RightsCase):
    def test_xlsx_has_both_sheets_and_no_formulas(self):
        from openpyxl import load_workbook

        figures = [("그림 1-1", "=HYPERLINK(\"http://x\")", "출처: 집필진 제작(2026)", "")]
        report = self.check([self.form("c.hwpx", S.inclusion_table([["1", "[그림 1-1] =HYPERLINK(\"http://x\")", "", M, "", "", "", "", "", "", ""]]))], figures)
        book = load_workbook(io.BytesIO(build_xlsx(report)))
        self.assertEqual(book.sheetnames, ["증빙 제출 현황", "누락·확인", "알림_개발기관", "알림_에디팅 기관"])
        sheet = book["증빙 제출 현황"]
        cells = [cell for row in sheet.iter_rows() for cell in row if cell.value is not None]
        self.assertTrue(any(cell.value == "그림 1-1" for cell in cells))
        self.assertFalse([cell.coordinate for cell in cells if cell.data_type == "f"], "원고에서 온 글이 수식이 되면 안 된다")
        full = load_workbook(io.BytesIO(build_xlsx(self.check())))
        self.assertEqual(full["누락·확인"].max_row, 3)                      # 머리 + 지적 2건
        self.assertEqual(full["증빙 제출 현황"].max_row, 6 + 9)             # 제목·요약 5줄 + 머리 + 그림 9줄
        self.assertEqual([cell.value for cell in full["누락·확인"][2]][-1], "개발기관")
        notice = full["알림_개발기관"]
        self.assertTrue(notice["A1"].value.startswith("[권리 증빙 제출 현황 점검] 객실 예약 관리 — 개발기관\n보완할 것이 2건"))
        self.assertEqual((notice.max_row, full["알림_에디팅 기관"].max_row), (3 + 2, 3), "글 + 머리 + 그곳의 지적")
        self.assertFalse([c.coordinate for sheet in book for row in sheet.iter_rows() for c in row if c.data_type == "f"])
        old = {key: value for key, value in self.check().items() if key != "알림"}        # 알림이 없는 예전 결과도 내보낼 수 있다
        for finding in old["지적사항"]:
            del finding["받는 곳"]
        self.assertEqual(load_workbook(io.BytesIO(build_xlsx(old))).sheetnames, ["증빙 제출 현황", "누락·확인"])


class WebTests(RightsCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.out.cleanup)
        cls.client = TestClient(create_app(out_dir=Path(cls.out.name) / "결과"))

    def post(self, manuscript: Path, forms: list[Path], expect: int = 200, print_copy: Path | None = None, **data):
        files = [("manuscript", (manuscript.name, manuscript.read_bytes()))] + [("forms", (f.name, f.read_bytes())) for f in forms]
        if print_copy:
            files.append(("print_copy", (print_copy.name, print_copy.read_bytes())))
        response = self.client.post("/api/rights/check", files=files, data=data)
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def test_check_export_and_bad_requests(self):
        manuscript, forms = S.manuscript(self.folder), S.full_forms(self.folder)
        report = self.post(manuscript, forms, first_review_on="2026-10-01", submitted_on="2026-10-20", transfer_author="true",
                           transfer_maker="true", portrait="none", pledge="true")
        self.assertEqual((report["요약"]["적합"], report["요약"]["부적합"], report["원고"]["파일"], report["저장"]), (7, 2, S.MANUSCRIPT_NAME, None))
        self.assertEqual(report["기한"]["판정"], "적합")
        self.assertEqual([notice["받는 곳"] for notice in report["알림"]], ["개발기관", "에디팅 기관"])
        self.assertIsNone(report["출력본"])
        alone = self.post(manuscript, [])                          # 서류 없이 원고만 — 점검은 되고 목록 미제출로 나온다
        self.assertEqual(alone["지적사항"][0]["종류"], "목록 미제출")
        printed = self.post(manuscript, forms, print_copy=PRINT_COPY, pledge="true", transfer_author="true")   # 출력본을 함께 — 쪽수 대조
        self.assertEqual(printed["출력본"]["파일"], PRINT_COPY.name)
        self.assertIn("쪽수 다름", [finding["종류"] for finding in printed["지적사항"]])

        exported = self.client.post("/api/rights/export", json=report)
        self.assertEqual(exported.status_code, 200)
        self.assertTrue(exported.content.startswith(b"PK") and "filename*=UTF-8''" in exported.headers["content-disposition"])
        self.assertEqual(self.client.post("/api/rights/export", json={"요약": {}}).status_code, 400)

        self.assertIn("YYYY-MM-DD", self.post(manuscript, [], expect=400, first_review_on="10/01")["error"])
        self.assertIn("portrait", self.post(manuscript, [], expect=400, portrait="yes")["error"])
        self.assertIn("데이터베이스", self.post(manuscript, [], expect=400, save="true", by="누구")["error"])
        self.assertIn("같은 이름", self.post(manuscript, [forms[0], forms[0]], expect=400)["error"])
        broken = self.folder / "깨진.hwpx"
        broken.write_bytes(b"not a zip")
        error = self.post(broken, [], expect=400)["error"]
        self.assertIn("깨진.hwpx", error)
        self.assertNotIn(str(self.folder), error, "서버의 임시 경로를 내보내지 않는다")
        self.assertEqual(self.client.post("/api/rights/check").status_code, 400)


if __name__ == "__main__":
    unittest.main()
