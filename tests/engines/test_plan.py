"""개발계획서 점검(ncs_plan): 표 읽기와 ①~⑨ 규칙을 합성 표로 검사한다. 실제 계획서 샘플이 있으면 끝에서 한 번 돌려 본다."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ncs_core.lexicon import ActionNounLexicon
from ncs_plan.parsers import read_change_table, read_module, read_plan, read_summary_table
from ncs_plan.rules.front import check_change_table, check_identity, check_ncs_text, check_required, expected_analysis
from ncs_plan.rules.module import check_element_codes, check_goal, check_lessons, check_subs, check_targets

CODE = "1203020201_24v3"


class RealCatalog(unittest.TestCase):
    """개발계획서 ①은 NCS 목록과 대조한다. 골든 테스트(tests/golden_cases.py)가 같은 프로세스에서 먼저 불리면
    NCS_CATALOG_FILE을 없는 파일로 두어 목록을 끄므로, 이 묶음을 도는 동안만 그 설정을 걷어 패키지 기본 목록을 쓴다."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("NCS_CATALOG_FILE", None)
C1 = ["1.1 호텔의 객실 유형에 따라 객실 및 부대시설 정보를 구분 할 수 있다.", "1.2 객실 요금 종류에 따라 마켓별 요금을 구분하여 적용할 수 있다."]
C2 = ["2.1 호텔 객실 운영 시스템(PMS)을 기반으로 예약 가능한 객실 현황을 파악할 수 있다."]


def module_table(lessons, *, code=CODE, name="객실 예약 관리", lm_name="객실 예약 관리",
                 definition="객실 예약 접수란 객실 · 부대시설 이용정보 파악, 예약 현황 확인을 처리하는 능력이다.",
                 goal="객실 · 부대시설 이용정보 파악, 예약 현황 확인을 처리할 수 있다.",
                 elements=((f"{CODE}.1", "객실 · 부대시설 이용정보 파악하기", C1), (f"{CODE}.2", "예약 현황 확인하기", C2))):
    """실제 양식과 같은 8열 표. lessons: [(요소 index 목록, '1. 학습명', [('1-1. 내용명', [목표…]), …])]."""
    cells = {(0, 0): "NCS (수정 금지)", (0, 5): "NCS학습모듈", (1, 0): "능력단위 코드번호", (1, 1): code, (1, 2): "능력단위명", (1, 3): name,
             (1, 5): "학습모듈명", (1, 6): lm_name, (2, 0): "능력단위 정의", (2, 1): definition, (2, 5): "학습모듈의 목표", (2, 6): goal,
             (3, 0): "코드번호 능력단위요소명", (3, 1): "수 행 준 거", (3, 5): "학습명", (3, 6): "학습내용명", (3, 7): "학 습 목 표"}
    r = 4
    for element_idx, lesson, subs in lessons:
        first = r
        for i in element_idx:
            ecode, ename, criteria = elements[i]
            cells[(r, 0)], cells[(r, 1)] = f"{ecode} {ename}", " ".join(criteria)
            r += 1
        r = first
        cells[(r, 5)] = lesson
        for sub, goals in subs:
            cells[(r, 6)], cells[(r, 7)] = sub, " ".join(goals)
            r += 1
        r = max(r, first + len(element_idx))
    used = {i for element_idx, _, _ in lessons for i in element_idx}
    for i, (ecode, ename, criteria) in enumerate(elements):   # 어느 학습에도 안 쓰인 요소는 학습 없이 행만 남긴다
        if i not in used:
            cells[(r, 0)], cells[(r, 1)] = f"{ecode} {ename}", " ".join(criteria)
            r += 1
    return {"paragraph": 1, "rows": r, "cols": 8, "cells": cells}


OK_LESSONS = [([0], "1. 객실·부대시설 이용정보 파악하기", [("1-1. 호텔정보 구분", [C1[0]]), ("1-2. 요금 적용", [C1[1]])]),
              ([1], "2. 예약 현황 확인하기", [("2-1. 예약 현황 조회", C2)])]


def summary_table(rows):
    cells = {(0, 0): "① NCS", (0, 2): "② NCS학습모듈 개선 유형", (0, 3): "③ NCS학습모듈", (0, 5): "④ 담당 집필진", (0, 6): "⑤ 담당 검토진",
             (1, 0): "능력단위번호", (1, 1): "능력단위명", (1, 3): "NCS학습모듈 코드 번호", (1, 4): "NCS학습모듈명(안)"}
    for i, values in enumerate(rows, 2):
        for c, v in enumerate(values):
            cells[(i, c)] = v
    return {"paragraph": 2, "rows": 2 + len(rows), "cols": 7, "cells": cells}


def change_table(rows):
    cells = {(0, 0): "① NCS 개선 전", (0, 2): "② NCS 개선 후", (0, 4): "③ 개선된 NCS 분석 결과",
             (1, 0): "능력단위번호", (1, 1): "능력단위명", (1, 2): "능력단위번호", (1, 3): "능력단위명"}
    for i, values in enumerate(rows, 2):
        for c, v in enumerate(values):
            cells[(i, c)] = v
    return {"paragraph": 3, "rows": 2 + len(rows), "cols": 5, "cells": cells}


SUMMARY_OK = [(CODE, "객실 예약 관리", "기존 개선", f"LM{CODE}", "객실 예약 관리", "노선희", "김근혜")]
# 조회 결과를 데이터 파일에 쓰지 않도록 임시 폴더를 준다(목록 파일이 비어 있으니 모든 판정은 resolver가 한다)
LEXICON = ActionNounLexicon(directory=tempfile.mkdtemp(prefix="ncs_plan_lexicon_"), resolver=lambda word: (word in {"구분", "적용", "조회", "파악"}, "테스트"))


def checks_of(rows, prefix):
    return {k: v for row in rows for k, v in row["체크"].items() if k.startswith(prefix)}


class ParserTests(unittest.TestCase):
    def test_module_table_reads_elements_lessons_and_goals(self):
        m = read_module(module_table(OK_LESSONS))
        self.assertEqual((m["코드"], m["명칭"], m["학습모듈명"]), (CODE, "객실 예약 관리", "객실 예약 관리"))
        self.assertEqual([e["코드"] for e in m["요소"]], [f"{CODE}.1", f"{CODE}.2"])
        self.assertEqual(m["요소"][0]["수행준거"], C1)
        self.assertEqual([(l["번호"], l["명칭"], l["요소"]) for l in m["학습"]],
                         [(1, "객실·부대시설 이용정보 파악하기", [f"{CODE}.1"]), (2, "예약 현황 확인하기", [f"{CODE}.2"])])
        self.assertEqual([(s["소번호"], s["명칭"], s["목표"]) for s in m["학습"][0]["내용"]], [(1, "호텔정보 구분", [C1[0]]), (2, "요금 적용", [C1[1]])])

    def test_merged_lesson_takes_both_elements(self):
        m = read_module(module_table([([0, 1], "1. 이용정보 파악 및 예약 현황 확인하기", [("1-1. 정보 구분", C1 + C2)])]))
        self.assertEqual(m["학습"][0]["요소"], [f"{CODE}.1", f"{CODE}.2"])

    def test_front_tables(self):
        self.assertEqual(read_summary_table([summary_table(SUMMARY_OK)])[0]["LM 코드"], f"LM{CODE}")
        self.assertEqual(read_change_table([change_table([("1203020201_19v2", "객실 예약 관리", CODE, "객실 예약 관리", "능력단위 코드 변경")])])[0]["분석 결과"],
                         "능력단위 코드 변경")
        self.assertIsNone(read_change_table([summary_table(SUMMARY_OK)]))


