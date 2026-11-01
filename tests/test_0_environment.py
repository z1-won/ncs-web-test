"""테스트 실행 환경 고정 — 이 파일은 이름 때문에 discover가 가장 먼저 import 한다.

- 외부 호출 차단: 셸에 .env가 로드돼 있어도(LLM_API_KEY, LLM_ALLOW_UPLOAD=1) 단위 테스트가 LLM·사전 API를 부르지 않게 비운다.
  네트워크가 필요한 확인은 scripts/llm_probe.py, scripts/build_*.py로 따로 한다.
- NCS 목록 비활성화는 golden_cases가 맡는다(합성 원고는 실제 NCS와 다르므로).
단일 모듈만 실행할 때(python -m unittest tests.test_x)는 이 파일이 로드되지 않으니 그때는 셸 환경을 비우고 돌린다.
"""

import os
import unittest

for name in ("LLM_API_KEY", "OPENAI_API_KEY", "LLM_ALLOW_UPLOAD", "STDICT_API_KEY"):
    os.environ[name] = ""


class EnvironmentTests(unittest.TestCase):
    def test_external_calls_are_disabled(self):
        from ncs_core import llm
        self.assertFalse(llm.settings().ready)
        self.assertEqual(os.environ.get("STDICT_API_KEY"), "")
