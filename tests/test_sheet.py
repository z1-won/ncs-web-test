"""검수 확인서 비고 접기(summarize_remarks): 체크 이름당 건수·위치·수정 제안 한 줄."""

import unittest

from ncs_core.sheet import MAX_LOCATIONS, MAX_NOTE_LENGTH, SheetItem, build_sheet, summarize_remarks


class SummarizeRemarksTests(unittest.TestCase):
    def test_counts_locations_and_one_suggestion_line(self):
        checks = [("일치", "X", "상세", "1-1", "통일"), ("일치", "O", "", "1-2", None), ("일치", "X", "상세", "1-3", "통일"),
                  ("개수", "△", "", "1-3", "통일"), ("개수", "O", "", "1-1", None)]
        self.assertEqual(summarize_remarks(checks), [
            "일치: 3건 중 부적합 2건 (1-1, 1-3)",
            "개수: 2건 중 판단불가 1건 (1-3)",
            "— 통일",
        ])

    def test_all_pass_gives_nothing(self):
        self.assertEqual(summarize_remarks([("일치", "O", "", "1-1", None), ("일치", "O", "", "1-2", None)]), [])

    def test_mixed_verdicts_without_location_and_location_cap(self):
        self.assertEqual(summarize_remarks([("형식", "X", "", "", None), ("형식", "△", "", "", None)]),
                         ["형식: 2건 중 부적합 1건·판단불가 1건"])
        many = [("연번", "X", "", f"{i}-1", None) for i in range(1, MAX_LOCATIONS + 3)]
        [line] = summarize_remarks(many)
        self.assertTrue(line.endswith(f"{MAX_LOCATIONS}-1 …)"), line)

    def test_same_location_and_suggestion_counted_once(self):
        checks = [("일치", "X", "", "1-1", "통일"), ("일치", "X", "", "1-1", "통일"), ("개수", "X", "", "1-1", "통일"), ("개수", "O", "", "1-2", None)]
        self.assertEqual(summarize_remarks(checks), ["일치: 2건 중 부적합 2건 (1-1)", "개수: 2건 중 부적합 1건 (1-1)", "— 통일"])


    def test_single_row_check_shows_its_note_and_ignores_non_text_suggestion(self):
        self.assertEqual(summarize_remarks([("번호 찾기", "△", "자동 번호일 수 있음", "1-1", None)]), ["번호 찾기: 자동 번호일 수 있음"])
        self.assertEqual(summarize_remarks([("표", "X", "", "", None)]), ["표: 부적합"])
        [line] = summarize_remarks([("긴", "X", "가" * 200, "", None)])
        self.assertEqual(len(line), len("긴: ") + MAX_NOTE_LENGTH)


class BuildSheetTests(unittest.TestCase):
    def test_sheet_verdict_and_remarks(self):
        rows = [
            {"item_id": "T-①", "위치": "1-1", "체크": {"일치": "X", "개수": "O"}, "비고": {"일치": "상세는 여기"}, "수정 제안": "통일"},
            {"item_id": "T-①", "위치": "1-2", "체크": {"일치": "X", "개수": "△"}, "비고": {}, "수정 제안": "통일"},
            {"item_id": "T-②", "체크": {"형식": "O"}, "비고": {}},
        ]
        items = [SheetItem("①", "하나", ("T-①",)), SheetItem("②", "둘", ("T-②",)), SheetItem("③", "셋", ())]
        sheet = build_sheet(rows, items, "시험")
        self.assertEqual([s["검수결과"] for s in sheet], ["부적합", "적합", "미검사"])
        self.assertEqual(sheet[0]["비고"], "일치: 2건 중 부적합 2건 (1-1, 1-2)\n개수: 2건 중 판단불가 1건 (1-2)\n— 통일")
        self.assertNotIn("상세는 여기", sheet[0]["비고"])
        self.assertEqual(sheet[1]["비고"], "")
        self.assertEqual(sheet[2]["비고"], "규칙 미구현")


if __name__ == "__main__":
    unittest.main()
