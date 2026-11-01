"""설치된 배포 메타데이터와 작업 폴더에 독립적인 실행 명령을 검증한다."""

import importlib.metadata
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path


class InstallationTests(unittest.TestCase):
    def run_outside_project(self, args):
        with tempfile.TemporaryDirectory(prefix="ncs_installed_test_") as folder:
            return subprocess.run(
                args, cwd=folder,
                env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
                capture_output=True, text=True, timeout=30,
            )

    def test_distribution_separates_optional_dependencies(self):
        dist = importlib.metadata.distribution("ncs-f02-review")
        self.assertEqual(set(dist.metadata.get_all("Provides-Extra")), {"web", "test"})
        self.assertTrue(dist.requires)
        self.assertTrue(all("extra ==" in requirement for requirement in dist.requires))
        self.assertEqual({entry.name for entry in dist.entry_points if entry.group == "console_scripts"}, {
            "ncs-web", "ncs-position", "ncs-toc", "ncs-overview", "ncs-knowledge", "ncs-perform", "ncs-evaluation",
        })

    def test_isolated_imports_and_web_factory_outside_repository(self):
        script = '''
import json
import ncs_core, ncs_service, ncs_position, ncs_toc, ncs_overview, ncs_knowledge
from ncs_web.server import create_app
print(json.dumps(sorted(route.path for route in create_app().routes)))
'''
        result = self.run_outside_project([sys.executable, "-I", "-c", script])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/api/review", json.loads(result.stdout))

    def test_console_commands_and_module_command(self):
        scripts = Path(sysconfig.get_path("scripts"))
        for name in ("ncs-web", "ncs-position", "ncs-toc", "ncs-overview", "ncs-knowledge"):
            with self.subTest(command=name):
                result = self.run_outside_project([str(scripts / name), "--help"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--out", result.stdout)
                if name == "ncs-web":
                    self.assertIn("--dist", result.stdout)
                    self.assertNotIn("--src", result.stdout)
        result = self.run_outside_project([sys.executable, "-I", "-m", "ncs_web", "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        removed_option = self.run_outside_project([str(scripts / "ncs-web"), "--src", "src"])
        self.assertEqual(removed_option.returncode, 2)


if __name__ == "__main__":
    unittest.main()
