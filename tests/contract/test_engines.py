"""엔진 계약 검사. ncs_service.registry.ENGINES에 등록된 모든 엔진이 공통 계약(docs/CONVENTIONS.md)을 지키는지 본다.

엔진 이름을 여기에 적지 않는다. 새 구성요소 엔진을 ENGINES에 등록하면 이 테스트가 자동으로 그 엔진을 검사한다.
"""

import dataclasses
import json
from importlib import import_module
import re
import sys
import tempfile
import unittest
import zipfile
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from ncs_core import Rule, ReviewResult, SavedReport, VERDICTS, flatten, visible
from ncs_core.f02_items import F02_ITEMS
from ncs_core.plan_items import PLAN_ITEMS
from ncs_core.sheet import NOT_CHECKED
from ncs_service import ReviewRequest, execute_review, persist_review
from ncs_service.registry import ENGINES

FIXTURES = ROOT / "tests" / "fixtures"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"
CODE = "LM1203020201_24v3"

PUBLIC_API = ("CheckConfig", "DEFAULT_RULES", "prepare_review", "evaluate_review", "run_review", "save_results")
ROW_KEYS = {"item_id", "region_path", "원고", "체크", "판정", "비고", "수정 제안"}
SHEET_KEYS = {"구성요소", "번호", "체크 항목", "검수결과", "적합", "부적합", "비고"}
CHECK_VALUES = {"O", "X", "△", "-"}
SHEET_ITEMS = {**F02_ITEMS, **PLAN_ITEMS}   # 확인서 구성요소: F02 10개 + 개발계획서(REQ-02-001)


def engines():
    for check, engine in ENGINES.items():
        yield check, engine, engine.load()


