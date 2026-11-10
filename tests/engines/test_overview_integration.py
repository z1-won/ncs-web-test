"""개요 ⑦: 능력단위 요소를 통합한 학습의 코드·명칭 기재."""

import unittest

from ncs_overview.rules.structure import check_structure_integration

PLAN = {"요소": [{"code": "1203020201_24v3.1", "name": "객실 정보 파악하기"}, {"code": "1203020201_24v3.2", "name": "예약 현황 확인하기"},
                 {"code": "1203020201_24v3.3", "name": "고객 이력 확인하기"}]}


def overview(elements, lessons=({"no": 1, "text": "가", "row": 2}, {"no": 2, "text": "나", "row": 5})):
    return {"내용체계": {"학습": list(lessons), "요소": elements, "내용": [], "근거": "표"}}


class IntegrationTests(unittest.TestCase):
    def test_integrated_lesson_with_full_pairs_passes(self):
        ov = overview([{"code": "1203020201_24v3.1", "name": "객실 정보 파악하기", "row": 2}, {"code": "1203020201_24v3.2", "name": "예약 현황 확인하기", "row": 3},
                       {"code": "1203020201_24v3.3", "name": "고객 이력 확인하기", "row": 5}])
        [row] = check_structure_integration(ov, PLAN)
        self.assertEqual((row["위치"], row["판정"]), ("학습 1", "적합"))

    def test_missing_or_wrong_name_fails(self):
        ov = overview([{"code": "1203020201_24v3.1", "name": "", "row": 2}, {"code": "1203020201_24v3.2", "name": "엉뚱한 이름", "row": 3}])
        [row] = check_structure_integration(ov, PLAN)
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("명칭 없음", row["비고"]["⑦ 통합 요소의 코드·명칭 모두 기재"])
        self.assertIn("계획서 \"예약 현황 확인하기\"", row["비고"]["⑦ 통합 요소의 코드·명칭 모두 기재"])

    def test_no_integration_is_not_applicable_and_missing_table_fails(self):
        ov = overview([{"code": "1203020201_24v3.1", "name": "객실 정보 파악하기", "row": 2}, {"code": "1203020201_24v3.2", "name": "예약 현황 확인하기", "row": 5}])
        [row] = check_structure_integration(ov, PLAN)
        self.assertEqual((row["판정"], row["체크"]), ("적합", {"⑦ 통합 요소의 코드·명칭 모두 기재": "-"}))
        self.assertEqual(check_structure_integration({"내용체계": None}, PLAN)[0]["판정"], "부적합")  # 표 없음은 ⑤⑥과 같이 X


if __name__ == "__main__":
    unittest.main()
