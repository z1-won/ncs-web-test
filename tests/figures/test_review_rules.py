"""ncs_figures R1(005 규칙 점검): 식별·해시, 그림 종류, 외부 전송 표시, 점검 ①⑦⑨, 미실행 처리, 위험도, 행·요약·검수표."""

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image

from ncs_core.figure_context import FigureContext
from ncs_core.source_line import parse_ai_marker, parse_source
from ncs_figures.checks import run_checks
from ncs_figures.config import DEFAULT_CONFIG
from ncs_figures.ids import hamming, image_id, phash
from ncs_figures.link import RecordingLink
from ncs_figures.models import FigureItem, FigureReviewResult, Resources
from ncs_figures.pipeline import review_figures
from ncs_figures.report import write_html
from ncs_figures.rows import summarize, to_row
from ncs_figures.select import classify, transfer_of


def picture(fmt="PNG", size=(120, 80), seed=0):
    image = Image.new("RGB", size, "white")
    for x in range(10, 60):
        for y in range(10 + seed, 40 + seed):
            image.putpixel((x, y), (20, 40, 160))
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return buffer.getvalue()


def ctx(caption="[그림 1-1] 가", source="출처: 집필진 제작(2026)", ai=None, mm=(150, 80), data=None):
    label = "그림 1-1" if caption else None
    return FigureContext(section=1, para=10, bin_id="B", format="png", px=(120, 80), size_hwp=(0, 0), mm=mm, dpi=150,
                         data=data or picture(), caption=caption, caption_para=12 if caption else None, figure_label=label,
                         source_line=source, source_para=11 if source else None, ai_marker_line=ai,
                         ai_marker_para=11 if ai and not source else (12 if ai else None), region_path="section1 > 학습 1 > [그림 1-1]")


def item(c, kind=None, transfer=None):
    src = parse_source(c.source_line) if c.source_line else None
    transfer, why = transfer_of(src, DEFAULT_CONFIG, override=transfer)
    return FigureItem(ctx=c, image_id=image_id(c.data), file_sha256="", phash=phash(c.data),
                      kind=kind or classify(c, image_id(c.data), templates=frozenset(), cfg=DEFAULT_CONFIG),
                      source=src, ai=parse_ai_marker(c.ai_marker_line) if c.ai_marker_line else None,
                      transfer=transfer, transfer_reason=why)


def captions(contexts, verdict="match"):
    """③ 캡션 판정을 이미 받은 것처럼(그림 판독 결과) — 위험도는 ③이 있어야 정해진다(없으면 '판정 안 함')."""
    from ncs_figures.reading import RecordedCaptions
    judged = {image_id(c.data): {"status": "완료", "판정": verdict, "근거": "시험", "읽은 글자": [], "검증": "통과", "model": "test"}
              for c in contexts if c.caption}
    return RecordedCaptions(judged, "test")


def outcome(checks, name):
    return next(c for c in checks if c.name == name)


class IdsTests(unittest.TestCase):
    def test_image_id_is_pixel_based(self):
        self.assertEqual(image_id(picture("PNG")), image_id(picture("BMP")))
        self.assertNotEqual(image_id(picture(seed=0)), image_id(picture(seed=20)))
        self.assertIsNone(image_id(b"not an image"))

    def test_phash_survives_resize(self):
        small = Image.open(io.BytesIO(picture())).resize((60, 40))
        buffer = io.BytesIO()
        small.save(buffer, "PNG")
        self.assertLessEqual(hamming(phash(picture()), phash(buffer.getvalue())), 8)


class SelectTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(classify(ctx(), "x", templates=frozenset({"x"}), cfg=DEFAULT_CONFIG), "양식")
        self.assertEqual(classify(ctx(), "y", templates=frozenset(), cfg=DEFAULT_CONFIG), "본문 그림")
        self.assertEqual(classify(ctx(caption="", mm=(92, 7)), "y", templates=frozenset(), cfg=DEFAULT_CONFIG), "양식 후보")
        self.assertEqual(classify(ctx(caption="", mm=(52, 23)), "y", templates=frozenset(), cfg=DEFAULT_CONFIG), "캡션 없는 그림")

    def test_all_figures_sent(self):
        """2026-11-21: 출처 종류와 상관없이 모두 보낸다. 사람이 정한 값과 FIG_TRANSFER_OTHERS로는 막을 수 있다."""
        cfg = replace(DEFAULT_CONFIG, transfer_others="허용")
        kogl = lambda t: parse_source(f"출처: 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 1. 15. 검색. 공공누리 {t}.")  # noqa: E731
        gongu = parse_source("출처: 사진(2020). 공유마당(https://gongu.copyright.or.kr)에서 2026. 1. 15. 검색.")
        for source in (kogl("제1유형"), kogl("제3유형"), gongu, parse_source("출처: 집필진 제작(2026)"), None):
            self.assertEqual(transfer_of(source, cfg)[0], "허용")
        self.assertEqual(transfer_of(None, cfg, override="금지")[0], "금지")
        closed = replace(DEFAULT_CONFIG, transfer_others="확인 전")
        self.assertEqual(transfer_of(kogl("제1유형"), closed)[0], "확인 전")


class CheckTests(unittest.TestCase):
    def run_one(self, c, kind=None):
        checks, _ = run_checks(item(c, kind), Resources(), DEFAULT_CONFIG)
        return checks

    def test_source_present_format_and_requirements(self):
        checks = self.run_one(ctx())
        self.assertEqual([outcome(checks, n).value for n in ("①출처 있음", "①출처 형식", "①출처 요건")], ["O", "O", "-"])
        missing = self.run_one(ctx(source=None))
        self.assertEqual(outcome(missing, "①출처 있음").value, "X")
        web = self.run_one(ctx(source="출처: 객실 통계(2025). 한국관광공사 홈페이지(https://kto.or.kr)."))
        self.assertEqual(outcome(web, "①출처 요건").value, "X")              # 확인 일자 없음(계약서 제4조 3항)
        spacing = self.run_one(ctx(source="출처:집필진 제작(2026)"))
        self.assertEqual(outcome(spacing, "①출처 형식").value, "X")

    def test_captionless_is_human_check(self):
        checks = self.run_one(ctx(caption="", source=None, mm=(52, 23)))
        self.assertEqual(outcome(checks, "①출처 있음").value, "△")
        self.assertFalse(any(c.name.startswith("⑦") for c in checks))      # 본문 그림 점검은 하지 않음

    def test_ai_marker_and_third_party(self):
        ok = self.run_one(ctx(ai="ChatGPT를 활용하여 생성함. 2026. 7. 20."))
        self.assertEqual(outcome(ok, "⑦AI 표기").value, "O")
        no_date = self.run_one(ctx(ai="ChatGPT를 활용하여 생성함."))
        self.assertEqual(outcome(no_date, "⑦AI 표기").value, "X")
        third = self.run_one(ctx(source="출처: 교육부(2018). 공급망 공정계획(LM0204010404_16v2). 한국직업능력개발원. p.6.",
                                 ai="ChatGPT를 활용하여 수정 보완함. 2026. 7. 20."))
        self.assertEqual(outcome(third, "⑨제3자 원본").value, "△")
        self.assertEqual(outcome(self.run_one(ctx()), "⑦AI 표기").value, "-")   # 표기 없으면 추정하지 않음

    def test_checks_moved_from_008(self):
        """출처 검토(008) 화면에서 그림 출처를 빼면서 옮겨 온 점검 — 옛 기관 명칭, AI 생성·수정 구분(표시만)."""
        old = self.run_one(ctx(source="출처: 교육부(2018). 공급망 공정계획(LM0204010404_16v2). 한국직업능력개발원. p.6."))
        self.assertEqual(outcome(old, "①기관 명칭").value, "△")
        made = self.run_one(ctx(source="출처: 교육부(2018). 공급망 공정계획(LM0204010404_16v2). 한국직업능력연구원. p.6.",
                                ai="ChatGPT를 활용하여 생성함. 2026. 7. 20."))
        self.assertEqual(outcome(made, "⑦생성·수정 구분").value, "△")
        self.assertEqual(outcome(self.run_one(ctx(ai="ChatGPT를 활용하여 생성함. 2026. 7. 20.")), "⑦생성·수정 구분").value, "O")

    def test_missing_resources_are_skipped_not_passed(self):
        checks = self.run_one(ctx())
        skipped = {c.name: c.skipped for c in checks if c.value is None}
        for name in ("③캡션 일치", "⑥수록 현황", "②마크·워터마크", "④DB 대조"):
            self.assertIn(name, skipped)
        self.assertTrue(all(c.value is None for c in checks if c.skipped))


