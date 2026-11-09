"""테스트 실행 환경 고정 — 각 테스트 묶음(core/, engines/ …)의 __init__.py가 가장 먼저 import 한다.

- 외부 호출 차단: 셸에 .env가 로드돼 있어도(LLM_API_KEY, LLM_ALLOW_UPLOAD=1) 단위 테스트가 LLM·사전 API를 부르지 않게 비운다.
  네트워크가 필요한 확인은 scripts/probe/llm_probe.py, scripts/data/build_*.py로 따로 한다.
- NCS 목록 비활성화는 golden_cases가 맡는다(합성 원고는 실제 NCS와 다르므로).
실행은 저장소 루트에서 `python -m unittest discover tests`. 묶음 하나만 돌릴 때는
`python -m unittest discover tests/engines -t tests`처럼 -t tests를 주면 이 파일이 먼저 로드된다.
"""

import os

for name in ("LLM_API_KEY", "OPENAI_API_KEY", "LLM_ALLOW_UPLOAD", "STDICT_API_KEY"):
    os.environ[name] = ""
