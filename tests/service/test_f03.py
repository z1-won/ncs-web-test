"""F03 직능연 검수 체크리스트로 옮기기(ncs_service.f03) — F02 확인서 행을 F03 문항에 묶고, 양식 편집 원고는 적용 문항만 본다."""

import io
import unittest

from ncs_service.f03 import APPLY_ALL, CHECK, NA_TEXT, PASS_TEXT, FAIL_TEXT, build_f03_xlsx, f03_rows


def sheet(verdicts=None):
    """{"구성요소 번호": 검수결과}. 적지 않은 항목은 적합."""
    from ncs_service.export import full_sheet

    rows = full_sheet([])
    for row in rows:
        row["검수결과"], row["비고"] = "적합", ""
    for key, verdict in (verdicts or {}).items():
        component, no = key.split(" ")
        hit = [row for row in rows if row["구성요소"].replace(" ", "").replace("-", "").startswith(component) and row["번호"] == no]
        assert len(hit) == 1, key
        hit[0]["검수결과"] = verdict
    return rows


class F03Tests(unittest.TestCase):
    def test_items_fold_f02_results(self):
        rows = f03_rows(sheet({"필요지식 ⑤": "부적합", "차례 ⑦": "판단불가"}))
        self.assertEqual(len([r for r in rows if r["대상"] == "01 검수 완료 파일"]), 20)
        by = {(r["대상"], r["구분"], r["번호"]): r for r in rows}
        self.assertEqual(by[("01 검수 완료 파일", "학습", "②")]["결과"], FAIL_TEXT)            # 학습목표는 개발계획서를 따르는가 ← 필요 지식 ⑤
        self.assertIn("필요 지식 ⑤ 부적합", by[("01 검수 완료 파일", "학습", "②")]["근거"])
        self.assertEqual(by[("01 검수 완료 파일", "학습", "③")]["결과"], PASS_TEXT)
        self.assertEqual(by[("03 PDF", "차례", "①")]["결과"], CHECK)                           # 판단불가는 적합이 아니다 — 사람 확인
        self.assertEqual(by[("01 검수 완료 파일", "평가", "①")]["결과"], CHECK)                 # 대응하는 F02 항목이 없는 문항(평가 준거 기본 문구)
        self.assertIn("프로그램이 보지 않는 문항", by[("01 검수 완료 파일", "평가", "①")]["근거"])
        self.assertEqual(by[("03 PDF", "표지(앞면)", "①")]["결과"], CHECK)

    def test_form_edit_manuscript_uses_flagged_items_only(self):
        rows = f03_rows(sheet({"필요지식 ⑤": "부적합", "기타 ②": "부적합"}), kind="기존양식편집")
        by = {(r["대상"], r["구분"], r["번호"]): r for r in rows}
        self.assertEqual(by[("01 검수 완료 파일", "학습", "②")]["결과"], NA_TEXT)             # 양식 편집에는 적용하지 않는 문항
        self.assertEqual(by[("01 검수 완료 파일", "기타", "①")]["결과"], FAIL_TEXT)           # 사진 누락은 양식 편집에도 적용
        self.assertEqual(sum(1 for r in rows if r["대상"] == "01 검수 완료 파일" and r["양식 편집 적용"]), 5)
        with self.assertRaises(ValueError):
            f03_rows(sheet(), kind="대충")
        self.assertIn("기존개선", APPLY_ALL)

    def test_xlsx_and_endpoint(self):
        from fastapi.testclient import TestClient
        from openpyxl import load_workbook
        from ncs_web.server import create_app

        book = load_workbook(io.BytesIO(build_f03_xlsx("LM1203020201_24v3", f03_rows(sheet({"수행내용 ③": "부적합"})), kind="기존개선")))
        cells = [str(c.value) for row in book.active.iter_rows() for c in row if c.value]
        self.assertTrue(any("안전유의사항" in text for text in cells))
        self.assertIn(FAIL_TEXT, cells)
        self.assertFalse(any("원고 평가" in text for text in cells))        # 직능연 내부 평가(외부 유출 금지) 줄은 만들지 않는다
        with TestClient(create_app()) as client:
            response = client.post("/api/export/f03?kind=기존개선", json={"module_code": "LM1203020201_24v3", "rows": sheet()})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.content.startswith(b"PK"))
            self.assertEqual(client.post("/api/export/f03?kind=아무거나", json={"module_code": "x", "rows": []}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
