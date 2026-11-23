"""그림 DB(스텁): 만들기, 같은 주제 대체 후보 찾기(similar), 같은 그림 찾기(find — 판정에는 안 씀), 권리 어림값."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ncs_figures.checks import run_checks
from ncs_figures.config import DEFAULT_CONFIG
from ncs_figures.db import StubLookup, build, licensed, rights_of
from ncs_figures.ids import image_id, phash
from ncs_figures.models import Resources

from .test_review_rules import ctx, item, picture


def shrunk_jpeg(data: bytes) -> bytes:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image = image.resize((int(image.width * 0.8), int(image.height * 0.8)))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=70)
    return out.getvalue()


def record(data, module, label, title, source=None, keywords=()):
    return {"image_id": image_id(data), "phash": phash(data), "source": source, "image_file": None,
            "llm": {"keywords": list(keywords)},
            "uses": [{"module": module, "figure_label": label, "figure_title": title, "source_text": (source or {}).get("text"),
                      "element_code": f"{module[2:]}.1", "element_name": "요소"}]}


def make_db(folder: Path, records) -> StubLookup:
    jsonl = folder / "figures.jsonl"
    jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    return StubLookup(Path(build([jsonl], folder / "db.sqlite")["db"]))


class RightsTests(unittest.TestCase):
    def test_rights_guess(self):
        self.assertEqual(rights_of(None)[0], "교육부 귀속")
        self.assertEqual(rights_of({"kind": "공공누리", "kogl_type": "1"})[0], "공공누리 제1유형")
        self.assertEqual(rights_of({"kind": "웹·검색"})[0], "미확인")
        self.assertTrue(licensed("교육부 귀속") and licensed("공공누리 제1유형"))
        self.assertFalse(licensed("미확인") or licensed("공공누리 유형 미상"))
        # 공공누리는 모든 유형(제0~4·AI)을 쓸 수 있는 권리로 본다(2026-11-21)
        self.assertTrue(licensed("공공누리 제0유형") and licensed("공공누리 AI유형"))
        self.assertTrue(licensed("공공누리 제2유형") and licensed("공공누리 제3유형") and licensed("공공누리 제4유형"))
        self.assertEqual(rights_of({"kind": "공공누리", "kogl_type": "AI"})[0], "공공누리 AI유형")


class SimilarTests(unittest.TestCase):
    def setUp(self):
        self.lookup = make_db(Path(tempfile.mkdtemp()), [
            record(picture(seed=1), "LM2001010401_19v4", "그림 2-3", "SW제품의 응용 시스템 구성도"),
            record(picture(seed=2), "LM2001010402_19v4", "그림 1-1", "목표 시스템 구성도 예시", source={"kind": "웹·검색", "text": "출처: 블로그"}),
            record(picture(seed=3), "LM2001010403_19v4", "그림 3-1", "손익분기점 그래프"),
            record(picture(seed=4), "LM2001010409_19v4", "그림 1-1", "응용 시스템 구성도"),     # 검수 중인 모듈 — 빠져야 함
        ])

    def test_same_topic_found_and_licensed_first(self):
        found = self.lookup.similar("SW제품의 응용 시스템 구성도 예시", exclude_module="LM2001010409_19v4")
        modules = [c["module"] for c in found]
        self.assertIn("LM2001010401_19v4", modules)
        self.assertNotIn("LM2001010409_19v4", modules)             # 자기 모듈 제외
        self.assertNotIn("LM2001010403_19v4", modules)             # 다른 주제
        self.assertTrue(found[0]["licensed"])                       # 재사용 가능한 권리 먼저
        self.assertIn("구성도", found[0]["common"])

    def test_keywords_help(self):
        found = self.lookup.similar("수익 분석", keywords=["손익분기점", "그래프"])
        self.assertEqual(found[0]["module"], "LM2001010403_19v4")

    def test_no_title_no_candidates(self):
        self.assertEqual(self.lookup.similar(""), [])


class FindTests(unittest.TestCase):
    def test_exact_and_resized_copy(self):
        original = picture(seed=5)
        lookup = make_db(Path(tempfile.mkdtemp()), [record(original, "LM2001010401_19v4", "그림 2-3", "설문")])
        self.assertEqual(lookup.find(image_id(original), phash(original))[0][0].match_type, "exact")
        copy = shrunk_jpeg(original)
        self.assertEqual(lookup.find(image_id(copy), phash(copy))[0][0].match_type, "near")
        self.assertEqual(lookup.find(image_id(original), phash(original), exclude_module="LM2001010401_19v4"), [])



class DbRiskTests(unittest.TestCase):
    """④ DB 대조가 같은 그림을 찾으면 위험도 규칙(H1·H2·H3·M2)의 입력이 된다(2026-11-21 다시 넣음)."""

    def judge(self, source, db_source=None):
        from ncs_figures.pipeline import review_figures
        data = picture(seed=7)
        lookup = make_db(Path(tempfile.mkdtemp()), [record(data, "LM2001010401_19v4", "그림 2-3", "설문", source=db_source)])
        from .test_review_rules import captions
        c = ctx(source=source, data=data)
        [review] = review_figures([item(c)], Resources(lookup=lookup, asker=captions([c])), cfg=DEFAULT_CONFIG,
                                  module_code="LM2001010409_19v4")
        return review.risk, {c.name: c for c in review.checks}["④DB 대조"], " ".join(review.risk_reasons)

    def test_no_match_is_fine(self):
        lookup = make_db(Path(tempfile.mkdtemp()), [record(picture(seed=7), "LM2001010401_19v4", "그림 2-3", "설문")])
        checks, _ = run_checks(item(ctx(data=picture(size=(200, 200), seed=40))), Resources(lookup=lookup), DEFAULT_CONFIG)
        self.assertEqual({c.name: c for c in checks}["④DB 대조"].value, "O")

    def test_h1_no_source(self):
        risk, check, why = self.judge(None)
        self.assertEqual((risk, check.value), ("고위험", "X"))
        self.assertIn("[권리] 출처 표기가 없는데 기존 그림", why)

    def test_h2_unlicensed(self):
        risk, check, why = self.judge("출처: 홍길동(2020). 블로그 글. https://example.com 에서 2026. 1. 2. 검색.",
                                      db_source={"kind": "웹·검색", "text": "출처: 홍길동(2020). 블로그 글."})
        self.assertEqual((risk, check.value), ("고위험", "X"))
        self.assertIn("재사용 근거 없음", why)

    def test_h3_claimed_own(self):
        risk, check, why = self.judge("출처: 집필진 제작(2026)")
        self.assertEqual((risk, check.value), ("고위험", "X"))
        self.assertIn("[출처] 출처를 집필진 제작으로 적었으나", why)

    def test_reuse_with_right_source(self):
        cite = "출처: 교육부(2019). 설문(LM2001010401_19v4). 한국직업능력연구원. p.12."
        risk, check, why = self.judge(cite)
        self.assertEqual((risk, check.value), ("문제없음", "O"))
        self.assertIn("기존 그림 재사용", why)
        risk, check, why = self.judge(cite.replace("LM2001010401", "LM2001010402"))      # 다른 모듈을 인용 → 출처 정정
        self.assertEqual((risk, check.value), ("확인 필요", "△"))
        self.assertIn("[출처] 출처가 DB의 원래 출처와 다름", why)


class RiskRuleTests(unittest.TestCase):
    """OCR·캡션 판정 결과(prior)를 쓰는 규칙 — H5 스톡 워터마크, M4 캡션 mismatch만, 형식은 위험도 밖."""

    def assess(self, prior, source="출처: 집필진 제작(2026)"):
        from ncs_figures.risk import assess
        checks, _ = run_checks(item(ctx(source=source)), Resources(), DEFAULT_CONFIG)
        return assess(checks, (), item(ctx(source=source)), prior=prior)

    def test_stock_watermark_is_high(self):
        self.assertEqual(self.assess({"marks_found": {"stock": ["shutterstock"], "copyright": []}})[0], "고위험")

    def test_copyright_without_source_is_high(self):
        self.assertEqual(self.assess({"marks_found": {"copyright": ["©"]}}, source=None)[0], "고위험")

    def test_caption_only_mismatch_raises(self):
        from ncs_core.text import TRI
        from ncs_figures.models import CheckOutcome
        from ncs_figures.risk import assess
        it = item(ctx())
        base, _ = run_checks(it, Resources(), DEFAULT_CONFIG)
        cap = [CheckOutcome("③캡션 일치", TRI, "캡션과 다를 수 있음 — 막대그래프인데 캡션은 조직도")]
        self.assertEqual(assess(base + cap, (), it, prior={"caption_verdict": "mismatch"})[0], "확인 필요")
        level, why = assess(base + cap, (), it, prior={"caption_verdict": "uncertain"})
        self.assertEqual(level, "문제없음")
        self.assertIn("위험도에 넣지 않음", " ".join(why))


if __name__ == "__main__":
    unittest.main()
