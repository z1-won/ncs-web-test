"""본문 구조 보조는 ncs_core.manuscript.units로 옮겼다. 이름은 기존 호출자를 위해 남긴다."""

from ncs_core.manuscript.units import GOAL_LINE, HEAD_MARK, MEMO_LINE, mark, unit_regions as _unit_regions

from .config import DEFAULT_CONFIG, CheckConfig

__all__ = ["GOAL_LINE", "HEAD_MARK", "MEMO_LINE", "mark", "unit_regions"]


def unit_regions(body: dict, config: CheckConfig = DEFAULT_CONFIG) -> list[dict]:
    return _unit_regions(body, goal_lookahead=config.goal_lookahead)