class ModuleRuleTests(unittest.TestCase):
    def test_ok_plan_passes(self):
        m = read_module(module_table(OK_LESSONS))
        for fn in (check_goal, check_lessons, check_element_codes, check_targets):
            self.assertTrue(all(r["판정"] == "적합" for r in fn(m)), (fn.__name__, [r["비고"] for r in fn(m)]))
        self.assertTrue(all(r["판정"] == "적합" for r in check_subs(m, LEXICON)))

    def test_goal_ending_and_subject(self):
        m = read_module(module_table(OK_LESSONS, goal="객실 예약 접수란 객실 · 부대시설 이용정보 파악, 예약 현황 확인을 처리한다."))
        checks = checks_of(check_goal(m), "③")
        self.assertEqual((checks["③ '~할 수 있다.' 종결"], checks["③ 주어 삭제"]), ("X", "X"))

    def test_lesson_without_haki(self):
        m = read_module(module_table([([0], "1. 객실·부대시설 이용정보 파악", [("1-1. 호텔정보 구분", C1)]), ([1], "2. 예약 현황 확인하기", [("2-1. 조회", C2)])]))
        first, second = check_lessons(m)
        self.assertEqual((first["체크"]["④ '~하기' 종결"], second["체크"]["④ '~하기' 종결"]), ("X", "O"))

    def test_lesson_count_short_of_elements_is_a_merge_not_an_omission(self):
        # 요소 2개, 학습 1개(두 번째 요소 행에 학습명 없음) → 통합으로 읽고 △(아우르는지 확인). 누락 X가 아니다
        m = read_module(module_table([([0], "1. 이용정보 파악 및 예약 현황 확인하기", [("1-1. 정보 구분", C1)])]))
        [first] = check_lessons(m)
        self.assertEqual(first["체크"]["④ 요소명 준용"], "△")
        self.assertEqual(first["체크"]["④ 요소 배정"], "O")

    def test_elements_without_any_lesson_are_unassigned(self):
        table = module_table([])
        rows = check_lessons(read_module(table))
        self.assertTrue(any("배정되지 않은" in n for r in rows for n in r["비고"].values()))

    def test_lesson_name_differs_from_element_is_undecided_not_fail(self):
        m = read_module(module_table([([0], "1. 객실 정보 파악하기", [("1-1. 호텔정보 구분", C1)]), ([1], "2. 예약 현황 확인하기", [("2-1. 조회", C2)])]))
        [first, *_] = check_lessons(m)
        self.assertEqual(first["체크"]["④ 요소명 준용"], "△")
        self.assertIn("능력단위요소명", first["비고"]["④ 요소명 준용"])

    def test_lesson_name_spacing_must_follow_the_element_name(self):
        """학습명은 능력단위요소명의 띄어쓰기를 따른다(F04 준용 집필 기준 2-4) — 띄어쓰기만 달라도 부적합(학습 목표 ⑥과 같은 기준, 2026-11-23 결정)."""
        elements = ((f"{CODE}.1", "비즈니스전략분석하기", C1), (f"{CODE}.2", "예약 현황 확인하기", C2))
        m = read_module(module_table([([0], "1. 비즈니스 전략 분석하기", [("1-1. 구분", C1)]), ([1], "2. 예약 현황 확인하기", [("2-1. 조회", C2)])], elements=elements))
        first, second = check_lessons(m)
        self.assertEqual((first["체크"]["④ 요소명 준용"], first["판정"]), ("X", "부적합"))
        self.assertIn("띄어쓰기만 다름", first["비고"]["④ 요소명 준용"])
        self.assertIn("능력단위요소명 「비즈니스전략분석하기」", first["비고"]["④ 요소명 준용"])
        self.assertIsNotNone(first["수정 제안"])
        self.assertEqual((second["체크"]["④ 요소명 준용"], second["판정"]), ("O", "적합"))
        # 반대 방향(요소명에 있는 띄어쓰기를 붙여 씀)도 같다
        m = read_module(module_table([([0], "1. 객실 · 부대시설 이용정보 파악하기", [("1-1. 구분", C1)]), ([1], "2. 예약현황 확인하기", [("2-1. 조회", C2)])]))
        first, second = check_lessons(m)
        self.assertEqual((first["체크"]["④ 요소명 준용"], second["체크"]["④ 요소명 준용"]), ("O", "X"))

    def test_lesson_name_with_another_shape_of_middle_dot_is_the_same_name(self):
        """가운뎃점의 꼴(･ ・ ·)만 다른 것은 글꼴·입력 차이라 같은 이름으로 본다."""
        m = read_module(module_table([([0], "1. 객실 ･ 부대시설 이용정보 파악하기", [("1-1. 구분", C1)]), ([1], "2. 예약 현황 확인하기", [("2-1. 조회", C2)])]))
        [first, *_] = check_lessons(m)
        self.assertEqual(first["체크"]["④ 요소명 준용"], "O")

    def test_far_lesson_name_is_still_undecided(self):
        """요소명과 많이 다른 학습명도 X가 아니라 △ — 윤문인지 다른 이름인지는 내용 판단(안내서: 후보 제시)."""
        m = read_module(module_table([([0], "1. 고객 응대하기", [("1-1. 호텔정보 구분", C1)]), ([1], "2. 예약 현황 확인하기", [("2-1. 조회", C2)])]))
        [first, *_] = check_lessons(m)
        self.assertEqual((first["체크"]["④ 요소명 준용"], first["판정"]), ("△", "판단불가"))

    def test_ncs_element_name_without_haki_is_undecided(self):
        """NCS 요소명 자체가 '~하기'가 아니면(예: 메뉴 주문받기) 그대로 쓴 학습명은 X가 아니라 △ — 집필자가 고칠 수 없다."""
        elements = ((f"{CODE}.1", "메뉴 주문받기", C1), (f"{CODE}.2", "예약 현황 확인하기", C2))
        m = read_module(module_table([([0], "1. 메뉴 주문받기", [("1-1. 구분", C1)]), ([1], "2. 예약 현황 확인하기", [("2-1. 조회", C2)])], elements=elements))
        first, second = check_lessons(m)
        self.assertEqual((first["체크"]["④ '~하기' 종결"], first["체크"]["④ 요소명 준용"], first["판정"]), ("△", "O", "판단불가"))
        self.assertIn("NCS 원문", first["비고"]["④ '~하기' 종결"])
        self.assertEqual(second["판정"], "적합")

    def test_element_code_sequence(self):
        elements = ((f"{CODE}.1", "a하기", C1), ("1203020299_24v3.2", "b하기", C2))
        m = read_module(module_table([([0], "1. a하기", [("1-1. 구분", C1)]), ([1], "2. b하기", [("2-1. 조회", C2)])], elements=elements))
        [row] = check_element_codes(m)
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("1203020299_24v3.2", row["비고"]["⑤ 요소 코드 연번"])

    def test_targets_missing_extra_space_and_changed(self):
        spaced = C1[0].replace("구분 할 수", "구분할 수")                    # 띄어쓰기만 → X(원고 검수와 같은 기준)
        changed = C2[0].replace("파악할", "확인할")                        # 글자 다름 → △
        m = read_module(module_table([([0], "1. a하기", [("1-1. 구분", [spaced, "1.3 수행준거에 없는 문장을 쓸 수 있다."])]),
                                      ([1], "2. b하기", [("2-1. 조회", [changed])])]))
        first, second = check_targets(m)
        self.assertEqual(first["체크"], {"⑥ 수행준거 누락 없음": "X", "⑥ 수행준거 외 문장 없음": "X", "⑥ 문장 수정 없음": "X"})
        self.assertIn("마켓별 요금", first["비고"]["⑥ 수행준거 누락 없음"])
        self.assertIn("띄어쓰기도 수행준거와 같아야 함", first["비고"]["⑥ 문장 수정 없음"])
        self.assertEqual(second["체크"]["⑥ 문장 수정 없음"], "△")
        self.assertIn("수행준거 「", second["비고"]["⑥ 문장 수정 없음"])

    def test_subs_numbering_and_action_noun(self):
        m = read_module(module_table([([0], "1. a하기", [("1.1 호텔 시장 동향에 대한 이해", [C1[0]]), ("1-2 요금 적용", [C1[1]])]),
                                      ([1], "2. b하기", [("2-1. 예약 현황에 대하여", C2)])]))
        first, second = check_subs(m, LEXICON)
        self.assertEqual(first["체크"]["⑦ N-M 연번·기재"], "X")
        self.assertIn("'N-M.' 꼴이 아님", first["비고"]["⑦ N-M 연번·기재"])
        self.assertEqual(second["체크"]["⑦ 행동명사 종결"], "X")
        # 번호가 깨진 행의 목표 문장도 ⑥에서 살아 있어야 한다(누락으로 이중 지적하지 않음)
        self.assertEqual(check_targets(m)[0]["체크"]["⑥ 수행준거 누락 없음"], "O")