class RiskAndOutputTests(unittest.TestCase):
    def review(self, contexts):
        return review_figures([item(c) for c in contexts], Resources(asker=captions(contexts)), cfg=DEFAULT_CONFIG)

    def test_no_caption_check_blocks_risk(self):
        """③ 캡션 일치를 안 했으면 위험도를 정하지 않는다 — 찾은 문제는 [판독 전]으로 남긴다(2026-11-21)."""
        fine, missing = review_figures([item(ctx()), item(ctx(source=None))], Resources(), cfg=DEFAULT_CONFIG)
        self.assertEqual((fine.risk, missing.risk), ("판정 안 함", "판정 안 함"))
        self.assertIn("[미실행] ③캡션 일치", fine.risk_reasons[0])
        self.assertIn("[판독 전] 확인 필요: [출처] 출처 표기 없음", " ".join(missing.risk_reasons))
        self.assertFalse(to_row(missing)["03-003 연계"])
        self.assertEqual(summarize([fine, missing])["위험도"]["판정 안 함"], 2)
        captionless = ctx(caption="", source=None, mm=(52, 23))               # ③은 캡션 있는 그림만 — 캡션 없는 그림은 막지 않음
        [only] = review_figures([item(captionless)], Resources(), cfg=DEFAULT_CONFIG)
        self.assertEqual(only.risk, "확인 필요")

    def test_risk_levels(self):
        fine, fmt, missing, captionless = self.review([
            ctx(), ctx(source="출처:집필진 제작(2026)"), ctx(source=None), ctx(caption="", source=None, mm=(52, 23))])
        self.assertEqual(fine.risk, "문제없음")
        self.assertEqual(fmt.risk, "문제없음")                       # 형식 오류만 → 위험도에 넣지 않음
        self.assertIn("[표기 형식]", " ".join(fmt.risk_reasons))
        self.assertEqual(missing.risk, "확인 필요")
        self.assertEqual(captionless.risk, "확인 필요")
        self.assertIn("미실행", " ".join(fine.risk_reasons))          # 문제없음에도 미실행 점검을 근거에 적음
        [unsure] = review_figures([item(ctx())], Resources(asker=captions([ctx()], "uncertain")), cfg=DEFAULT_CONFIG)
        self.assertEqual(unsure.risk, "문제없음")                       # ③ 근거 부족은 위험도에 넣지 않음(실행은 됨)

    def test_around_text_drops_own_caption(self):
        """주변 글(앞·뒤 문단)에 그림 자신의 캡션·출처 줄은 넣지 않는다."""
        c = replace(ctx(), after=("[그림 1-1] 가", "출처: 집필진 제작(2026)", "다음 문단은 본문이다."), before=("앞 문단이다.",))
        row = to_row(self.review([c])[0])
        self.assertEqual(row["문맥"]["뒤"], ["다음 문단은 본문이다."])
        self.assertEqual(row["문맥"]["앞"], ["앞 문단이다."])

    def test_templates_are_not_reviewed(self):
        [template] = review_figures([item(ctx(), kind="양식")], Resources(), cfg=DEFAULT_CONFIG)
        self.assertIsNone(template.risk)

    def test_rows_summary_link_and_html(self):
        reviews = self.review([ctx(), ctx(source=None)])
        rows = [to_row(r) for r in reviews]
        self.assertEqual(rows[1]["판정"], "부적합")
        self.assertTrue(rows[1]["03-003 연계"])
        self.assertEqual(rows[0]["출처 해석"]["source_kind"], "집필진 제작")
        summary = summarize(reviews)
        self.assertEqual(summary["위험도"], {"고위험": 0, "확인 필요": 1, "문제없음": 1, "판정 안 함": 0})
        with tempfile.TemporaryDirectory() as tmp:
            link = RecordingLink(Path(tmp) / "calls.jsonl")
            for row in rows:
                if row["03-003 연계"]:
                    link.notify(row)
            self.assertEqual(link.count, 1)
            result = FigureReviewResult("LM0000000000_00v0", tuple(reviews), rows, summary)
            html = write_html(result, Path(tmp) / "표.html", title="시험").read_text(encoding="utf-8")
            self.assertIn("이미지 검수표", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertNotIn("침해", html)                            # 법적 단정 문구 없음


if __name__ == "__main__":
    unittest.main()
