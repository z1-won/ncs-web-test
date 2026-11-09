"""실행 조정의 설정·규칙 전달 및 CLI 호환성을 실제 문서와 함께 검증한다."""

import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

from ncs_core import Rule
from ncs_service import ReviewRequest, execute_review

FIXTURES = ROOT / "tests" / "fixtures"
MANUSCRIPT = FIXTURES / "원고_ok_LM1203020201_24v3.hwpx"
PLAN = FIXTURES / "개발계획서_LM1203020201_24v3.hwpx"
CHECKS = ("position", "toc", "overview", "knowledge")
CODE = "LM1203020201_24v3"


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ncs_service_test_")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.swapped = self.folder / "renamed.hwpx"
        # 실제 섹션 위치를 바꾸어 기본 설정으로는 성공할 수 없는 입력을 만든다.
        with zipfile.ZipFile(MANUSCRIPT) as original, zipfile.ZipFile(self.swapped, "w") as target:
            for name in original.namelist():
                mapped = {
                    "Contents/section0.xml": "Contents/section1.xml",
                    "Contents/section1.xml": "Contents/section0.xml",
                }.get(name, name)
                target.writestr(mapped, original.read(name))

    def config_for(self, check):
        engine = importlib.import_module(f"ncs_{check}")
        options = {"front_section": 1}
        if check in ("toc", "knowledge"):
            options["body_section"] = 0
        return engine.CheckConfig(**options)

    def test_config_roles_and_module_override_reach_each_engine(self):
        roles = {str(self.swapped): "manuscript", str(PLAN): "plan"}
        for check in CHECKS:
            with self.subTest(check=check):
                engine = importlib.import_module(f"ncs_{check}")
                config = self.config_for(check)
                request = ReviewRequest((PLAN, self.swapped), check, CODE, roles, config)
                actual = execute_review(request).result
                expected = engine.run_review(request.paths, roles=roles, module_code=CODE, config=config)
                self.assertIs(actual.context.config, config)
                self.assertEqual(actual.checklist, expected.checklist)
                self.assertEqual(actual.findings, expected.findings)
                self.assertEqual(actual.sheet, expected.sheet)
                self.assertEqual(actual.diagnostics, expected.diagnostics)
                self.assertEqual(actual.diagnostics["sections"]["front"], 1)
                self.assertEqual(actual.module_code, CODE)

    def test_custom_rules_replace_defaults_and_receive_config(self):
        for check in CHECKS:
            with self.subTest(check=check):
                engine = importlib.import_module(f"ncs_{check}")
                config = engine.CheckConfig()
                prefix = engine.DEFAULT_RULES[0].item_prefix
                row = {
                    "item_id": prefix, "region_path": "custom", "원고": "직접 정의한 규칙",
                    "체크": {"사용자 규칙": "X"}, "판정": "부적합",
                    "비고": {"사용자 규칙": "설정 전달 확인"}, "수정 제안": "테스트",
                }
                seen = []

                def custom(context):
                    seen.append(context.config)
                    return [row]

                rules = (Rule("custom", prefix, custom),)
                result = execute_review(ReviewRequest(
                    (MANUSCRIPT, PLAN), check, config=config, rules=rules,
                )).result
                self.assertEqual(seen, [config])
                self.assertEqual(result.checklist, [row])
                self.assertEqual(len(result.findings), 1)
                self.assertEqual(result.findings[0]["check"], "사용자 규칙")

    def test_empty_rules_do_not_fall_back_to_defaults(self):
        for check in CHECKS:
            with self.subTest(check=check):
                result = execute_review(ReviewRequest((MANUSCRIPT, PLAN), check, rules=())).result
                self.assertEqual(result.checklist, [])
                self.assertEqual(result.findings, [])
                self.assertEqual(result.diagnostics["implemented"], [])
                self.assertTrue(all(row["검수결과"] == "미검사" for row in result.sheet))
                self.assertTrue(execute_review(ReviewRequest((MANUSCRIPT, PLAN), check)).result.checklist)

    def test_wrong_config_rejected_before_reading_files(self):
        from ncs_position import CheckConfig

        with self.assertRaisesRegex(ValueError, "ncs_toc.CheckConfig"):
            execute_review(ReviewRequest((self.folder / "missing.hwpx",), "toc", config=CheckConfig()))

    def test_rule_validation_is_preserved(self):
        rule = Rule("duplicate", "F02-차례-①", lambda context: [])
        with self.assertRaisesRegex(ValueError, "중복된 규칙"):
            execute_review(ReviewRequest((MANUSCRIPT,), "toc", rules=(rule, rule)))

    def test_each_cli_uses_shared_execution_and_save(self):
        from ncs_service import save_cli_review

        for check in CHECKS:
            with self.subTest(check=check):
                cli = importlib.import_module(f"ncs_{check}.__main__")
                engine = importlib.import_module(f"ncs_{check}")
                output = self.folder / check
                args = [f"ncs_{check}", str(self.swapped), str(PLAN),
                        "--manuscript", str(self.swapped), "--plan", str(PLAN),
                        "--module-code", CODE, "--front-section", "1", "--out", str(output)]
                if check in ("toc", "knowledge"):
                    args.extend(["--body-section", "0"])
                stdout = io.StringIO()
                with (
                    patch.object(sys, "argv", args),
                    patch.object(cli, "execute_review", wraps=execute_review) as execute,
                    patch.object(cli, "save_cli_review", wraps=save_cli_review) as persist,
                    patch.object(engine, "run_review", side_effect=AssertionError("CLI가 엔진 직접 호출")),
                    redirect_stdout(stdout),
                ):
                    cli.main()
                execute.assert_called_once()
                persist.assert_called_once()
                self.assertEqual(persist.call_args.kwargs["out"], str(output), "--out은 저장 폴더로 그대로 넘어간다")
                self.assertEqual(list(persist.call_args.args[1]), [str(self.swapped), str(PLAN)], "입력 경로를 이력용으로 넘긴다")
                request = execute.call_args.args[0]
                self.assertEqual(request.check, check)
                self.assertEqual(request.config, self.config_for(check))
                self.assertEqual(request.roles, {str(self.swapped): "manuscript", str(PLAN): "plan"})
                self.assertIn("지적사항", stdout.getvalue())
                result_file = next(output.glob("*/*_전체.json"))
                expected = execute_review(request).result
                self.assertEqual(json.loads(result_file.read_text()), expected.checklist)

    def run_cli(self, check, *args):
        return subprocess.run(
            [sys.executable, "-m", f"ncs_{check}", *map(str, args)],
            cwd=self.folder, env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            capture_output=True, text=True, timeout=30,
        )

    def test_cli_subprocess_success_and_errors(self):
        for check in CHECKS:
            with self.subTest(check=check):
                success = self.run_cli(check, MANUSCRIPT, PLAN, "--out", self.folder / f"subprocess_{check}")
                self.assertEqual(success.returncode, 0, success.stderr)
                self.assertIn("지적사항", success.stdout)
                error = self.run_cli(check, MANUSCRIPT, PLAN, "--front-section", "-1")
                self.assertEqual(error.returncode, 2)
                self.assertIn("검수 실행 실패:", error.stderr)
                self.assertNotIn("Traceback", error.stderr)
        missing_plan = self.run_cli("position", MANUSCRIPT)
        self.assertEqual(missing_plan.returncode, 2)
        self.assertIn("개발계획서 파일이 필요합니다", missing_plan.stderr)


if __name__ == "__main__":
    unittest.main()
