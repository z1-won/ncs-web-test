"""규칙 등록과 실행. 규칙 함수는 컨텍스트 하나를 받아 체크리스트 행 목록을 돌려준다.

규칙이 행을 하나도 내지 않으면 그 항목을 판단불가(△) 한 행으로 남긴다 — 검사 대상이 없는 것인지 못 읽은 것인지 가릴 수 없고,
행이 없으면 확인서에 '미검사 — 규칙 미구현'으로 보여 규칙이 없는 항목과 구분되지 않는다. 대상이 없음을 규칙이 아는 경우에는
규칙이 직접 해당 없음(-) 행을 낸다(예: 그림이 없는 원고의 해상도).
규칙 하나가 예외로 끝나도 검수를 멈추지 않는다 — 그 규칙의 항목만 판단불가(△) 한 행으로 남기고 나머지 규칙은 계속 돈다.
'확신할 수 없으면 판단불가'와 같은 원칙이다: 못 본 항목을 적합·미검사로 보이게 두지 않고, 다른 항목의 결과도 버리지 않는다.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .text import TRI, UNDECIDED

logger = logging.getLogger("ncs_core.rules")
NO_TARGET_CHECK = "검사 대상"     # 규칙이 행을 내지 않았을 때의 체크 이름
RULE_ERROR_CHECK = "규칙 실행"   # 실패 행의 체크 이름. 번호(①②…)가 없어 한 행에 여러 항목이 섞인 확인서 줄에도 모두 접힌다


@dataclass(frozen=True)
class Rule:
    """key: 규칙 식별자(중복 불가). item_prefix: 반환 행의 item_id가 시작해야 하는 문자열.
    failure_item_ids: 이 규칙이 예외로 끝났을 때 판단불가 행을 남길 item_id들. 비우면 item_prefix 하나
    (item_prefix가 여러 확인서 항목의 공통 머리일 뿐 item_id가 아닌 규칙만 적는다 — 예: 필요 지식 내비게이터 ①②③)."""

    key: str
    item_prefix: str
    run: Callable[[Any], list[dict]]
    failure_item_ids: tuple[str, ...] = ()


def _undecided_rows(rule: Rule, check: str, note: str) -> list[dict]:
    return [{
        "item_id": item_id, "region_path": "", "위치": "", "원고": "",
        "체크": {check: TRI}, "판정": UNDECIDED,
        "비고": {check: note}, "수정 제안": None,
    } for item_id in (rule.failure_item_ids or (rule.item_prefix,))]


def no_target_rows(rule: Rule) -> list[dict]:
    """행을 하나도 내지 않은 규칙의 항목마다 판단불가 한 행."""
    return _undecided_rows(rule, NO_TARGET_CHECK, "검사 대상을 찾지 못함 — 원고에 해당 내용이 없는지, 읽지 못한 것인지 사람이 확인하세요")


def failure_rows(rule: Rule, error: Exception) -> list[dict]:
    """예외로 끝난 규칙의 항목마다 판단불가 한 행. 비고에는 예외 종류만 적는다(메시지에 서버 경로가 들어 있을 수 있어 상세는 로그에)."""
    return _undecided_rows(rule, RULE_ERROR_CHECK,
                           f"자동 검사가 오류로 끝나 이 항목을 판정하지 못했습니다 — 사람이 확인하세요 (규칙 {rule.key}, {type(error).__name__})")


def run_rules(context: Any, rules: Sequence[Rule]) -> list[dict]:
    keys = [rule.key for rule in rules]
    if len(keys) != len(set(keys)):
        raise ValueError("중복된 규칙 key가 있습니다")
    rows: list[dict] = []
    for rule in rules:
        try:
            result = rule.run(context)
        except Exception as error:   # 규칙 하나의 결함이 다른 항목의 결과까지 버리지 않게 한다
            logger.exception("규칙 %s(%s) 실행 실패: %s", rule.key, rule.item_prefix, error)
            rows.extend(failure_rows(rule, error))
            continue
        if not result:
            rows.extend(no_target_rows(rule))
            continue
        for row in result:
            if not row["item_id"].startswith(rule.item_prefix):
                raise ValueError(f"{rule.key} 규칙이 다른 item_id를 반환했습니다: {row['item_id']}")
        rows.extend(result)
    return rows
