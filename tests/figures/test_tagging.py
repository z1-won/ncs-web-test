"""009 태깅·내보내기: 카탈로그 연결(요소·수행준거), 합치기(image_id·출처 다름), 사람이 고친 값 반영, CSV·확인 표."""

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ncs_figures.export import merge, read_overrides
from ncs_figures.tagging import link_criteria, link_element, min_px_300dpi, module_info, priority

DETAIL = {"code": "2001010409_19v4", "name": "SW제품 판매 계획 수립", "elements": [
    {"code": "2001010409_19v4.1", "no": 1, "name": "SW제품 인증 기획하기",
     "criteria": ["1.1 제품의 기능 명세를 바탕으로 국내외 인증 제도를 조사할 수 있다.",
                  "1.2 인증 획득 계획에 따라 인증 포트폴리오를 작성할 수 있다."]}]}


class FakeCatalog:
    def unit_detail(self, code):
        return DETAIL if code.replace("LM", "")[:10] == "2001010409" else None


class LinkTests(unittest.TestCase):
    def test_module_and_unit(self):
        info = module_info(Path("LM2001010409_19v4_SW제품 판매 계획 수립.hwpx"), FakeCatalog())
        self.assertEqual((info["code"], info["title"], info["unit_code_match"]), ("LM2001010409_19v4", "SW제품 판매 계획 수립", "정확"))
        old = module_info(Path("LM2001010409_14v2_옛판.hwpx"), FakeCatalog())
        self.assertEqual(old["unit_code_match"], "버전 다름")
        self.assertIsNone(module_info(Path("원고.hwpx"), FakeCatalog())["code"])

    def test_element_by_lesson(self):
        self.assertEqual(link_element(DETAIL, 1, "SW제품 인증 기획하기")["element_check"], "일치")
        self.assertEqual(link_element(DETAIL, 1, "SW 제품 인증 기획하기")["element_check"], "일치")      # 띄어쓰기만 다름 — 태깅에선 같은 요소
        self.assertEqual(link_element(DETAIL, 1, "SW제품 인증 계획하기")["element_check"], "이름 다름")
        self.assertEqual(link_element(DETAIL, 1, None)["element_code"], "2001010409_19v4.1")
        self.assertIsNone(link_element(DETAIL, None, None)["element_code"])

    def test_criteria_from_goals(self):
        codes, problem = link_criteria(DETAIL, 1, ["• 제품의 기능 명세를 바탕으로 국내외 인증 제도를 조사할 수 있다."])
        self.assertEqual((codes, problem), (["1.1"], None))
        self.assertEqual(link_criteria(DETAIL, 1, ["• 전혀 관계없는 목표 문장이다."]), ([], "수행준거 연결 약함"))
        self.assertEqual(link_criteria(DETAIL, 1, [])[1], "학습 목표를 읽지 못함")

    def test_helpers(self):
        self.assertEqual(min_px_300dpi((25.4, 50.8)), [300, 600])
        self.assertEqual(priority(["학습명과 능력단위요소명이 다름", "출처 줄 없음"]), 1)