class FrontRuleTests(unittest.TestCase):
    def plan(self, summary=SUMMARY_OK, change=None, modules=(module_table(OK_LESSONS),)):
        tables = [summary_table(summary)] + ([change_table(change)] if change is not None else []) + list(modules)
        return read_plan(tables)

    def test_identity_lm_code_and_name(self):
        rows = check_identity(self.plan([(CODE, "객실 예약 관리", "기존 개선", "LM1203020201_23v3", "객실예약관리 업무", "a", "b")]))
        self.assertEqual(rows[0]["체크"]["② LM 코드"], "X")
        self.assertEqual(rows[0]["체크"]["② 학습모듈명 = 능력단위명"], "X")
        self.assertEqual(rows[0]["체크"]["② 표 간 일치"], "X")   # 모듈 표의 학습모듈명과 다름

    def test_identity_ok(self):
        self.assertTrue(all(r["판정"] == "적합" for r in check_identity(self.plan())))

    def test_required_fields_and_placeholders(self):
        plan = self.plan([(CODE, "객실 예약 관리", "개선", f"LM{CODE}", "객실 예약 관리", "", "b")])
        [row] = check_required(plan, ["oo 계획(0000000000_20v2)"])
        self.assertEqual(row["체크"]["⑧ 개선 유형"], "X")
        self.assertEqual(row["체크"]["⑧ 담당 집필진·검토진"], "X")
        self.assertEqual(row["체크"]["⑧ 안내 문구·자리표시"], "X")
        self.assertEqual(row["체크"]["⑧ 기본 정보"], "X")   # 기본 정보 표가 없어 모두 비어 있음

    def test_minimal_improvement_needs_no_reviewer_but_one_lead_writer(self):
        """최소개선은 대표집필자 1인이 일괄 담당하고 별도 검토진을 두지 않는 것이 원칙(F05 최소개선 유형 세부 지침 2항)."""
        other = "1203020202_24v2"
        rows = [(CODE, "객실 예약 관리", "최소개선", f"LM{CODE}", "객실 예약 관리", "노선희", ""),
                (other, "체크 인", "최소 개선", f"LM{other}", "체크 인", "노선희", "")]
        [row] = check_required(self.plan(rows), [])
        self.assertEqual((row["체크"]["⑧ 개선 유형"], row["체크"]["⑧ 담당 집필진·검토진"], row["체크"]["⑧ 최소개선 담당"]), ("O", "O", "O"))
        [row] = check_required(self.plan([rows[0], (other, "체크 인", "최소개선", f"LM{other}", "체크 인", "김근혜", "")]), [])
        self.assertEqual(row["체크"]["⑧ 최소개선 담당"], "△")          # 담당이 둘 — 대표집필자 1인이 맡는지 확인
        self.assertIn("대표집필자", row["비고"]["⑧ 최소개선 담당"])
        [row] = check_required(self.plan([(CODE, "객실 예약 관리", "최소개선", f"LM{CODE}", "객실 예약 관리", "", "")]), [])
        self.assertEqual(row["체크"]["⑧ 담당 집필진·검토진"], "X")      # 최소개선도 집필진(대표집필자)은 적는다
        [row] = check_required(self.plan([(CODE, "객실 예약 관리", "기존 개선", f"LM{CODE}", "객실 예약 관리", "노선희", "")]), [])
        self.assertEqual(row["체크"]["⑧ 담당 집필진·검토진"], "X")      # 기존 개선은 검토진이 있어야 한다(그대로)
        self.assertNotIn("⑧ 최소개선 담당", row["체크"])

    def test_improvement_type_against_the_change_table(self):
        """최소개선은 능력단위 코드와 기본 구조에 변경이 없을 때(F05 1항) — 대조표에 코드 변경·신설로 적힌 능력단위면 유형 확인 후보.
        양식 편집은 코드 변경이 '없거나 경미'하면 되므로(F21 양식편집 운영 기준) 코드 변경만으로는 후보가 아니다. 신설–신규 개발 짝은 지침에 없어 보지 않는다."""
        other, new = "1203020202_24v2", "1203020203_24v1"
        moved = "1203020204_24v2"
        summary = [(CODE, "객실 예약 관리", "최소개선", f"LM{CODE}", "객실 예약 관리", "노선희", ""),
                   (other, "체크 인", "양식 편집", f"LM{other}", "체크 인", "노선희", "김근혜"),
                   (new, "체크 아웃", "기존 개선", f"LM{new}", "체크 아웃", "노선희", "김근혜"),
                   (moved, "객실 정비", "최소개선", f"LM{moved}", "객실 정비", "노선희", "")]
        change = [(CODE, "객실 예약 관리", CODE, "객실 예약 관리", "변경 없음"),
                  ("1203020202_13v1", "체크 인", other, "체크 인", "능력단위 코드 변경"),
                  ("", "", new, "체크 아웃", "능력단위 신설"),
                  ("1203020204_20v1", "객실 정비", moved, "객실 정비", "능력단위 코드 변경")]
        [row] = check_required(self.plan(summary, change=change), [])
        self.assertEqual(row["체크"]["⑧ 개선 유형과 대조표"], "△")
        note = row["비고"]["⑧ 개선 유형과 대조표"]
        self.assertIn(moved, note)                     # 최소개선인데 코드 변경
        self.assertIn("F05", note)
        self.assertNotIn(other, note)                  # 양식 편집 + 코드 변경: 경미하면 되므로 후보가 아니다(F21)
        self.assertNotIn(new, note)                    # 신설인데 기존 개선: 지침에 없는 짝 — 보지 않는다
        self.assertNotIn(f"{CODE} ", note)             # 변경 없음 + 최소개선은 맞는 짝
        ok = [(CODE, "객실 예약 관리", "최소개선", f"LM{CODE}", "객실 예약 관리", "노선희", ""), (new, "체크 아웃", "신규 개발", f"LM{new}", "체크 아웃", "노선희", "김근혜")]
        [row] = check_required(self.plan(ok, change=change[:3]), [])
        self.assertEqual(row["체크"]["⑧ 개선 유형과 대조표"], "O")
        [row] = check_required(self.plan(ok), [])      # 대조표가 없으면 이 체크는 내지 않는다
        self.assertNotIn("⑧ 개선 유형과 대조표", row["체크"])

    def test_change_table_analysis(self):
        self.assertEqual(expected_analysis("1203020201_19v2", CODE), "능력단위 코드 변경")
        self.assertEqual(expected_analysis("", CODE), "능력단위 신설")
        self.assertEqual(expected_analysis(CODE, CODE), "변경 없음")
        rows = check_change_table(self.plan(change=[("1203020201_19v2", "객실 예약 관리", CODE, "객실 예약 관리", "변경 없음"),
                                                    ("1203020202_13v1", "체크 인", "1203020202_24v2", "체크 인", "능력단위 코드 변경")]))
        self.assertEqual(rows[0]["체크"]["⑨ 분석 결과"], "X")
        self.assertEqual(rows[1]["체크"]["⑨ 개선 후 = 총괄표"], "X")   # 총괄표에 없는 능력단위


SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "개발계획서_12030202_26.7.6.hwp"


@unittest.skipUnless(SAMPLE.is_file(), "실제 개발계획서 샘플이 없음(samples/는 git 제외)")
class RealSampleTests(RealCatalog):
    def test_real_plan_runs_and_finds_known_numbering_errors(self):
        from ncs_plan import run_review

        result = run_review([SAMPLE])
        self.assertEqual(result.diagnostics["counts"]["modules"], 7)
        by_no = {row["번호"]: row["검수결과"] for row in result.sheet}
        self.assertEqual((by_no["②"], by_no["⑤"], by_no["⑨"]), ("적합", "적합", "적합"))
        # ①: 목록 대조는 적합. 기준정보 대조에서 요소명 하나가 띄어쓰기만 다르다('처리하기( Lost & Found)') → 판단불가, X는 없다
        first = [r for r in result.checklist if r["item_id"] == "PLAN-①"]
        self.assertEqual(by_no["①"], "판단불가")
        self.assertEqual([k for r in first for k, v in r["체크"].items() if v != "O"], ["① NCS 표기 띄어쓰기"])
        self.assertEqual(by_no["⑦"], "부적합")   # 객실 매출 관리 학습 1의 '1.1 …' 번호 표기
        self.assertTrue(any("1.1 호텔 시장 동향" in n for r in result.checklist if r["item_id"] == "PLAN-⑦" for n in r["비고"].values()))


if __name__ == "__main__":
    unittest.main()


