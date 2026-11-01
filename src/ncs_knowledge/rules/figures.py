"""F02 필요지식 ⑦: 그림·표 번호 연속 — figtab.check_figtab 행을 그대로 쓴다(행 = 그림/표 × 학습 묶음)."""

from ..figtab import check_figtab


def check_figures(sections, labels: dict, *, min_agreement: float) -> list[dict]:
    return check_figtab(sections, labels["lesson_spans"], min_agreement=min_agreement, labels=labels)
