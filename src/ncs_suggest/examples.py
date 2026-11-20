"""참고 예문 — 같은 원고에서 같은 종류이면서 규정 꼴을 지킨 문장 가운데 형태가 비슷한 것을 붙인다.

직무 내용을 새로 만들지 않고 맥락을 주는 방법이다(요구사항: '같은 원고 안의 잘 쓰인 문장'). 유사도는 difflib 글자 일치율.
후보가 아니라 참고이므로 순위에 들지 않고, 채택 기록에도 넣지 않는다.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .config import DEFAULT_CONFIG, SuggestConfig


def similar(body: str, pool: list[tuple[str, str]], *, config: SuggestConfig = DEFAULT_CONFIG) -> list[dict]:
    """pool: [(본문, 자리)] — 규정을 지킨 같은 종류 문장. → [{'문장','자리','유사도'}] 유사도 순, 최대 config.max_examples개."""
    scored = []
    for text, where in pool:
        if text == body:
            continue
        ratio = SequenceMatcher(None, body, text, autojunk=False).ratio()
        if ratio >= config.example_min:
            scored.append((ratio, text, where))
    scored.sort(key=lambda item: -item[0])
    return [{"문장": text, "자리": where, "유사도": round(ratio, 2)} for ratio, text, where in scored[: config.max_examples]]