class FillTests(RealCatalog):
    """자동 입력(fill): 합성 spec → 초안 hwpx → 다시 읽어 NCS 쪽이 그대로이고 점검 ①~⑥·⑧에서 X가 없어야 한다."""

    SPEC = {
        "기본": {"세분류명": "객실관리", "영문 세분류명": "Rooms Operation", "신규/개선": "신규", "개발기관명": "테스트기관"},
        "위치": {"대분류": "이용·숙박·여행·오락·스포츠", "중분류": "관광·레저", "소분류": "숙박서비스", "세분류": ["숙박기획·개발", "객실관리"]},
        "총괄표": [{"코드": CODE, "명칭": "객실 예약 관리", "집필진": "김집필", "검토진": "이검토"},
                 {"코드": "1203020202_24v2", "명칭": "체크 인(Check In)", "집필진": "김집필", "검토진": "이검토"}],
        "모듈": [{"코드": CODE, "명칭": "객실 예약 관리",
                 "정의": "객실 예약 접수란 객실 · 부대시설 이용정보 파악, 예약 현황 확인을 처리하는 능력이다.",
                 "요소": [{"코드": f"{CODE}.1", "명칭": "객실 · 부대시설 이용정보 파악하기", "수행준거": C1},
                          {"코드": f"{CODE}.2", "명칭": "예약 현황 확인하기", "수행준거": C2}]},
                {"코드": "1203020202_24v2", "명칭": "체크 인(Check In)", "정의": "체크 인이란 고객 응대를 제공하는 능력이다.",
                 "요소": [{"코드": "1203020202_24v2.1", "명칭": "체크 인 준비하기", "수행준거": ["1.1 투숙 현황에 따라 체크 인 업무를 준비할 수 있다."]}]}],
    }

    def test_draft_round_trip(self):
        import io
        import zipfile

        from ncs_core import load_document
        from ncs_plan.fill import build_plan, draft_goal
        from ncs_plan.parsers import read_plan

        self.assertEqual(draft_goal("객실 매출 관리란 수입을 증대하기 위한 관리 능력이다."), "수입을 증대하기 위한 관리를 할 수 있다.")
        data = build_plan(self.SPEC)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.infolist()[0].filename, "mimetype")
            self.assertEqual(archive.infolist()[0].compress_type, zipfile.ZIP_STORED)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "개발계획서_초안.hwpx"
            path.write_bytes(data)
            plan = read_plan(load_document(path).tables)
            self.assertEqual(plan["기본"]["세분류명"], "객실관리")
            self.assertEqual([e["코드"] for e in plan["총괄표"]], [CODE, "1203020202_24v2"])
            self.assertEqual(plan["총괄표"][0]["LM 코드"], f"LM{CODE}")
            self.assertEqual(plan["위치"]["모듈"][0], {"능력단위": "객실 예약 관리", "학습모듈명": ""})      # 위치 표의 학습모듈명은 추후 기관에서 기재(F21 3쪽)
            self.assertEqual(len(plan["모듈"]), 2)
            first = plan["모듈"][0]
            self.assertEqual([e["수행준거"] for e in first["요소"]], [C1, C2])
            self.assertEqual([(l["번호"], l["명칭"], l["요소"]) for l in first["학습"]],
                             [(1, "객실 · 부대시설 이용정보 파악하기", [f"{CODE}.1"]), (2, "예약 현황 확인하기", [f"{CODE}.2"])])
            self.assertEqual(first["학습"][0]["내용"][0]["목표"], C1)
            self.assertEqual(first["목표"], "객실 · 부대시설 이용정보 파악, 예약 현황 확인을 처리할 수 있다.")
            from ncs_plan import run_review

            result = run_review([path])
            by_no = {row["번호"]: row["검수결과"] for row in result.sheet}
            for no in "③④⑤⑥⑧":
                self.assertEqual(by_no[no], "적합", (no, [r["비고"] for r in result.checklist if r["item_id"] == f"PLAN-{no}" and r["판정"] != "적합"]))
            # ② 최종본 기준: 위치 표의 학습모듈명은 기관이 적는 칸이라 초안에서는 비어 있다(F21 3쪽) → 부적합. 다른 사유는 없어야 한다
            self.assertEqual(by_no["②"], "부적합")
            second = [note for r in result.checklist if r["item_id"] == "PLAN-②" for note in r["비고"].values()]
            self.assertTrue(second and all("학습모듈명이 비어 있음" in note for note in second), second)
            self.assertEqual(by_no["⑦"], "부적합")   # 최종본 기준: '(집필자 작성)' 자리표시가 남아 있으면 부적합
            # 1차(draft) 기준: 기관 기재 칸(학습모듈명·영문명·집필진·학습 내용명)은 해당 없음 → 전부 적합
            from ncs_plan import CheckConfig

            draft = run_review([path], config=CheckConfig(stage="draft"))
            # ①은 뺀다: 이 합성 spec의 정의·수행준거는 실제 NCS 기준정보와 글자가 달라 기준정보 대조에서 걸린다(그게 맞다)
            self.assertTrue(all(row["검수결과"] == "적합" for row in draft.sheet if row["번호"] != "①"), [(r["번호"], r["검수결과"]) for r in draft.sheet])
            self.assertTrue(any("① 수행준거" in r["비고"] or "① 능력단위 정의" in r["비고"] for r in draft.checklist if r["item_id"] == "PLAN-①"))

    def test_improve_form_round_trip(self):
        """개선 계획서: 개선 양식(대조표 + 총괄표의 개선 유형 열)에 채우고 다시 읽는다. 신규는 지금까지의 양식 그대로."""
        import copy

        from ncs_core import load_document
        from ncs_plan.fill import build_plan, change_from_modules
        from ncs_plan.parsers import read_plan

        spec = copy.deepcopy(self.SPEC)
        spec["기본"]["신규/개선"] = "개선"
        spec["총괄표"][0]["개선 유형"] = "최소개선"          # 둘째는 비워 둔다 → 빈 칸 그대로(유형은 직능연이 분류한다 — 프로그램이 정하지 않는다)
        rows = change_from_modules(spec["모듈"], {CODE: {"코드": "1203020201_20v2", "명칭": "객실 예약 접수"}, "1203020202_24v2": {"코드": "없음"}})
        self.assertEqual([row["분석 결과"] for row in rows], ["능력단위 코드 변경", "능력단위 신설"])
        self.assertEqual(change_from_modules(spec["모듈"])[0]["분석 결과"], "")     # 개선 전을 모르면 비워 둔다(지어내지 않는다)
        spec["대조표"] = rows
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "개발계획서_개선_초안.hwpx"
            path.write_bytes(build_plan(spec))
            plan = read_plan(load_document(path).tables)
            self.assertEqual([entry["개선 유형"] for entry in plan["총괄표"]], ["최소개선", ""])
            self.assertEqual([m["학습모듈명"] for m in plan["위치"]["모듈"]], ["", ""])      # 위치 표의 학습모듈명은 추후 기관에서 기재(F21 3쪽)
            self.assertEqual([entry["LM 명칭"] for entry in plan["총괄표"]], ["객실 예약 관리", "체크 인(Check In)"])   # 총괄표 학습모듈명(안)은 능력단위명과 같게(F21 2쪽)
            self.assertEqual([entry["집필진"] for entry in plan["총괄표"]], ["김집필", "김집필"])
            self.assertEqual([(row["개선 전 코드"], row["개선 후 코드"], row["분석 결과"]) for row in plan["대조표"]],
                             [("1203020201_20v2", CODE, "능력단위 코드 변경"), ("", "1203020202_24v2", "능력단위 신설")])     # 신설은 개선 전 칸을 비운다
            self.assertEqual(len(plan["모듈"]), 2)
            self.assertEqual([e["수행준거"] for e in plan["모듈"][0]["요소"]], [C1, C2])
            new_path = Path(folder) / "개발계획서_신규_초안.hwpx"
            new_path.write_bytes(build_plan(self.SPEC))
            self.assertIsNone(read_plan(load_document(new_path).tables)["대조표"])     # 신규 양식에는 대조표가 없다


