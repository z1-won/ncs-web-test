"""도표·표 생성(REQ-02-006 ① AI 생성) — 명세의 모양 검사, 근거 검사(집필자가 쓴 글에 있는 말만), 그리기, 생성형 AI 후보 거르기.

생성형 AI는 가짜 응답(asker)으로 넣는다. 그리기는 한글 글꼴이 있어야 돈다(fonts/ 또는 시스템 글꼴) — 없으면 건너뛴다.
"""

import hashlib
import io
import unittest

from ncs_aiimage import SpecError, grounding, omissions, propose, read_spec, render, table_html, table_tsv
from ncs_aiimage.diagram import candidates
from ncs_aiimage.draw import font_available
from ncs_core import llm

TEXT = ("객실 예약은 다음 순서로 접수한다. 먼저 전화나 온라인으로 들어온 예약 요청을 접수하고, 객실 현황을 확인한다. "
        "이어서 고객명과 투숙 일자 등 예약 정보를 입력한 뒤 예약 확인서를 발송한다. 성수기에는 2일 전까지 예약 보증금을 받는다.")
SEQUENCE = {"kind": "sequence", "title": "객실 예약 접수 절차", "items": [
    {"label": "예약 요청 접수", "note": "전화, 온라인"}, {"label": "객실 현황 확인"},
    {"label": "예약 정보 입력", "note": "고객명, 투숙 일자"}, {"label": "예약 확인서 발송"}]}
TABLE = {"kind": "table", "title": "예약 접수 단계", "header": ["단계", "내용"],
         "rows": [["예약 요청 접수", "전화나 온라인"], ["예약 정보 입력", "고객명과 투숙 일자"]]}


def fake(specs, reason=""):
    return lambda system, user: {"data": {"specs": specs, "reason": reason}, "model": "fake"}


