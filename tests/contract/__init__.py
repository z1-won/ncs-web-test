"""테스트 묶음. 외부 호출 차단을 먼저 적용한다(tests/_env.py)."""

import sys
from pathlib import Path

# 저장소 루트에서 `python -m unittest tests.contract.test_x`처럼 한 파일만 돌릴 때는 tests/가 sys.path에 없다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _env  # noqa: E402,F401