class NcsTextTests(unittest.TestCase):
    """① NCS 기준정보 대조: 모듈 표의 NCS 쪽(정의·요소·수행준거)이 받아 둔 기준정보와 같은가. 글자가 다르면 X, 띄어쓰기만 다르면 △, 기준정보가 없으면 △."""

    class Catalog:
        def __init__(self, units):
            self.units = units

        def unit_detail(self, code):
            return self.units.get(code)

    DETAIL = {"code": CODE, "name": "객실 예약 관리", "definition": "객실 예약 관리란 예약을 처리하는 능력이다.",
              "elements": [{"code": f"{CODE}.1", "name": "객실 · 부대시설 이용정보 파악하기", "criteria": list(C1)},
                           {"code": f"{CODE}.2", "name": "예약 현황 확인하기", "criteria": list(C2)}]}

    def module(self, **changes):
        module = {"코드": CODE, "명칭": "객실 예약 관리", "정의": "객실 예약 관리란 예약을 처리하는 능력이다.",
                  "요소": [{"코드": f"{CODE}.1", "명칭": "객실･부대시설 이용정보 파악하기", "수행준거": list(C1)},
                           {"코드": f"{CODE}.2", "명칭": "예약 현황 확인하기", "수행준거": list(C2)}]}
        module.update(changes)
        return module

    def run_rule(self, module, detail=None):
        rows = check_ncs_text({"모듈": [module]}, self.Catalog({CODE: detail or self.DETAIL}))
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_same_as_reference_is_ok(self):
        row = self.run_rule(self.module())      # 가운뎃점 꼴과 앞뒤 공백은 같은 것으로 본다
        self.assertEqual(row["판정"], "적합", row["비고"])
        self.assertEqual(row["item_id"], "PLAN-①")

    def test_changed_text_is_x(self):
        elements = self.module()["요소"]
        elements[1]["명칭"] = "예약 현황 파악하기"
        elements[0]["수행준거"][1] = "1.2 객실 요금 종류에 따라 요금을 적용할 수 있다."
        row = self.run_rule(self.module(요소=elements, 정의="객실 예약 관리란 예약을 접수하는 능력이다."))
        self.assertEqual(row["판정"], "부적합")
        self.assertEqual({k for k, v in row["체크"].items() if v == "X"}, {"① 능력단위 정의", "① 능력단위요소명", "① 수행준거"})
        self.assertIn("예약 현황 확인하기", row["비고"]["① 능력단위요소명"])
        self.assertIn("마켓별", row["비고"]["① 수행준거"])

    def test_missing_and_extra_elements_and_criteria(self):
        elements = self.module()["요소"][:1]
        elements[0]["수행준거"] = C1[:1]
        row = self.run_rule(self.module(요소=elements))
        self.assertEqual(row["체크"]["① 능력단위요소 구성"], "X")
        self.assertIn(f"{CODE}.2", row["비고"]["① 능력단위요소 구성"])
        self.assertEqual(row["체크"]["① 수행준거"], "X")
        self.assertIn("빠짐", row["비고"]["① 수행준거"])

    def test_spacing_only_is_candidate(self):
        elements = self.module()["요소"]
        elements[1]["명칭"] = "예약현황 확인하기"
        elements[0]["수행준거"][0] = C1[0].replace("구분 할 수", "구분할 수")
        row = self.run_rule(self.module(요소=elements))
        self.assertEqual(row["판정"], "판단불가")
        self.assertEqual([k for k, v in row["체크"].items() if v != "O"], ["① NCS 표기 띄어쓰기"])
        self.assertIn("2곳", row["비고"]["① NCS 표기 띄어쓰기"])

    def test_no_reference_is_one_unknown_row(self):
        rows = check_ncs_text({"모듈": [self.module(), self.module(코드="1203020202_24v2")]}, self.Catalog({}))
        self.assertEqual([(r["판정"], r["위치"]) for r in rows], [("판단불가", "")])
        self.assertIn("2개", rows[0]["비고"]["① NCS 기준정보"])
        self.assertEqual(check_ncs_text({"모듈": [self.module()]}, None), [])       # 목록이 꺼져 있으면 ① 앞 행이 이미 알린다
        self.assertEqual(check_ncs_text({"모듈": []}, self.Catalog({})), [])


class TypeSignalTests(unittest.TestCase):
    """개선 유형 판단 자료(ncs_plan.type_signals): 기존 학습모듈 원고에서 지침이 든 '내용 수정이 필요한 경우'의 신호를 찾는다. 유형을 정하지는 않는다."""

    DETAIL = NcsTextTests.DETAIL

    def signals(self, paragraphs, detail="same"):
        from ncs_plan.type_signals import type_signals

        result = type_signals([paragraphs], self.DETAIL if detail == "same" else detail)
        return result, {item["신호"]: item for item in result["신호"]}

    def test_laws_urls_and_empty_safety_notes(self):
        text = ["학습 1. 객실 · 부대시설 이용정보 파악하기", *C1, *C2, "「관광진흥법」에 따라 등록한다.", "궁중 조리법과 현장 대처법을 익힌다.", "관광진흥법 시행령을 본다.", "자세한 내용은 https://www.example.go.kr/a?b=1 참고.",
                "안전·유의 사항", "해당사항 없음"]
        result, found = self.signals(text)
        self.assertEqual(set(found), {"법령 기재", "URL 기재", "안전·유의 사항 ‘해당 사항 없음’"})
        self.assertEqual(found["법령 기재"]["예"], ["관광진흥법", "관광진흥법 시행령"])       # '조리법'·'대처법'은 법령이 아니다
        self.assertEqual(found["URL 기재"]["예"], ["https://www.example.go.kr/a?b=1"])
        self.assertTrue(all("최소개선" in item["유형"] and item["근거"] for item in found.values()))
        self.assertNotIn("판정", result)                     # 유형을 정하지 않는다
        self.assertIn("직능연", result["안내"])

    def test_goals_that_differ_from_criteria(self):
        changed = [C1[0], "1.2 객실 요금 종류에 따라 요금을 적용할 수 있다.", *C2]
        _, found = self.signals(changed)
        self.assertEqual(set(found), {"학습 목표와 NCS 수행준거 불일치"})
        self.assertEqual(found["학습 목표와 NCS 수행준거 불일치"]["건수"], 1)
        self.assertIn("마켓별", found["학습 목표와 NCS 수행준거 불일치"]["예"][0])
        self.assertIn("기존 개선 또는 최소개선", found["학습 목표와 NCS 수행준거 불일치"]["유형"])
        # 띄어쓰기만 다른 것은 불일치로 세지 않는다
        _, found = self.signals([C1[0].replace("구분 할 수", "구분할 수"), C1[1], *C2])
        self.assertEqual(found, {})

    def test_no_signal_and_no_reference(self):
        result, found = self.signals([*C1, *C2])
        self.assertEqual(found, {})
        self.assertIn("양식 편집", result["안내"])            # 신호가 없으면 양식 편집 요건을 확인하라고만 한다
        result, found = self.signals([*C1], detail=None)
        self.assertEqual(found, {})
        self.assertIn("수행준거와 대조하지 못", result["확인 못 한 것"][0])


