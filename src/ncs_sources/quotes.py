"""어문 자료 문장 단위 출처 — 인용 부호로 묶은 긴 문장인데 그 문단·바로 다음 문단에 출처 표시가 없는 후보(△).

규칙이 볼 수 있는 것은 '인용한 티가 나는 문장'뿐이다. 인용 부호 없이 남의 문장을 옮긴 경우(표절·의역)는 규칙으로 못 찾는다
— 그 부분은 LLM(또는 문서 대조)이 필요하다(service.LLM_NEEDED).
"""

from __future__ import annotations

import re

from ncs_core.source_line import SRC_HEAD

QUOTE = re.compile(r"[“\"「『]([^”\"」』]{30,})[”\"」』]")
# 같은 문단 안의 출처 표시: (저자, 연도) / 저자(연도) / 각주식 '출처:' / 연도 괄호 + '에 따르면'
CITE = re.compile(r"\([^()]{1,40}?,\s*\d{4}[a-z]?(?:,\s*pp?\.\s*\d+)?\)|[가-힣A-Za-z]\s*\(\d{4}[a-z]?\)|출\s*처\s*[:：]|에\s*따르면|재인용")


def quote_candidates(document, *, section: int = 1, end: int | None = None, limit: int = 200) -> list[dict]:
    if section >= len(document.sections):
        return []
    paragraphs = document.sections[section]
    in_table = document.section_table_paragraphs(section) or frozenset()
    aside = document.section_aside_paragraphs(section) or frozenset()
    stop = end if end is not None else len(paragraphs)
    out = []
    for i in range(stop):
        text = (paragraphs[i] or "").strip()
        if not text or i in in_table or i in aside:
            continue                       # 표 안(사례·대본·서식)은 인용 문장이 아닌 경우가 많아 뺀다
        quoted = QUOTE.findall(text)
        if not quoted or CITE.search(text):
            continue
        nxt = next(((paragraphs[j] or "").strip() for j in range(i + 1, min(i + 3, len(paragraphs))) if (paragraphs[j] or "").strip()), "")
        if SRC_HEAD.match(nxt):
            continue
        out.append({"para": i, "text": text, "quote": quoted[0][:80]})
        if len(out) >= limit:
            break
    return out
