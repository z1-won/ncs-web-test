"""개발계획서 점검(ncs_plan): 표 읽기와 ①~⑨ 규칙을 합성 표로 검사한다. 실제 계획서 샘플이 있으면 끝에서 한 번 돌려 본다."""

import tempfile
import unittest
from pathlib import Path

from ncs_core.lexicon import ActionNounLexicon
from ncs_plan.parsers import read_change_table, read_module, read_plan, read_summary_table
from ncs_plan.rules.front import check_change_table, check_identity, check_required, expected_analysis
from ncs_plan.rules.module import check_element_codes, check_goal, check_lessons, check_subs, check_targets

CODE = "1203020201_24v3"
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

    def test_element_code_sequence(self):
        elements = ((f"{CODE}.1", "a하기", C1), ("1203020299_24v3.2", "b하기", C2))
        m = read_module(module_table([([0], "1. a하기", [("1-1. 구분", C1)]), ([1], "2. b하기", [("2-1. 조회", C2)])], elements=elements))
        [row] = check_element_codes(m)
        self.assertEqual(row["판정"], "부적합")
        self.assertIn("1203020299_24v3.2", row["비고"]["⑤ 요소 코드 연번"])

    def test_targets_missing_extra_space_and_changed(self):
        spaced = C1[0].replace("구분 할 수", "구분할 수")                    # 띄어쓰기만 → 허용
        changed = C2[0].replace("파악할", "확인할")                        # 글자 다름 → △
        m = read_module(module_table([([0], "1. a하기", [("1-1. 구분", [spaced, "1.3 수행준거에 없는 문장을 쓸 수 있다."])]),
                                      ([1], "2. b하기", [("2-1. 조회", [changed])])]))
        first, second = check_targets(m)
        self.assertEqual(first["체크"], {"⑥ 수행준거 누락 없음": "X", "⑥ 수행준거 외 문장 없음": "X", "⑥ 문장 수정 없음": "O"})
        self.assertIn("마켓별 요금", first["비고"]["⑥ 수행준거 누락 없음"])
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
class RealSampleTests(unittest.TestCase):
    def test_real_plan_runs_and_finds_known_numbering_errors(self):
        from ncs_plan import run_review

        result = run_review([SAMPLE])
        self.assertEqual(result.diagnostics["counts"]["modules"], 7)
        by_no = {row["번호"]: row["검수결과"] for row in result.sheet}
        self.assertEqual((by_no["①"], by_no["②"], by_no["⑤"], by_no["⑨"]), ("적합", "적합", "적합", "적합"))
        self.assertEqual(by_no["⑦"], "부적합")   # 객실 매출 관리 학습 1의 '1.1 …' 번호 표기
        self.assertTrue(any("1.1 호텔 시장 동향" in n for r in result.checklist if r["item_id"] == "PLAN-⑦" for n in r["비고"].values()))


if __name__ == "__main__":
    unittest.main()


class FillTests(unittest.TestCase):
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
            self.assertEqual(plan["위치"]["모듈"][0], {"능력단위": "객실 예약 관리", "학습모듈명": "객실 예약 관리"})
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
            for no in "②③④⑤⑥⑧":
                self.assertEqual(by_no[no], "적합", (no, [r["비고"] for r in result.checklist if r["item_id"] == f"PLAN-{no}" and r["판정"] != "적합"]))
            self.assertEqual(by_no["⑦"], "판단불가")   # 학습 내용명은 집필자 작성 칸이라 비어 있음


class LawTests(unittest.TestCase):
    def test_extract_law_names(self):
        from ncs_core.law_catalog import extract_law_names

        self.assertEqual(extract_law_names("「개인정보 보호법」에 따라"), [("개인정보 보호법", True)])
        self.assertEqual(extract_law_names("근로기준법과 최저임금법은"), [("근로기준법", False), ("최저임금법", False)])
        self.assertEqual(extract_law_names("규정에 따라 산업안전보건법을 지킨다"), [("산업안전보건법", False)])
        self.assertEqual(extract_law_names("화학물질관리법 시행규칙에 따른다"), [("화학물질관리법 시행규칙", False)])
        self.assertEqual(extract_law_names("작업 방법과 분석 기법, 법인 설립의 법적 근거"), [])

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