class EngineContractTests(unittest.TestCase):
    def test_registry_entries_are_well_formed(self):
        for check, engine, module in engines():
            with self.subTest(check=check):
                self.assertTrue(re.fullmatch(r"[a-z]+", check), "check 이름은 소문자 영문이어야 합니다")
                self.assertEqual(module.__name__, engine.package)
                self.assertTrue({"manuscript", "plan"} & set(engine.required), "원고 또는 개발계획서 중 하나는 필수여야 합니다")
                self.assertLessEqual(set(engine.required), {"manuscript", "plan"})

    def test_report_names_are_unique(self):
        names = [import_module(engine.package + ".reporting").REPORT_NAME for _, engine, _ in engines()]
        self.assertEqual(len(names), len(set(names)), f"REPORT_NAME이 중복됩니다: {names}")

    def test_public_api_is_exported(self):
        for check, engine, module in engines():
            with self.subTest(check=check):
                for name in PUBLIC_API:
                    self.assertTrue(hasattr(module, name), f"{module.__name__}에 {name}이 없습니다")
                    self.assertIn(name, module.__all__, f"{module.__name__}.__all__에 {name}이 없습니다")
                config = module.CheckConfig()
                self.assertTrue(dataclasses.is_dataclass(config) and config.__dataclass_params__.frozen,
                                "CheckConfig는 frozen dataclass여야 합니다")
                self.assertIsInstance(module.DEFAULT_RULES, Sequence)
                self.assertTrue(module.DEFAULT_RULES, "기본 규칙이 하나는 있어야 합니다")
                for rule in module.DEFAULT_RULES:
                    self.assertIsInstance(rule, Rule)
                keys = [rule.key for rule in module.DEFAULT_RULES]
                self.assertEqual(len(keys), len(set(keys)), "규칙 key가 중복됩니다")
                # 보고서 이름·요약은 파일 저장과 DB 이력 저장이 함께 쓴다. 엔진 목록을 다른 곳에 복사하지 않기 위한 계약.
                reporting = import_module(engine.package + ".reporting")
                self.assertIsInstance(reporting.REPORT_NAME, str)
                self.assertTrue(reporting.REPORT_NAME, f"{engine.package}.reporting.REPORT_NAME이 비어 있습니다")
                self.assertTrue(callable(reporting.summary), f"{engine.package}.reporting.summary가 없습니다")
                self.assertTrue(all(tail.startswith(reporting.REPORT_NAME) for _, tail in reporting.ITEM_FILES),
                                "ITEM_FILES 꼬리말은 REPORT_NAME으로 시작해야 합니다(이관 시 파일 인식 기준)")

    def test_review_result_follows_checklist_and_sheet_contract(self):
        for check, _, module in engines():
            with self.subTest(check=check):
                result = execute_review(ReviewRequest((MANUSCRIPT, PLAN), check)).result
                self.assertIsInstance(result, ReviewResult)
                self.assertEqual(result.module_code, CODE)
                self.assertTrue(result.checklist, "기본 규칙이 체크리스트 행을 내야 합니다")
                prefixes = tuple(rule.item_prefix for rule in module.DEFAULT_RULES)
                for row in result.checklist:
                    self.assertLessEqual(ROW_KEYS, row.keys(), f"체크리스트 행 키 부족: {row.keys()}")
                    self.assertTrue(row["item_id"].startswith(prefixes), row["item_id"])
                    self.assertIn(row["판정"], VERDICTS)
                    self.assertIsInstance(row["체크"], dict)
                    self.assertLessEqual(set(row["체크"].values()), CHECK_VALUES, row["체크"])
                    self.assertIsInstance(row["비고"], (dict, list))
                self.assertEqual(result.findings, flatten(result.checklist), "지적사항은 체크리스트의 X·△ 체크를 펼친 것")
                self.assertTrue(result.sheet, "확인서 표가 비어 있습니다")
                components = {row["구성요소"] for row in result.sheet}
                self.assertEqual(len(components), 1, "엔진 하나는 확인서 구성요소 하나를 맡습니다")
                component = components.pop()
                self.assertIn(component, SHEET_ITEMS, "확인서 구성요소 이름은 F02 원문(또는 개발계획서 항목)과 같아야 합니다")
                self.assertEqual([row["번호"] for row in result.sheet], list(SHEET_ITEMS[component]),
                                 "확인서 행은 해당 구성요소의 모든 항목 번호를 원문 순서로 가져야 합니다")
                for row in result.sheet:
                    self.assertLessEqual(SHEET_KEYS, row.keys())
                    # 확인서 문구는 원문을 visible()로 표시 변환한 것(기호 글꼴의 네모 번호 → [1])
                    self.assertEqual(row["체크 항목"], visible(SHEET_ITEMS[component][row["번호"]]))
                    self.assertIn(row["검수결과"], set(VERDICTS) | {NOT_CHECKED})
                for key in ("module_code", "implemented", "not_implemented", "warnings"):
                    self.assertIn(key, result.diagnostics)

    def test_empty_rules_produce_unchecked_sheet(self):
        for check, _, _ in engines():
            with self.subTest(check=check):
                result = execute_review(ReviewRequest((MANUSCRIPT, PLAN), check, rules=())).result
                self.assertEqual(result.checklist, [])
                self.assertEqual({row["검수결과"] for row in result.sheet}, {NOT_CHECKED})

    def test_foreign_config_is_rejected(self):
        modules = {check: module for check, _, module in engines()}
        for check, module in modules.items():
            other = next((m for c, m in modules.items() if c != check), None)
            if other is None:
                self.skipTest("엔진이 하나뿐입니다")
            with self.subTest(check=check):
                with self.assertRaises(ValueError):
                    execute_review(ReviewRequest((MANUSCRIPT, PLAN), check, config=other.CheckConfig()))

    def test_persist_writes_standard_files_and_zip(self):
        for check, _, _ in engines():
            with self.subTest(check=check), tempfile.TemporaryDirectory(prefix="ncs_engine_test_") as out:
                execution = execute_review(ReviewRequest((MANUSCRIPT, PLAN), check))
                saved = persist_review(execution, out)
                self.assertIsInstance(saved, SavedReport)
                self.assertTrue(saved.directory.is_dir() and saved.directory.parent == Path(out).resolve())
                self.assertTrue(saved.directory.name.startswith(CODE + "_"), "실행별 폴더 이름은 <코드>_로 시작합니다")
                self.assertIn("검수결과", saved.summary)
                self.assertIn("항목", saved.summary)
                reporting = import_module(ENGINES[check].package + ".reporting")
                self.assertEqual(saved.summary, reporting.summary(execution.result),
                                 "파일 저장 요약과 summary()가 다릅니다 — 두 저장 경로가 어긋났습니다")
                names = sorted(p.name for p in saved.directory.glob("*.json"))
                for tail in ("00_요약", "지적사항", "전체", "진단", "검수확인서"):
                    self.assertTrue(any(n.startswith(CODE + "_") and n.endswith(f"_{tail}.json") for n in names),
                                    f"{tail} 파일이 없습니다: {names}")
                with zipfile.ZipFile(saved.zip_path) as archive:
                    self.assertEqual(sorted(archive.namelist()), names, "ZIP에는 모든 JSON이 들어가야 합니다")
                whole = next(p for p in saved.directory.glob("*_전체.json"))
                self.assertEqual(json.loads(whole.read_text(encoding="utf-8")), execution.result.checklist)

    def test_every_engine_package_has_the_fixed_skeleton_files(self):
        """뼈대 파일 8개는 모든 검수 패키지가 같은 이름으로 갖는다(docs/CONVENTIONS.md '구조')."""
        skeleton = ("config.py", "models.py", "registry.py", "pipeline.py", "reporting.py", "sheet.py", "__main__.py", "rules/__init__.py")
        for check, engine in ENGINES.items():
            with self.subTest(check=check):
                folder = ROOT / "src" / engine.package
                missing = [name for name in skeleton if not (folder / name).is_file()]
                self.assertEqual(missing, [], f"{engine.package}에 뼈대 파일이 없습니다")

    def test_web_server_and_frontend_list_every_engine(self):
        """엔진을 등록하면 src/ncs_web/server.py의 CheckName·health 목록과 화면의 CHECKS도 함께 갱신해야 한다."""
        registered = set(ENGINES)
        server = (ROOT / "src" / "ncs_web" / "server.py").read_text(encoding="utf-8")
        literal = re.search(r"CheckName = Literal\[(.*?)\]", server).group(1)
        self.assertEqual(set(re.findall(r'"(\w+)"', literal)), registered, "server.py CheckName")
        # /api/health의 checks·engines는 registry.ENGINES에서 만들므로 손으로 적은 목록이 없어야 한다
        self.assertIn('"checks": list(ENGINES)', server, "server.py /api/health는 ENGINES에서 생성")
        self.assertNotRegex(server, r'"checks":\s*\[', "server.py /api/health에 손으로 적은 목록이 있음")
        message = re.search(r"check는 (.*?) 중 하나여야 합니다", server).group(1)
        self.assertEqual(set(message.split(" / ")), registered, "server.py 오류 메시지")
        # 화면: 선택 목록 글은 서버 engines로 채우지만, 기본 목록(CHECKS)과 파일 안내(FILE_HINTS)는 모든 엔진을 알아야 한다
        # 두 목록은 frontend/src/lib/checks.js에 있다(App.jsx에서 옮겨 옴).
        checks = (ROOT / "frontend" / "src" / "lib" / "checks.js").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'value:\s*"(\w+)"', checks)), registered, "checks.js CHECKS")
        hints = re.search(r"const FILE_HINTS = \{(.*?)\};", checks, re.S).group(1)
        self.assertEqual(set(re.findall(r"^\s*(\w+):", hints, re.M)), registered, "checks.js FILE_HINTS")


if __name__ == "__main__":
    unittest.main()
