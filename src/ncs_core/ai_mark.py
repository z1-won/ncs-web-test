"""AI 활용 줄 읽기 — '○○를 활용하여 생성함/수정 보완함. YYYY. M. D.' 한 줄을 읽는 정규식과 함수를 한 곳에 둔다.

전에는 같은 줄을 읽는 정규식이 둘이었다(figures.AI_MARK, source_line.AI_LINE). 필요 지식 ⑧·권리 증빙 점검·AI 표기 넣기는 앞의 것을,
그림 검수·출처 검토는 뒤의 것을 써서, 한쪽만 고치면 같은 줄을 서로 다르게 읽을 수 있었다. 이제 둘 다 이 모듈의 read()를 쓰고
각자의 자료형(figures.AiMark, source_line.AiMarker)으로만 바꾼다.

읽는 법
- 줄 어디에 있어도 찾는다(출처 줄 뒤에 붙여 쓴 것, 캡션 앞에 붙은 것).
- 도구 이름은 40자까지, 마침표는 숫자 사이(판 번호 'ChatGPT 6.0')일 때만 이름의 일부로 본다 — 그 밖의 마침표는 앞 문장의 끝이다.
- '생성 함'처럼 '함' 앞을 띈 것도 읽는다. 일자는 없어도 되고, 달력에 없는 날이면 on이 None이다(date_text에는 적힌 글이 남는다).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

AI_MARK = re.compile(
    r"(?P<tool>[^\s.。,](?:[^.。]|(?<=\d)\.(?=\d)){0,40}?)\s*[을를]\s*활용하여\s*(?P<mode>생성|수정\s*보완)\s*함"
    r"(?:\s*\.?\s*(?P<date>(?P<y>\d{4})\s*\.\s*(?P<m>\d{1,2})\s*\.\s*(?P<d>\d{1,2})\s*\.?))?")


@dataclass(frozen=True)
class AiRead:
    tool: str               # 도구 이름
    mode: str               # 'generated'(생성함) | 'modified'(수정 보완함)
    on: date | None         # 적힌 일자(없거나 달력에 없는 날이면 None)
    date_text: str | None   # 적힌 일자 글에서 띄어쓰기를 뺀 것('2026.7.20.'), 없으면 None
    text: str               # 줄에서 AI 활용 표기에 해당하는 부분
    raw: str                # 줄 전체

    @property
    def action(self) -> str:
        return "생성" if self.mode == "generated" else "수정 보완"


def read(text: str) -> AiRead | None:
    found = AI_MARK.search(text or "")
    if not found:
        return None
    on = None
    if found.group("y"):
        try:
            on = date(int(found.group("y")), int(found.group("m")), int(found.group("d")))
        except ValueError:
            on = None
    mode = "generated" if found.group("mode") == "생성" else "modified"
    date_text = re.sub(r"\s+", "", found.group("date")) if found.group("date") else None
    return AiRead(found.group("tool").strip(), mode, on, date_text, found.group(0).strip(), (text or "").strip())
