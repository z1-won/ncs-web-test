"""테스트 실행 환경 고정이 적용됐는지 확인한다. 실제 고정은 tests/_env.py(묶음 __init__.py가 먼저 import)."""

import os
import unittest


class EnvironmentTests(unittest.TestCase):
    def test_external_calls_are_disabled(self):
        from ncs_core import llm
        self.assertFalse(llm.settings().ready)
        self.assertEqual(os.environ.get("STDICT_API_KEY"), "")