class ApplyTests(RealCatalog):
    """비교 결과 반영(ncs_plan.apply): 고른 칸을 대상 계획서(hwpx)의 사본에 기준 글로 바꿔 넣는다. 한쪽이 빈 칸과 못 찾은 칸은 반영하지 않고 알린다."""

    def test_apply_selected_differences(self):
        import copy

        from ncs_core import load_document
        from ncs_plan.apply import apply_differences
        from ncs_plan.compare import compare_plans
        from ncs_plan.fill import build_plan
        from ncs_plan.parsers import read_plan

        base_spec = copy.deepcopy(FillTests.SPEC)
        target_spec = copy.deepcopy(FillTests.SPEC)
        target_spec["모듈"][0]["요소"][1]["명칭"] = "예약 현황 파악하기"                      # 글자가 다름(NCS 쪽)
        target_spec["모듈"][0]["요소"][0]["수행준거"][1] = C1[1].replace("적용할 수", "적용 할 수")   # 띄어쓰기만 다름
        with tempfile.TemporaryDirectory() as folder:
            base, target = Path(folder) / "기준.hwpx", Path(folder) / "대상.hwpx"
            base.write_bytes(build_plan(base_spec))
            target.write_bytes(build_plan(target_spec))
            read = lambda path: read_plan(load_document(path).tables)
            before = compare_plans(read(base), read(target))
            self.assertTrue(before["차이"])
            chosen = [row for row in before["차이"] if row["차이"] == "다름"]            # 글자가 다른 칸만 고른다
            self.assertTrue(chosen)
            data, report = apply_differences(target.read_bytes(), chosen + [{"구역": "모듈 표", "자리": CODE, "칸": "학습모듈명", "차이": "다름", "기준": "없는 글", "대상": "어디에도 없는 글"},
                                                                       {"구역": "총괄표", "자리": CODE, "칸": "검토진", "차이": "기준에만 있음", "기준": "이검토", "대상": ""}])
            self.assertEqual(report["반영"], len(chosen))
            self.assertEqual([item["사유"] for item in report["반영 못 함"]], ["대상 계획서에서 그 글을 찾지 못함", "한쪽이 빈 칸 — 한글에서 직접 적을 것"])
            patched = Path(folder) / "대상_반영.hwpx"
            patched.write_bytes(data)
            after = compare_plans(read(base), read(patched))
            self.assertEqual([row["차이"] for row in after["차이"]], ["띄어쓰기만 다름"] * len(after["차이"]))    # 고르지 않은 띄어쓰기 차이는 그대로
            self.assertTrue(after["차이"])
            self.assertEqual(read(target)["모듈"][0]["요소"][1]["명칭"], "예약 현황 파악하기")          # 원본은 그대로


class CompareTests(unittest.TestCase):
    """계획서 둘 비교(ncs_plan.compare): 같은 칸은 세기만, 다른 칸은 띄어쓰기만/다름/한쪽에만. 개선 유형 변경과 NCS 쪽 변경을 따로 센다."""

    def plan(self, **changes):
        import copy

        base = {"기본": {"세분류명": "객실관리"}, "대조표": [],
                "총괄표": [{"코드": CODE, "명칭": "객실 예약 관리", "개선 유형": "기존 개선", "LM 코드": f"LM{CODE}", "LM 명칭": "객실 예약 관리", "집필진": "김집필", "검토진": "이검토"}],
                "위치": {"대분류": "가", "중분류": "나", "소분류": "다", "세분류": ["객실관리"], "모듈": [{"능력단위": "객실 예약 관리", "학습모듈명": "객실 예약 관리"}]},
                "모듈": [{"코드": CODE, "명칭": "객실 예약 관리", "정의": "정의이다.", "학습모듈명": "객실 예약 관리", "목표": "목표를 달성할 수 있다.",
                         "요소": [{"코드": f"{CODE}.1", "명칭": "예약 현황 확인하기", "수행준거": list(C1)}],
                         "학습": [{"번호": 1, "명칭": "예약 현황 확인하기", "내용": [{"명칭": "1-1. 객실 현황 파악", "목표": list(C1)}]}]}]}
        plan = copy.deepcopy(base)
        for path, value in changes.items():
            target = plan
            keys = path.split("/")
            for key in keys[:-1]:
                target = target[int(key)] if key.isdigit() else target[key]
            target[int(keys[-1]) if keys[-1].isdigit() else keys[-1]] = value
        return plan

    def test_same_plans_have_no_difference(self):
        from ncs_plan.compare import compare_plans

        result = compare_plans(self.plan(), self.plan())
        self.assertEqual(result["차이"], [])
        self.assertEqual(result["요약"]["같음"], result["요약"]["견준 칸"])
        self.assertGreater(result["요약"]["견준 칸"], 15)

    def test_kinds_of_difference(self):
        from ncs_plan.compare import compare_plans

        target = self.plan(**{"모듈/0/학습/0/명칭": "예약현황 확인하기", "모듈/0/목표": "다른 목표를 달성할 수 있다.",
                              "모듈/0/학습/0/내용/0/명칭": "", "총괄표/0/검토진": ""})
        result = compare_plans(self.plan(), target)
        found = {(row["칸"], row["차이"]) for row in result["차이"]}
        self.assertEqual(found, {("학습명", "띄어쓰기만 다름"), ("학습모듈의 목표", "다름"), ("학습 내용명", "기준에만 있음"), ("검토진", "기준에만 있음")})
        self.assertEqual(result["요약"]["수정 금지 칸 변경"], 0)
        self.assertEqual(compare_plans(target, self.plan())["요약"]["대상에만 있음"], 2)

    def test_type_change_and_locked_cells(self):
        from ncs_plan.compare import compare_plans

        target = self.plan(**{"총괄표/0/개선 유형": "최소개선", "모듈/0/요소/0/명칭": "예약 현황 파악하기",
                              "모듈/0/요소/0/수행준거/1": "1.2 객실 요금 종류에 따라 마켓별 요금을 구분하여 적용 할 수 있다."})
        result = compare_plans(self.plan(), target)
        self.assertEqual(result["개선 유형 변경"], [{"코드": CODE, "명칭": "객실 예약 관리", "기준": "기존 개선", "대상": "최소개선"}])
        locked = [(row["칸"], row["차이"]) for row in result["차이"] if row["수정 금지 칸"]]
        self.assertEqual(sorted(locked), [("능력단위요소명", "다름"), ("수행준거", "띄어쓰기만 다름")])
        self.assertEqual(result["요약"]["수정 금지 칸 변경"], 2)
        # 가운뎃점 꼴과 앞뒤 공백 차이는 같은 것으로 본다(판정 ④·⑥과 같은 기준)
        self.assertEqual(compare_plans(self.plan(**{"모듈/0/명칭": "객실･부대시설"}), self.plan(**{"모듈/0/명칭": "객실 · 부대시설"}))["차이"][0]["차이"], "띄어쓰기만 다름")

    def test_unit_on_one_side_only(self):
        from ncs_plan.compare import compare_plans

        result = compare_plans(self.plan(), self.plan(**{"모듈": [], "총괄표": []}))
        self.assertEqual({(row["구역"], row["차이"]) for row in result["차이"] if row["칸"] in ("모듈 표", "능력단위")}, {("모듈 표", "기준에만 있음"), ("총괄표", "기준에만 있음")})


