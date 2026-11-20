"""원고 분량 자동 산정(REQ-02-013) — 집필료 산정용으로 완성 원고의 분량(쪽·행)을 구성별로 세고, 기존 원고 대비 변경 분량을 낸다.

검수 엔진이 아닌 기능 패키지다(ncs_plan·ncs_upscale과 같은 층, ncs_core만 import). 판정(O/X)을 내지 않고 산정표를 낸다.
산정 규칙과 설정값의 근거는 config.py, 줄 배치 읽기는 layout.py, 구성 나누기는 segments.py, 변경 행은 diff.py, 합산은 pipeline.py.
"""

from .config import DEFAULT_CONFIG, VolumeConfig
from .pipeline import manual_check, measure, round_half_up, tally

__all__ = ["DEFAULT_CONFIG", "VolumeConfig", "manual_check", "measure", "round_half_up", "tally"]
