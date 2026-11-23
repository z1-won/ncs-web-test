"""⑦ AI 활용 표기 — 직능연 「AI활용기준_도구사용표기예」(2026-09) 양식: 출처 줄 → '{도구}를 활용하여 생성함/수정 보완함. 일자' → 캡션.

AI 사용 여부를 그림을 보고 추정하지 않는다. 표기가 없으면 해당 없음(-). 서약서 결과물 현황과의 대조는 C단계(⑥과 함께).
"""

from __future__ import annotations

import re

from ncs_core.source_line import AI_MARK
from ncs_core.text import NA, O, TRI, X

from ..models import CheckOutcome

# AI 도구 이름이 들어 있고 생성·수정·활용을 말하는 줄만 — 본문의 일반 문장('~를 활용하여 분석한다')은 보지 않는다
LOOSE = re.compile(r"(?:AI|GPT|Gemini|챗GPT|Copilot|코파일럿|Midjourney|미드저니|DALL|생성형)\S*.{0,20}(?:활용|생성|수정|보완|제작)")


def check_ai_marker(item, res, cfg, prior) -> list[CheckOutcome]:
    ctx, marker = item.ctx, item.ai
    if marker is not None:
        missing = [name for name, value in (("도구", marker.tool), ("생성함/수정 보완함", marker.action), ("일자", marker.date)) if not value]
        if missing:
            return [CheckOutcome("⑦AI 표기", X, f"AI 활용 표기에 {', '.join(missing)}이(가) 없음: 「{marker.raw[:60]}」",
                                 suggestion="'{도구}를 활용하여 생성함(또는 수정 보완함). YYYY. M. D.' 꼴로")]
        place = ""
        if ctx.source_para is not None and ctx.ai_marker_para is not None and ctx.ai_marker_para < ctx.source_para:
            place = " (출처 줄보다 위에 있음 — 양식은 출처 줄 다음, 캡션 앞)"
        return [CheckOutcome("⑦AI 표기", TRI if place else O,
                             f"{marker.tool}를 활용하여 {marker.action}함 {marker.date} — 서약서 결과물 현황과 대조 필요(C단계){place}")]
    # 양식에 맞지 않는 AI 언급: 출처 줄 안에 섞였거나, 캡션 근처에 '활용하여' 꼴이 깨진 줄
    if item.source is not None and AI_MARK.search(item.source.text) and item.source.kind != "집필진 제작":
        return [CheckOutcome("⑦AI 표기", X, f"출처 줄 안에 AI 활용이 섞여 있음: 「{item.source.text[:60]}」 — AI 활용 줄을 따로 적어야 함",
                             suggestion="출처 줄 다음 줄에 '{도구}를 활용하여 생성함. YYYY. M. D.'")]
    nearby = [ctx.source_line or "", ctx.caption]          # 양식상 AI 활용 줄이 올 자리(출처 줄~캡션)만 본다
    if any(LOOSE.search(t or "") for t in nearby):
        return [CheckOutcome("⑦AI 표기", TRI, "AI 활용으로 보이는 문구가 있으나 표기 양식으로 읽히지 않음 — 확인")]
    return [CheckOutcome("⑦AI 표기", NA)]
