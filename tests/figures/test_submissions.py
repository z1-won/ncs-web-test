"""⑥ 수록 현황·증빙, ⑦ 서약서 AI 결과물 현황 대조, ⑧ AI·외부 제작 그림 유사 — 합성 양식 표로 시험(실제 양식이 있으면 그것도)."""

import tempfile
import unittest
from pathlib import Path

from ncs_core import Document
from ncs_figures.checks import run_checks
from ncs_figures.config import DEFAULT_CONFIG
from ncs_figures.marks import analyze
from ncs_figures.models import Resources
from ncs_figures.submissions import AiEntry, StatusEntry, Submissions, _read_ai, _read_status

from ncs_figures.ids import image_id

from .test_db import make_db, record
from .test_review_rules import ctx, item, picture

FORMS = Path(r"C:\Users\Mint\Desktop\캡스톤디자인\0.공통참고자료")


def status_table():
    cells = {(1, 0): "순번", (1, 1): "시각적 자료 제목", (1, 2): "저작물 제작 방식(해당 방식에 ✓ 표시)",
             (2, 2): "집필자 직접제작", (2, 4): "외부 제작의뢰", (2, 6): "공공 누리, 공유 마당", (2, 7): "포괄적 이용 허락", (2, 8): "기개발 학습 모듈",
             (3, 2): "사진", (3, 3): "삽화", (3, 4): "사진", (3, 5): "삽화",
             (4, 0): "1", (4, 1): "[그림 1-1] 가", (4, 2): "✓",
             (5, 0): "2", (5, 1): "[그림 1-2] 나", (5, 7): "✓",
             (6, 0): "3", (6, 1): "[그림 1-3] 다", (6, 4): "✓"}
    return {"rows": 7, "cols": 9, "cells": cells}


def checks_of(c, sub, **res):
    import re
    from dataclasses import replace
    m = re.search(r"그림\s*(\d+)-(\d+)\]\s*(.*)", c.caption or "")
    if m:                                    # test_review_rules.ctx는 번호를 늘 '그림 1-1'로 둔다 — 캡션에 맞춘다
        c = replace(c, figure_label=f"그림 {m.group(1)}-{m.group(2)}", figure_title=m.group(3) or None)
    outcomes, _ = run_checks(item(c), Resources(submissions=sub, **res), DEFAULT_CONFIG, module_code="LM2001010409_19v4")
    return {o.name: o for o in outcomes}


class ReadTests(unittest.TestCase):
    def test_status_table_methods(self):
        rows = _read_status(status_table())
        self.assertEqual([(e.label, e.method, e.kind) for e in rows],
                         [("그림 1-1", "집필자 직접제작", "사진"), ("그림 1-2", "포괄적 이용 허락", None), ("그림 1-3", "외부 제작의뢰", "사진")])

    def test_ai_table_skips_placeholder(self):
        cells = {(0, 0): "순번", (0, 1): "결과물 명", (0, 2): "학습모듈 해당 쪽수", (0, 3): "활용 AI", (0, 4): "비고",
                 (1, 0): "1", (1, 1): "그림 OOOO", (1, 2): "p.00", (1, 3): "ChatGPT 6.0",
                 (2, 0): "2", (2, 1): "[그림 1-1] 가", (2, 2): "p.12", (2, 3): "ChatGPT 5"}
        rows = _read_ai({"rows": 3, "cols": 5, "cells": cells})
        self.assertEqual([(e.label, e.page, e.tool) for e in rows], [("그림 1-1", "12", "ChatGPT 5")])

    @unittest.skipUnless((FORMS / "F07_계약서_직능연_원고집필·권리양도_2026.hwp").is_file(), "양식 원본 없음")
    def test_official_forms(self):
        from ncs_figures.submissions import read_documents
        sub = read_documents([FORMS / "F07_계약서_직능연_원고집필·권리양도_2026.hwp", FORMS / "F06_계약서_직능연_사진삽화제작·권리양도_2026.hwp"])
        self.assertEqual([e.method for e in sub.status][:2], ["집필자 직접제작", "포괄적 이용 허락"])
        self.assertEqual(len(sub.production), 3)


class StatusTests(unittest.TestCase):
    def test_missing_and_mismatch(self):
        sub = Submissions(status=_read_status(status_table()))
        ok = checks_of(ctx(caption="[그림 1-1] 가", source="출처: 집필진 제작(2025)"), sub)
        self.assertEqual((ok["⑥수록 현황"].value, ok["⑥증빙"].value), ("O", "-"))
        missing = checks_of(ctx(caption="[그림 2-1] 라"), sub)
        self.assertEqual(missing["⑥수록 현황"].value, "X")
        wrong = checks_of(ctx(caption="[그림 1-2] 나", source="출처: 집필진 제작(2025)"), sub)
        self.assertEqual(wrong["⑥수록 현황"].value, "△")                   # 목록은 포괄적 이용 허락인데 출처는 집필진 제작
        self.assertEqual(wrong["⑥증빙"].value, "X")                          # 이용허락 동의서 없음

    def test_evidence_for_commissioned_photo(self):
        entries = _read_status(status_table())
        no_list = checks_of(ctx(caption="[그림 1-3] 다"), Submissions(status=entries))
        self.assertEqual(no_list["⑥증빙"].value, "△")                         # 제작 목록 미제출
        listed = Submissions(status=entries, production=[StatusEntry("[그림 1-3] 다", "그림 1-3", "외부 제작의뢰", "사진")])
        self.assertEqual(checks_of(ctx(caption="[그림 1-3] 다"), listed)["⑥증빙"].value, "△")   # 사진인데 초상권 동의서 없음
        listed.portrait_consents = 1
        self.assertEqual(checks_of(ctx(caption="[그림 1-3] 다"), listed)["⑥증빙"].value, "O")


