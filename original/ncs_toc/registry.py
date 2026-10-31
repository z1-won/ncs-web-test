"""규칙 추가 지점. 함수는 CheckContext 하나를 받아 기존 형식의 행 목록을 반환한다."""
from dataclasses import dataclass
from typing import Callable
from .models import CheckContext
from .rules.names import check_toc1
from .rules.consistency import check_toc3
from .rules.tail import check_toc5, check_toc6


@dataclass(frozen=True)
class Rule:
    item_id: str
    run: Callable[[CheckContext], list[dict]]


DEFAULT_RULES = (
    Rule("F02-차례-①", lambda c: check_toc1(c.plan, c.toc)),
    Rule("F02-차례-③", lambda c: check_toc3(c.plan, c.toc, c.overview, c.body, c.eval_tables)),
    Rule("F02-차례-⑤", lambda c: check_toc5(c.presence, c.toc)),
    Rule("F02-차례-⑥", lambda c: check_toc6(c.presence, c.toc)),
)


def run_rules(context, rules=DEFAULT_RULES):
    rows = []
    for rule in rules:
        result = rule.run(context)
        if any(row["item_id"] != rule.item_id for row in result):
            raise ValueError(f"{rule.item_id} 규칙의 반환 item_id가 다릅니다")
        rows.extend(result)
    return rows
