"""위치 ②③④: 목록 비교 요약(summarize_diff)과 체크별 비고·방향 문장."""

import unittest

from ncs_position.compare import list_diff, summarize_diff
from ncs_position.pipeline import reference_module_name, resolve_module_name
from ncs_position.rules.emphasis import check_emphasis
from ncs_position.rules.position import check_position

PLAN = {"세분류": [f"세분류{i}" for i in range(1, 19)], "능력단위": ["가", "나", "다"], "학습모듈명": ["가", "나", "다"],
        "행쌍": [("가", "가"), ("나", "나"), ("다", "다")]}


class DiffTests(unittest.TestCase):
    def test_summary_counts_missing_and_changed(self):
        content, order, notes, info = list_diff("세분류", PLAN["세분류"], PLAN["세분류"][:8])
        self.assertEqual((content, order, len(info["missing"])), ("X", "O", 10))
        self.assertEqual(summarize_diff("세분류", info), "세분류 원고 8 / 개발계획서 18 · 누락 10(개발계획서에만: 세분류9, 세분류10, 세분류11 외 7)")
        content, order, notes, info = list_diff("능력단위", ["가", "나", "다"], ["가", "라", "다"])
        self.assertEqual(summarize_diff("능력단위", info), "능력단위 다름 1: 원고 「라」, 개발계획서 「나」 (글자가 다름)")
        # 띄어쓰기 하나 차이도 어느 문서의 어떤 문구인지 각각 보인다
        _, _, notes, info = list_diff("능력단위", ["AIoT 운영플랫폼요구사항분석"], ["AIoT 운영 플랫폼 요구사항 분석"])
        self.assertEqual(summarize_diff("능력단위", info), "능력단위 다름 1: 원고 「AIoT 운영 플랫폼 요구사항 분석」, 개발계획서 「AIoT 운영플랫폼요구사항분석」 (띄어쓰기만 다름)")
        self.assertEqual(notes, ["능력단위 1번째 다름: 원고 「AIoT 운영 플랫폼 요구사항 분석」, 개발계획서 「AIoT 운영플랫폼요구사항분석」 (띄어쓰기만 다름)"])
        _, _, notes, _ = list_diff("능력단위", ["가", "나"], ["가", "다", "라"])
        self.assertEqual(notes[1:], ["능력단위 누락: 개발계획서에는 「나」가 있는데 원고에 없음", "능력단위 원고에만 있음: 「다」 (개발계획서에 없음)", "능력단위 원고에만 있음: 「라」 (개발계획서에 없음)"])
        self.assertEqual(summarize_diff("능력단위", list_diff("능력단위", ["가", "나"], ["나", "가"])[3]), "능력단위 순서 다름")


class PositionRuleTests(unittest.TestCase):
    def test_notes_per_check_and_direction_suggestion(self):
        manuscript = {"세분류": PLAN["세분류"][:8], "능력단위": ["가", "나", "다"], "학습모듈명": ["가", "나", "다"], "행쌍": PLAN["행쌍"]}
        [row] = check_position(PLAN, manuscript)
        self.assertEqual(row["판정"], "부적합")
        self.assertEqual(set(row["비고"]), {"② 세분류 목록·순서 일치"})
        self.assertTrue(row["비고"]["② 세분류 목록·순서 일치"].startswith("세분류 원고 8 / 개발계획서 18 · 누락 10("))
        self.assertEqual(row["수정 제안"], "개발계획서의 세분류 18개를 순서대로 모두 나열")
        self.assertEqual(len(row["상세"]), 11)  # 개수 1 + 누락 10
        [ok] = check_position(PLAN, {**manuscript, "세분류": PLAN["세분류"]})
        self.assertEqual((ok["판정"], ok["비고"], ok["수정 제안"]), ("적합", {}, None))


def styled_table(names, bold_row):
    """세분류·능력단위·학습모듈명 표. bold_row(0부터)만 KoPub돋움체 Bold + 음영."""
    cells = {(0, 0): "세분류", (0, 1): "능력단위", (0, 2): "학습모듈명", (1, 0): "응용SW"}
    styles = {}
    for r, name in enumerate(names, 1):
        for c in (1, 2):
            cells[(r, c)] = name
            emphasised = r - 1 == bold_row
            styles[(r, c)] = {"fill": "#D9D9D9" if emphasised else None,
                              "runs": [{"font": "KoPub돋움체", "bold": emphasised}]}
    return {"cells": cells, "styles": styles, "paragraph": 0}


class EmphasisRowSelectionTests(unittest.TestCase):
    """⑤ 해당 행 고르기: 개발계획서 '학습 모듈명' 칸이 없을 때 기준 표의 능력단위 번호째 행 이름으로 찾는다."""

    POSITION = {"세분류": ["가", "나"], "능력단위": ["요구사항 분석", "구축 계획 수립", "데이터 수집"],
                "학습모듈명": ["요구사항 분석", "구축 계획 수립", "데이터 수집"], "행쌍": []}

    def test_reference_module_name_is_unit_number_th_row(self):
        self.assertEqual(reference_module_name(self.POSITION, "LM2001021702_25v1"), "구축 계획 수립")
        self.assertEqual(reference_module_name(self.POSITION, "LM2001021709_25v1"), None, "표에 9번째 행이 없으면 None")
        self.assertEqual(reference_module_name({**self.POSITION, "학습모듈명": []}, "LM2001021703_25v1"), "데이터 수집",
                         "학습모듈명 열이 비면 능력단위명")
        self.assertEqual(reference_module_name(None, "LM2001021701_25v1"), None)
        self.assertEqual(reference_module_name(self.POSITION, "LM12"), None)

    def test_resolve_prefers_plan_then_reference_table(self):
        plan_sections = [["능력단위 코드번호", "2001021702_25v1", "학습 모듈명", "구축 계획 수립(계획서)", "NCS (수정 금지)"]]
        self.assertEqual(resolve_module_name("LM2001021702_25v1", plan_sections, self.POSITION, "개발계획서"),
                         ("구축 계획 수립(계획서)", "개발계획서"))
        # 계획서에 '학습 모듈명' 칸이 없으면 기준 표의 2번째 행
        self.assertEqual(resolve_module_name("LM2001021702_25v1", [["아무 줄"]], self.POSITION, "개발계획서"),
                         ("구축 계획 수립", "개발계획서 위치 표"))
        self.assertEqual(resolve_module_name("LM2001021709_25v1", [["아무 줄"]], self.POSITION, "개발계획서"), (None, "없음"))

    def test_emphasis_uses_resolved_name_and_names_its_source(self):
        # 표의 행 순서가 NCS 순서와 다르면(1·2행 바뀜) 코드 번호 순번(2번째)은 틀린 행을 짚지만 이름으로는 맞는 행을 찾는다
        table = styled_table(["구축 계획 수립", "요구사항 분석", "데이터 수집"], bold_row=0)
        [row, *_] = check_emphasis(table, "LM2001021702_25v1", "구축 계획 수립", name_source="개발계획서 위치 표")
        self.assertEqual(row["판정"], "적합")
        self.assertEqual(row["해당 행 근거"], '개발계획서 위치 표 학습모듈명 "구축 계획 수립" 과 일치하는 행')
        [row, *_] = check_emphasis(table, "LM2001021702_25v1", None)
        self.assertEqual(row["판정"], "부적합", "이름이 없으면 코드 순번(2번째 행)으로 돌아가 다른 행을 본다")
        self.assertEqual(row["해당 행 근거"], "모듈 코드 LM2001021702_25v1 의 능력단위 번호 2")


if __name__ == "__main__":
    unittest.main()