class ReadSpecTests(unittest.TestCase):
    def test_round_trip(self):
        for raw in (SEQUENCE, TABLE):
            self.assertEqual(read_spec(raw).as_dict(), raw)

    def test_shape_errors(self):
        bad = [
            {"kind": "pie"},
            {"kind": "sequence", "items": [{"label": "하나"}]},                                        # 2칸 미만
            {"kind": "sequence", "items": [{"label": "가"}, {"label": "가 "}]},                        # 같은 이름
            {"kind": "sequence", "items": [{"label": "가" * 25}, {"label": "나"}]},                    # 너무 긴 이름
            {"kind": "sequence", "items": [{"label": "가", "children": ["x"]}, {"label": "나"}]},
            {"kind": "cycle", "items": [{"label": "가"}, {"label": "나"}]},                            # 순환은 3칸부터
            {"kind": "structure", "items": [{"label": "가"}, {"label": "나"}]},                        # root 없음
            {"kind": "compare", "items": [{"label": "가"}, {"label": "나", "children": ["x"]}]},       # 비교 열에 줄이 없음
            {"kind": "table", "header": ["가"], "rows": [["x"]]},                                      # 1열
            {"kind": "table", "header": ["가", "나"], "rows": [["x"]]},                                # 칸 수가 다름
            {"kind": "table", "header": ["가", "나"], "rows": [["", ""]]},                             # 빈 줄
            {"kind": "table", "header": ["가", "나"], "rows": []},
            "글",
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(SpecError):
                read_spec(raw)

    def test_text_is_tidied(self):
        spec = read_spec({"kind": "sequence", "items": ["  예약   요청 ", {"label": "확인", "note": None}]})
        self.assertEqual([item.label for item in spec.items], ["예약 요청", "확인"])


class GroundingTests(unittest.TestCase):
    def test_words_from_the_paragraph_pass(self):
        self.assertEqual(grounding(read_spec(SEQUENCE), TEXT).problems, [])
        self.assertEqual(grounding(read_spec(TABLE), TEXT).problems, [])

    def reasons(self, raw, source=TEXT):
        return [problem["reason"] for problem in grounding(read_spec(raw), source).problems]

    def test_word_not_in_the_paragraph(self):
        raw = {**SEQUENCE, "items": SEQUENCE["items"] + [{"label": "결제 승인"}]}
        reasons = self.reasons(raw)
        self.assertEqual(len(reasons), 1)
        self.assertIn("'결제'", reasons[0])
        self.assertIn("'승인'", reasons[0])

    def test_new_number_latin_and_brand(self):
        raw = {"kind": "sequence", "items": [{"label": "예약 요청 접수", "note": "3일 전까지"}, {"label": "PMS 예약 정보 입력"},
                                             {"label": "카카오톡 예약 확인서 발송"}]}
        reasons = " / ".join(self.reasons(raw))
        self.assertIn("글에 없는 수 '3'", reasons)
        self.assertIn("글에 없는 영문 'PMS'", reasons)
        self.assertIn("상표·상품명 '카카오톡'", reasons)

    def test_number_in_the_paragraph_passes(self):
        raw = {"kind": "sequence", "items": [{"label": "예약 요청 접수"}, {"label": "예약 보증금", "note": "성수기 2일 전까지"}]}
        self.assertEqual(self.reasons(raw), [])

    def test_particles_are_dropped_before_matching(self):
        raw = {"kind": "sequence", "items": [{"label": "객실 현황의 확인"}, {"label": "예약 확인서를 발송"}]}
        self.assertEqual(self.reasons(raw), [])

    def test_nominalised_verbs_match_the_verb_in_the_paragraph(self):
        """실제 응답(2026-11-24)에서 떨어졌던 꼴: '정하고' → '정함', '종류에' → '종류별'. 글에 없는 동사는 그대로 지적한다."""
        source = "계획 단계에서는 개선 목표와 방법을 정하고, 화재의 종류에 맞게 고른다. 물 소화기는 쓰지 않는다. 결과를 목표와 비교하며 원인을 없앤다."
        ok = {"kind": "sequence", "items": [{"label": "개선 목표와 방법을 정함"}, {"label": "화재 종류별 소화기", "note": "물 소화기는 쓰지 않음"},
                                            {"label": "결과를 목표와 비교함", "note": "원인을 없앰"}]}
        self.assertEqual(self.reasons(ok, source), ["글에 없는 말 '없앰'"])       # '없앤다' → '없앰'은 어림으로 잇지 못한다(알려진 한계)
        bad = {"kind": "sequence", "items": [{"label": "개선 목표를 승인함"}, {"label": "방법을 정함"}]}
        self.assertEqual(self.reasons(bad, source), ["글에 없는 말 '승인함'"])

    def test_one_letter_stem_needs_the_verb_form(self):
        raw = {"kind": "sequence", "items": [{"label": "정보를 정함"}, {"label": "정보 입력"}]}
        self.assertEqual(self.reasons(raw, "정보를 입력한다."), ["글에 없는 말 '정함'"])       # '정보'의 '정'으로 '정함'을 받지 않는다

    def test_frame_words_are_allowed(self):
        raw = {"kind": "table", "title": "예약 접수 절차 구분", "header": ["구분", "내용"], "rows": [["예약 요청", "전화나 온라인"]]}
        self.assertEqual(self.reasons(raw), [])

    def test_empty_source_grounds_nothing(self):
        self.assertTrue(self.reasons(SEQUENCE, ""))


class OmissionTests(unittest.TestCase):
    FIRE = ("소화기는 화재의 종류에 맞게 골라야 한다. 일반 화재에는 분말 소화기와 물 소화기를 쓴다. "
            "유류 화재에는 분말 소화기와 이산화탄소 소화기를 쓰고 물 소화기는 쓰지 않는다. 전기 화재에는 이산화탄소 소화기를 쓴다.")
    ROWS = [["일반 화재", "분말 소화기, 물 소화기"], ["유류 화재", "분말 소화기, 이산화탄소 소화기"], ["전기 화재", "이산화탄소 소화기"]]

    def table(self, rows):
        return read_spec({"kind": "table", "title": "화재 종류별 소화기", "header": ["화재 종류", "소화기"], "rows": rows})

    def test_dropped_prohibition_is_reported(self):
        """실제 응답(2026-11-24): 표가 '물 소화기는 쓰지 않는다'를 빠뜨렸다. 근거 검사는 통과하지만 빠진 내용으로 알린다."""
        spec = self.table(self.ROWS)
        self.assertTrue(grounding(spec, self.FIRE).ok)
        found = omissions(spec, self.FIRE)
        self.assertEqual(len(found), 1)
        self.assertIn("물 소화기는 쓰지 않는다", found[0]["reason"])
        self.assertTrue(found[0]["sentence"].startswith("유류 화재에는"))

    def test_kept_prohibition_is_not_reported(self):
        rows = [self.ROWS[0], ["유류 화재", "분말 소화기, 이산화탄소 소화기 (물 소화기는 쓰지 않음)"], self.ROWS[2]]
        self.assertEqual(omissions(self.table(rows), self.FIRE), [])

    def test_item_dropped_from_its_own_row_is_reported(self):
        """실제 응답(2026-11-24, 프롬프트를 고친 뒤): 유류 화재 줄에서 이산화탄소 소화기가 빠졌다. 낱말은 다른 줄에 있어 문장 단위로는 보이지 않는다."""
        rows = [["일반 화재", "분말 소화기, 물 소화기"], ["유류 화재", "분말 소화기 (물 소화기 쓰지 않음)"], self.ROWS[2]]
        found = omissions(self.table(rows), self.FIRE)
        self.assertEqual([entry["reason"] for entry in found], ["'유류 화재'에 빠진 듯한 말: 이산화탄소"])

    def test_unused_sentence_is_reported(self):
        text = TEXT + " 예약 취소는 투숙 전날까지 위약금 없이 받는다."
        found = omissions(read_spec(SEQUENCE), text)
        self.assertEqual([entry["reason"] for entry in found], ["이 문장의 내용이 명세에 쓰이지 않았습니다"] * len(found))
        self.assertTrue(any(entry["sentence"].startswith("예약 취소는") for entry in found))

    def test_omissions_do_not_reject_a_candidate(self):
        entry = candidates([self.table(self.ROWS).as_dict()], self.FIRE)[0]
        self.assertTrue(entry["ok"])
        self.assertEqual(len(entry["omissions"]), 1)


class CandidateTests(unittest.TestCase):
    def test_bad_shape_and_ungrounded_are_kept_with_reasons(self):
        found = candidates([SEQUENCE, {"kind": "cycle", "items": [{"label": "하나"}]},
                            {"kind": "sequence", "items": [{"label": "예약 요청 접수"}, {"label": "신용카드 결제"}]}, TABLE], TEXT)
        self.assertEqual(len(found), 3)                      # 후보는 3개까지만 본다
        self.assertEqual([entry["ok"] for entry in found], [True, False, False])
        self.assertTrue(found[1]["error"])
        self.assertTrue(found[2]["problems"])

    def test_propose_keeps_only_grounded(self):
        result = propose(TEXT, asker=fake([SEQUENCE, {"kind": "sequence", "items": [{"label": "예약 요청 접수"}, {"label": "신용카드 결제"}]}]))
        self.assertEqual((result["method"], result["usable"], len(result["candidates"])), ("llm", 1, 2))
        self.assertEqual(result["candidates"][0]["spec"], SEQUENCE)

    def test_propose_requested_kind_only(self):
        result = propose(TEXT, kind="table", asker=fake([SEQUENCE, TABLE]))
        self.assertEqual([entry["ok"] for entry in result["candidates"]], [False, True])
        self.assertIn("요청한 종류", result["candidates"][0]["error"])

    def test_propose_nothing_to_draw(self):
        result = propose(TEXT, asker=fake([], "정의만 있는 문단"))
        self.assertEqual((result["usable"], result["reason"]), (0, "정의만 있는 문단"))

    def test_propose_criterion_counts_as_source(self):
        spec = {"kind": "sequence", "items": [{"label": "예약 요청 접수"}, {"label": "고객 응대 매뉴얼"}]}
        self.assertEqual(propose(TEXT, asker=fake([spec]))["usable"], 0)
        self.assertEqual(propose(TEXT, "고객 응대 매뉴얼에 따라 예약을 접수할 수 있다.", asker=fake([spec]))["usable"], 1)

    def test_propose_focus_is_not_a_source(self):
        spec = {"kind": "sequence", "items": [{"label": "예약 요청 접수"}, {"label": "환불 처리"}]}
        self.assertEqual(propose(TEXT, focus="환불 처리", asker=fake([spec]))["usable"], 0)

    def test_propose_without_ai_makes_nothing_up(self):
        result = propose(TEXT)          # 테스트 환경에는 키·승인이 없다
        self.assertEqual((result["method"], result["candidates"]), ("none", []))
        self.assertIn("생성형 AI를 쓸 수 없어", result["note"])

    def test_propose_needs_a_paragraph(self):
        with self.assertRaises(ValueError):
            propose("  ", "수행준거만 있음", asker=fake([SEQUENCE]))
        with self.assertRaises(ValueError):
            propose(TEXT, kind="pie", asker=fake([SEQUENCE]))

    def test_task_is_on_the_allow_list(self):
        self.assertTrue(llm.task_allowed("image_generate_spec"))


class TableTextTests(unittest.TestCase):
    def test_html_and_tsv(self):
        spec = read_spec({"kind": "table", "header": ["구분", "내용"], "rows": [["A<B", "x\ty"]]})
        self.assertIn("<th>구분</th>", table_html(spec))
        self.assertIn("A&lt;B", table_html(spec))
        self.assertEqual(table_tsv(spec), "구분\t내용\nA<B\tx y\n")
        with self.assertRaises(SpecError):
            table_html(read_spec(SEQUENCE))


@unittest.skipUnless(font_available(), "한글 글꼴이 없음(fonts/ 또는 시스템 글꼴)")
class RenderTests(unittest.TestCase):
    SPECS = (SEQUENCE, TABLE,
             {"kind": "sequence", "items": [{"label": f"{i}단계 작업", "note": "설명"} for i in range(1, 8)]},
             {"kind": "cycle", "items": [{"label": "계획"}, {"label": "실행"}, {"label": "점검"}, {"label": "개선"}]},
             {"kind": "structure", "root": "로드맵", "items": [{"label": "시장", "children": ["고객 요구"]}, {"label": "기술"}]},
             {"kind": "compare", "items": [{"label": "가 방식", "children": ["순차 진행", "문서 중심"]}, {"label": "나 방식", "children": ["반복 개발"]}]})

    def test_every_kind_renders_at_the_asked_size(self):
        from PIL import Image

        for raw in self.SPECS:
            with self.subTest(kind=raw["kind"]):
                drawn = render(raw, width_mm=150, dpi=300)
                image = Image.open(io.BytesIO(drawn.png))
                self.assertEqual(image.width, round(150 / 25.4 * 300))          # 놓을 폭에서 300 DPI
                self.assertEqual((image.width, image.height), (drawn.width, drawn.height))
                self.assertGreater(image.height, 100)
                self.assertEqual(round(image.info["dpi"][0]), 300)
                self.assertLess(image.convert("L").getextrema()[0], 80)          # 무언가 그려졌다

    def test_same_spec_same_bytes(self):
        first, second = render(SEQUENCE), render(dict(SEQUENCE))
        self.assertEqual(hashlib.sha256(first.png).hexdigest(), hashlib.sha256(second.png).hexdigest())

    def test_width_changes_pixels_not_print_size_of_text(self):
        narrow, wide = render(SEQUENCE, width_mm=80), render(SEQUENCE, width_mm=160)
        self.assertEqual(wide.width, 2 * narrow.width)
        self.assertGreater(narrow.height, wide.height)       # 좁으면 줄이 바뀌어 높아진다

    def test_long_text_stays_inside_the_canvas(self):
        from PIL import Image

        raw = {"kind": "table", "header": ["구분", "내용"], "rows": [["가" * 24, "긴내용" * 20]]}
        image = Image.open(io.BytesIO(render(raw, width_mm=60).png)).convert("L")
        edge = max(1, round(1.0 * 300 / 72))                # 가장자리 1pt에는 글자가 닿지 않는다
        self.assertEqual(image.crop((image.width - edge, edge * 3, image.width, image.height - edge * 3)).getextrema()[0], 255)

    def test_bad_size_and_shape(self):
        with self.assertRaises(ValueError):
            render(SEQUENCE, width_mm=300)
        with self.assertRaises(SpecError):
            render({"kind": "sequence", "items": []})


if __name__ == "__main__":
    unittest.main()