def record(key, module, source, reasons=(), para=1):
    use = {"module": module, "file": f"{module}.hwpx", "section": 1, "para": para, "figure_label": "그림 1-1", "figure_title": "가",
           "caption": "[그림 1-1] 가", "region_path": "", "lesson": 1, "content_no": "1-1", "element_code": None, "element_name": None,
           "element_check": None, "performance_criteria": ["1.1"], "source_text": source, "page": None, "page_estimate": None,
           "mm": [100, 50], "dpi": 96, "min_px_300dpi": [1181, 591], "in_table": False}
    return {"image_id": key, "format": "png", "px": [10, 10], "source": {"text": source, "kind": "집필진 제작"} if source else None,
            "ai_marker": None, "rule_type": None, "llm": {"status": "미실행"}, "uses": [use], "review_reasons": list(reasons),
            "needs_human_review": bool(reasons), "overridden": [], "pipeline_version": "t",
            "module": {"code": module, "title": "t", "file": f"{module}.hwpx", "unit_code": None, "unit_name": None, "unit_code_match": "없음"}}


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        (self.out / "modules").mkdir()

    def write(self, name, records):
        (self.out / "modules" / f"{name}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")

    def test_same_image_across_modules(self):
        self.write("A", [record("img1", "LMA", "출처: 집필진 제작(2025)")])
        self.write("B", [record("img1", "LMB", "출처: 교육부(2018). 가(LM0000000000_16v2). p.3."), record("img2", "LMB", None, ["출처 줄 없음"])])
        summary = merge(self.out)
        self.assertEqual((summary["그림(image_id)"], summary["여러 원고에 쓰인 그림"], summary["쓰인 자리"]), (2, 1, 3))
        merged = {r["image_id"]: r for r in map(json.loads, (self.out / "figures.jsonl").read_text(encoding="utf-8").splitlines())}
        self.assertEqual(merged["img1"]["modules"], ["LMA", "LMB"])
        self.assertIn("같은 그림인데 원고마다 출처가 다름", merged["img1"]["review_reasons"])
        with open(self.out / "figures.csv", encoding="utf-8-sig") as f:
            self.assertEqual(len(list(csv.reader(f))), 1 + 3)     # 머리 + 자리 3
        with open(self.out / "review.tsv", encoding="utf-8-sig") as f:
            self.assertEqual(len(list(csv.reader(f, delimiter="\t"))), 1 + 2)

    def test_overrides_from_review_sheet(self):
        self.write("A", [record("img2", "LMA", None, ["출처 줄 없음"])])
        merge(self.out)
        with open(self.out / "review.tsv", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f, delimiter="\t"))
        header, row = rows[0], rows[1]
        row[header.index("필드")], row[header.index("고친 값")] = "source.kind", "집필진 제작"
        with open(self.out / "overrides.tsv", "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f, delimiter="\t").writerows([header, row])
        self.assertEqual(read_overrides(self.out / "overrides.tsv"), {"img2": {"source.kind": "집필진 제작"}})
        summary = merge(self.out, overrides=self.out / "overrides.tsv")
        fixed = json.loads((self.out / "figures.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((fixed["source"]["kind"], fixed["overridden"], fixed["needs_human_review"]), ("집필진 제작", ["source.kind"], False))
        self.assertEqual((summary["고친 값 반영"], summary["사람 확인"]), (1, 0))


SAMPLE = next(Path(__file__).resolve().parents[2].glob("samples/최종본_SW제품기획/LM2001010409_19v4_*.hwpx"), None)


@unittest.skipIf(SAMPLE is None, "최종본 원고 없음")
class FinalManuscriptTests(unittest.TestCase):
    def setUp(self):
        # golden_cases가 NCS_CATALOG_FILE을 없는 파일로 두어 목록을 끈다 — 이 시험 동안만 패키지 기본 목록을 쓴다(test_plan과 같음)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("NCS_CATALOG_FILE", None)

    def test_tag_one_final(self):
        from ncs_figures.export import tag_folder
        out = Path(tempfile.mkdtemp())
        manifest = tag_folder([SAMPLE], out, log=lambda *_: None)
        self.assertEqual(manifest["합계"]["완료"], 1)
        records = [json.loads(line) for line in next((out / "modules").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()]
        self.assertTrue(records)
        self.assertTrue(all(r["module"]["unit_code_match"] == "정확" for r in records))
        self.assertTrue(any(u["performance_criteria"] for r in records for u in r["uses"]))
        self.assertEqual(len(list((out / "images").glob("*.png"))), len(records))
        again = tag_folder([SAMPLE], out, log=lambda *_: None)                  # 두 번째는 건너뜀
        self.assertEqual(again["원고"], manifest["원고"])


if __name__ == "__main__":
    unittest.main()