class LawTests(unittest.TestCase):
    def test_extract_law_names(self):
        from ncs_core.law_catalog import extract_law_names

        self.assertEqual(extract_law_names("「개인정보 보호법」에 따라"), [("개인정보 보호법", True)])
        self.assertEqual(extract_law_names("근로기준법과 최저임금법은"), [("근로기준법", False), ("최저임금법", False)])
        self.assertEqual(extract_law_names("규정에 따라 산업안전보건법을 지킨다"), [("산업안전보건법", False)])
        self.assertEqual(extract_law_names("화학물질관리법 시행규칙에 따른다"), [("화학물질관리법 시행규칙", False)])
        self.assertEqual(extract_law_names("작업 방법과 분석 기법, 법인 설립의 법적 근거"), [])
        # 이름 앞에 문장이 두 어절 이상 붙어도 법령명만 남긴다
        self.assertEqual(extract_law_names("안전한 음식을 제공하기 위해 식품위생법을 준수할 수 있다."), [("식품위생법", False)])
        self.assertEqual(extract_law_names("고객 정보를 지키기 위하여 개인정보 보호법을 따른다"), [("개인정보 보호법", False)])
        # '…에 관한 법률'은 이름 안의 어절('등에')에서 자르지 않는다
        self.assertEqual(extract_law_names("부정청탁 및 금품등 수수의 금지에 관한 법률을 지킨다"), [("금품등 수수의 금지에 관한 법률", False)])

    def test_rule_with_table(self):
        from ncs_core.law_catalog import LawCatalog
        from ncs_plan.rules.laws import LABEL, check_laws

        with tempfile.TemporaryDirectory() as folder:
            table = Path(folder) / "law_names.tsv"
            table.write_text("# 표\n개인정보 보호법\t개인정보 보호법\t011357\t20250313\t일부개정\t현행\t개인정보 보호법\t2026-11-10\n"
                             "정보통신망법\t정보통신망 이용촉진 및 정보보호 등에 관한 법률\t000001\t20240101\t일부개정\t명칭변경\t정보통신망 이용촉진 및 정보보호 등에 관한 법률\t2026-11-10\n"
                             "고객정보보호법\t\t\t\t\t미검색\t\t2026-11-10\n", encoding="utf-8")
            catalog = LawCatalog(table)
            elements = ((f"{CODE}.1", "a하기", ["1.1 「개인정보 보호법」에 따라 등록할 수 있다.", "1.2 고객정보보호법에 따라 관리할 수 있다."]),)
            m = read_module(module_table([([0], "1. a하기", [("1-1. 등록", ["1.1 정보통신망법에 따라 등록할 수 있다."])])], elements=elements))
            rows = {r["원고"]: r for r in check_laws(m, catalog)}
            self.assertEqual(rows["개인정보 보호법"]["체크"][LABEL], "O")
            self.assertEqual(rows["정보통신망법"]["체크"][LABEL], "X")          # 학습모듈 쪽 → X, 현행 명칭 제안
            self.assertIn("정보통신망 이용촉진", rows["정보통신망법"]["수정 제안"])
            self.assertEqual(rows["고객정보보호법"]["체크"][LABEL], "△")      # NCS 쪽·미검색 → △
            [none] = check_laws(m, None)
            self.assertEqual(none["체크"][LABEL], "△")

    def test_spacing_differs_from_official_name(self):
        """현행 법령인데 띄어쓰기만 법제처 정식 명칭과 다르면 띄어쓰기 오류(F11 법령 표기 기준). NCS 쪽은 △, 약칭은 참고만."""
        from ncs_core.law_catalog import LawCatalog
        from ncs_plan.rules.laws import LABEL, check_laws, spacing_only

        self.assertTrue(spacing_only("개인 정보 보호법", "개인정보 보호법"))
        self.assertTrue(spacing_only("「개인정보보호법」", "개인정보 보호법"))
        self.assertFalse(spacing_only("개인정보 보호법", "개인정보 보호법"))
        self.assertFalse(spacing_only("정보통신망법", "정보통신망 이용촉진 및 정보보호 등에 관한 법률"))
        self.assertFalse(spacing_only("개인정보 보호법", ""))
        with tempfile.TemporaryDirectory() as folder:
            table = Path(folder) / "law_names.tsv"
            table.write_text("개인 정보 보호법\t개인정보 보호법\t011357\t20250313\t일부개정\t현행\t개인정보 보호법\t2026-11-10\n"
                             "정보통신망법\t정보통신망 이용촉진 및 정보보호 등에 관한 법률\t000030\t20261002\t일부개정\t현행\t\t2026-11-10\n", encoding="utf-8")
            elements = ((f"{CODE}.1", "a하기", ["1.1 개인 정보 보호법에 따라 등록할 수 있다."]),)
            m = read_module(module_table([([0], "1. a하기", [("1-1. 등록", ["1.1 「개인정보보호법」과 정보통신망법에 따라 등록할 수 있다."])])], elements=elements))
            rows = {r["원고"]: r for r in check_laws(m, LawCatalog(table))}
            plan_side = rows["개인정보보호법"]
            self.assertEqual(plan_side["체크"][LABEL], "X")
            self.assertIn("띄어쓰기만 다름", plan_side["비고"][LABEL])
            self.assertEqual(plan_side["수정 제안"], "「개인정보보호법」 → 「개인정보 보호법」로 띄어쓰기 수정")
            self.assertEqual(rows["개인 정보 보호법"]["체크"][LABEL], "△")              # NCS 쪽 → 직능연 협의
            self.assertIn("직능연", rows["개인 정보 보호법"]["비고"][LABEL])
            self.assertEqual(rows["정보통신망법"]["체크"][LABEL], "O")             # 약칭은 참고만
            self.assertIn("약칭", rows["정보통신망법"]["비고"][LABEL])


class ElementsTableTests(unittest.TestCase):
    def test_read_elements_and_criteria_format(self):
        from ncs_core.ncs_catalog import CRITERIA_SEP, read_elements

        with tempfile.TemporaryDirectory() as folder:
            table = Path(folder) / "ncs_elements.tsv"
            table.write_text("# 표\n12030202\t1203020201_24v3\t객실 예약 관리\t3\t객실 예약 접수란 … 능력이다.\t1203020201_24v3.1\t객실 · 부대시설 이용정보 파악하기\t"
                             + CRITERIA_SEP.join(C1) + "\n12030202\t1203020201_24v3\t객실 예약 관리\t3\t객실 예약 접수란 … 능력이다.\t1203020201_24v3.2\t예약 현황 확인하기\t"
                             + CRITERIA_SEP.join(C2) + "\n", encoding="utf-8")
            units = read_elements(table)
            unit = units["1203020201"]
            self.assertEqual((unit["name"], unit["level"], len(unit["elements"])), ("객실 예약 관리", 3, 2))
            self.assertEqual(unit["elements"][0]["criteria"], C1)
            self.assertEqual(unit["elements"][1]["no"], 2)
