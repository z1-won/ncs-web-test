"""출력본 PDF에서 그림이 놓인 쪽 — 한글 파일만으로는 알 수 없는 '쪽'을 생성형 AI 결과물 현황의 쪽수와 견주기 위해 읽는다.

출력본의 줄 가운데 그림 캡션('[그림 1-1] 그림명')으로 시작하는 줄을 찾아 그 쪽의 인쇄된 쪽 번호를 모은다.
본문에서 그림을 가리키는 문장('[그림 1-1]과 같이 …')이 줄 첫머리에 오는 경우는 원고 읽기와 같은 기준으로 뺀다.
판정은 하지 않는다(check가 한다).
"""

from __future__ import annotations

import re

from ncs_core.figures import caption_label

_RANGE = re.compile(r"(\d{1,4})\s*[-–—~∼〜]\s*(\d{1,4})")
_NUMBER = re.compile(r"\d{1,4}")
MAX_RANGE = 30          # '12~300' 같은 오기를 쪽 범위로 펼치지 않는다


def figure_pages(pdf) -> dict[str, list[dict]]:
    """PdfDocument → {'그림 1-1': [{'쪽': '4' 또는 None, '추정': False, '물리 쪽': 7}, …]} (문서 순서, 같은 쪽은 한 번)."""
    found: dict[str, list[dict]] = {}
    for page in pdf.pages:
        for line in page.body:
            label = caption_label(line)
            if label is None:
                continue
            places = found.setdefault(label, [])
            if not any(place["물리 쪽"] == page.number for place in places):
                places.append({"쪽": page.folio, "추정": page.folio_source == "추정", "물리 쪽": page.number})
    return found


def page_numbers(text: str) -> list[int]:
    """결과물 현황의 쪽수 칸 → 쪽 번호들. 'p.12' → [12], 'pp. 12~13' → [12, 13], '12쪽, 15쪽' → [12, 15].

    양식의 자리표시('p.00')처럼 0뿐이거나 숫자가 없으면 [].
    """
    text = text or ""
    numbers: list[int] = []
    for first, last in _RANGE.findall(text):
        first, last = int(first), int(last)
        if first <= last <= first + MAX_RANGE:
            numbers += range(first, last + 1)
        else:                       # 범위로 보기 어려우면 적힌 두 수만 쓴다
            numbers += [first, last]
    numbers += [int(number) for number in _NUMBER.findall(_RANGE.sub(" ", text))]
    return sorted({number for number in numbers if number > 0})
