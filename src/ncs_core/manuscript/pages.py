"""출력본(PDF)에서 차례가 가리키는 제목이 실제로 시작하는 쪽 찾기. 판정은 하지 않는다(차례 ⑦ 규칙이 비교한다).

차례 줄은 다섯 종류다 — '학습 N. 명 쪽', 'N-M. 명 쪽', '• 교수·학습 방법 쪽', '• 평가 쪽', '참고 자료/활용 서식/부록 쪽'.
여기서는 그 각각이 본문에서 처음 나오는 쪽을 같은 열쇠로 돌려준다:
  '학습 1' · '1-1' · '학습 1 교수·학습 방법' · '학습 1 평가' · '참고 자료' · '활용 서식' · '부록'

주의한 점
- 차례 면 자체에도 '학습 1. …' 줄이 있으므로, 쪽수가 붙은 차례 줄이 있는 마지막 쪽 이후부터 찾는다.
- 학습모듈의 개요(내용 체계)에도 '1-1. 명' 줄이 있으므로, 'N-M'은 첫 내비게이터('학습 N' 큰 제목) 쪽 이후부터 찾는다.
- 내비게이터는 학습마다 '학습 1 … 학습 N'을 모두 다시 적으므로, 교수·학습 방법·평가가 속한 학습은 가장 최근 'N-M.' 제목의 N으로 정한다.
- 달리는 머리말·꼬리말은 PdfPage.body에 없다(pdf.py가 띠로 분리).
"""

from __future__ import annotations

import re

from ..pdf import PdfDocument, PdfPage
from .patterns import BODY_SUB, HEAD_EVAL, HEAD_TEACH, NAV_HEAD, TOC_LESSON

TAIL_HEAD = re.compile(r"^(참고\s*자료|활용\s*서식|부\s*록)$")
TAIL_KEYS = {"참고자료": "참고 자료", "활용서식": "활용 서식", "부록": "부록"}


def toc_pages(pdf: PdfDocument) -> list[int]:
    """쪽수가 붙은 차례 줄('학습 N. 명 3')이 있는 쪽의 물리 인덱스들."""
    found = []
    for page in pdf.pages:
        for line in page.body:
            match = TOC_LESSON.match(line)
            if match and (match.group(3) or match.group(4)):
                found.append(page.index)
                break
    return found


def locate_headings(pdf: PdfDocument) -> dict[str, dict]:
    """{열쇠: {'folio', 'source', 'index', 'line'}} — 각 제목이 처음 시작하는 쪽. 못 찾은 제목은 열쇠가 없다.

    내비게이터 묶음('학습 1 … 학습 N'이 모두 적힌 큰 제목 묶음)은 어느 학습의 시작인지 글자만으로는 알 수 없으므로
    (hwpx의 강조 스타일이 PDF에는 없다), 그 묶음 뒤에 처음 나오는 'N-M.' 제목의 N을 묶음의 학습으로 본다.
    """
    toc = toc_pages(pdf)
    start = (max(toc) + 1) if toc else 0
    found: dict[str, dict] = {}
    pending_nav: tuple[PdfPage, str] | None = None   # 아직 학습 번호를 모르는 내비게이터 묶음(쪽, 첫 줄)
    body_started = False
    lesson: int | None = None

    def put(key: str, page: PdfPage, line: str) -> None:
        if key not in found:
            found[key] = {"folio": page.folio, "source": page.folio_source, "index": page.index, "line": line}

    for page in pdf.pages[start:]:
        for line in page.body:
            if NAV_HEAD.match(line):
                body_started = True
                if pending_nav is None:
                    pending_nav = (page, line)
                continue
            if not body_started:
                continue
            sub = BODY_SUB.match(line)
            if sub and sub.group(3):
                lesson = int(sub.group(1))
                if pending_nav is not None:
                    put(f"학습 {lesson}", *pending_nav)
                    pending_nav = None
                put(f"{lesson}-{int(sub.group(2))}", page, line)
                continue
            if lesson is not None and HEAD_TEACH.match(line):
                put(f"학습 {lesson} 교수·학습 방법", page, line)
                continue
            if lesson is not None and HEAD_EVAL.match(line):
                put(f"학습 {lesson} 평가", page, line)
                continue
            tail = TAIL_HEAD.match(line)
            if tail:
                put(TAIL_KEYS[re.sub(r"\s+", "", tail.group(1))], page, line)
    return found
