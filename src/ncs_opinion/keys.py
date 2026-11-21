"""의견 문장 읽기 도우미 — 의견이 가리키는 표·그림 참조를 뽑고, 대조용으로 글을 줄인다. I/O 없음.

의견의 유형·요구 내용은 읽지 않는다(LLM이 판정한다). 여기서 뽑는 것은 보낼 원고 범위를 정하는 데 쓰는 참조뿐이다.
- 참조: <표 1-3>, [그림 1-6], '표 5-2' → (종류, 'N-M')
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REF = re.compile(r"[<\[〈(]?\s*(표|그림)\s*(\d+)\s*-\s*(\d+)\s*[>\]〉)]?")


@dataclass(frozen=True)
class Ref:
    kind: str      # '표' | '그림'
    number: str    # '1-3'

    @property
    def label(self) -> str:
        return f"<표 {self.number}>" if self.kind == "표" else f"[그림 {self.number}]"


def compact(text: str) -> str:
    """대조용: 공백·하이픈·가운뎃점·따옴표·괄호 없이, 영문은 소문자."""
    return re.sub(r"[\s\-‐–—·ㆍ･‧∙⋅'‘’\"“”「」『』()<>\[\]〈〉]", "", text).lower()


def refs_of(text: str) -> list[Ref]:
    out: list[Ref] = []
    for match in REF.finditer(text):
        ref = Ref(match.group(1), f"{int(match.group(2))}-{int(match.group(3))}")
        if ref not in out:
            out.append(ref)
    return out
