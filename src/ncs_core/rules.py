"""규칙 등록과 실행. 규칙 함수는 컨텍스트 하나를 받아 체크리스트 행 목록을 돌려준다."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rule:
    """key: 규칙 식별자(중복 불가). item_prefix: 반환 행의 item_id가 시작해야 하는 문자열."""

    key: str
    item_prefix: str
    run: Callable[[Any], list[dict]]


def run_rules(context: Any, rules: Sequence[Rule]) -> list[dict]:
    keys = [rule.key for rule in rules]
    if len(keys) != len(set(keys)):
        raise ValueError("중복된 규칙 key가 있습니다")
    rows: list[dict] = []
    for rule in rules:
        result = rule.run(context)
        for row in result:
            if not row["item_id"].startswith(rule.item_prefix):
                raise ValueError(f"{rule.key} 규칙이 다른 item_id를 반환했습니다: {row['item_id']}")
        rows.extend(result)
    return rows