class AiListTests(unittest.TestCase):
    def sub(self, tool="ChatGPT 5", page=None):
        return Submissions(ai=[AiEntry("[그림 1-1] 가", "그림 1-1", page, tool)])

    def test_marker_vs_pledge(self):
        marker = "ChatGPT를 활용하여 생성함. 2025. 3. 2."
        self.assertEqual(checks_of(ctx(ai=marker), self.sub())["⑦AI 현황 대조"].value, "O")
        self.assertEqual(checks_of(ctx(ai=marker), self.sub(tool="Gemini"))["⑦AI 현황 대조"].value, "△")
        self.assertEqual(checks_of(ctx(), self.sub())["⑦AI 현황 대조"].value, "X")            # 서약서엔 있는데 원고 표기 없음
        other = Submissions(ai=[AiEntry("[그림 2-1] 라", "그림 2-1", None, "ChatGPT")])
        self.assertEqual(checks_of(ctx(ai=marker), other)["⑦AI 현황 대조"].value, "X")        # 원고엔 있는데 서약서에 없음

    def test_list_only_entries(self):
        sub = Submissions(status=[StatusEntry("[그림 3-1] 바", "그림 3-1", "집필자 직접제작", "삽화")], ai=[AiEntry("[그림 3-2] 사", "그림 3-2", None, "x")])
        self.assertEqual(sub.unmatched({"그림 1-1"}), {"수록 현황 목록": ["[그림 3-1] 바"], "AI 결과물 현황": ["[그림 3-2] 사"]})


class SimilarTests(unittest.TestCase):
    def test_ai_figure_close_to_existing(self):
        original = picture(seed=5)
        lookup = make_db(Path(tempfile.mkdtemp()), [record(original, "LM2001010401_19v4", "그림 2-3", "설문")])
        marker = "Gemini를 활용하여 생성함. 2025. 3. 2."
        near = checks_of(ctx(ai=marker, data=original), None, lookup=lookup)
        self.assertEqual(near["⑧AI 결과물 유사"].value, "△")
        far = checks_of(ctx(ai=marker, data=picture(size=(200, 200), seed=40)), None, lookup=lookup)
        self.assertEqual(far["⑧AI 결과물 유사"].value, "O")
        plain = checks_of(ctx(data=original), None, lookup=lookup)                 # AI 표기·외부 제작 아님 → 해당 없음
        self.assertEqual(plain["⑧AI 결과물 유사"].value, "-")


class AiActionTests(unittest.TestCase):
    """⑦ 생성·수정 구분 — '생성함'·'수정 보완함'이 실제 활용 유형과 맞나(REQ-02-008): 출처 짝·서약서 비고·DB(모델 호출 없음)."""
    MADE = "ChatGPT를 활용하여 생성함. 2026. 7. 20."

    def value(self, c, **res):
        return checks_of(c, res.pop("sub", None), **res)["⑦생성·수정 구분"]

    def test_pair_rule(self):
        cited = "출처: 교육부(2018). 공급망 공정계획(LM0204010404_16v2). 한국직업능력연구원. p.6."
        self.assertEqual(self.value(ctx(source=cited, ai=self.MADE)).value, "△")
        self.assertEqual(self.value(ctx(ai=self.MADE)).value, "O")
        self.assertEqual(self.value(ctx(source=None, ai="ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.")).value, "△")

    def test_pledge_note(self):
        sub = Submissions(ai=[AiEntry("[그림 1-1] 가", "그림 1-1", None, "ChatGPT", note="사진 보정(수정)")])
        self.assertIn("서약서 비고", self.value(ctx(ai=self.MADE), sub=sub).note)

    def test_db_says_existing_figure(self):
        original = picture(seed=5)
        lookup = make_db(Path(tempfile.mkdtemp()), [record(original, "LM2001010401_19v4", "그림 2-3", "설문")])
        out = self.value(ctx(ai=self.MADE, data=original), lookup=lookup)
        self.assertEqual(out.value, "△")
        self.assertIn("기존 그림", out.note)


class RequirementTests(unittest.TestCase):
    def test_same_rule_as_008(self):
        """제4조 요건은 그림 검수와 출처 검토가 같은 표를 쓴다 — 문헌은 쪽, 웹은 저작자명까지."""
        book = checks_of(ctx(source="출처: 홍길동(2020). 소프트웨어 공학. 한빛출판."), None)
        self.assertEqual(book["①출처 요건"].value, "X")
        self.assertIn("쪽", book["①출처 요건"].note)


class KoglAiTests(unittest.TestCase):
    def test_ai_type_is_an_addition(self):
        found = analyze(["OPEN 공공누리", "공공저작물 자유이용허락", "출처표시", "AI 학습 이용 가능"])
        self.assertEqual((found["kogl_type"], found["kogl_ai"]), ("1", True))
        free = analyze(["OPEN 공공누리", "자유이용"])
        self.assertEqual((free["kogl_type"], free["kogl_ai"]), ("0", False))


if __name__ == "__main__":
    unittest.main()
