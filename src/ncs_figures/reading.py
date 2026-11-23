"""그림 판독(009 태깅·005 브리프)과 캡션 일치(005 ③) — 맥락은 코드가 모으고, 모델은 그림에 보이는 것만 답한다.

그림 한 장에 호출 한 번(fig_read): 판독과 캡션 판정을 같이 받는다. read_figure·judge_caption은 같은 요청이라
둘째는 디스크 캐시에서 읽는다(그림을 두 번 보내지 않음). 둘 다 필요하면 read_and_judge.

맥락(캡션·본문 참조·앞뒤 문단·표 칸·위치)은 ncs_core.figure_context가 원고 구조에서 읽은 것을 그대로 넣는다.
답은 코드가 검증한다: 유형이 정해진 목록 안인가, 설명이 비었거나 캡션을 베꼈는가, 캡션 판정의 근거에 인용한 그림 속 글자가
'읽은 글자'에 있는가(없으면 지어낸 근거로 보고 그 답을 버림). 모델 결과는 후보일 뿐이다(점검 값은 최대 △).
"""

from __future__ import annotations

import re

from .models import FigureItem
from .prompts import build
from .vision import VisionError, VisionModel, png_for_model

TYPES = ("사진", "삽화", "도표", "그래프", "화면 캡처", "기타")
READ_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"유형": {"type": "string", "enum": list(TYPES)}, "설명": {"type": "string"},
                   "그림 속 글자": {"type": "array", "items": {"type": "string"}},
                   "키워드": {"type": "array", "items": {"type": "string"}},
                   "맥락 요약": {"type": "string"}, "확신도": {"type": "number"}},
    "required": ["유형", "설명", "그림 속 글자", "키워드", "맥락 요약", "확신도"],
}
CAPTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"판정": {"type": "string", "enum": ["match", "mismatch", "uncertain"]}, "근거": {"type": "string"},
                   "읽은 글자": {"type": "array", "items": {"type": "string"}}},
    "required": ["판정", "근거", "읽은 글자"],
}
BOTH_SCHEMA = {"type": "object", "additionalProperties": False,
               "properties": {"판독": READ_SCHEMA, "캡션": CAPTION_SCHEMA}, "required": ["판독", "캡션"]}
QUOTED = re.compile(r"[\"'“”‘’「『]([^\"'“”‘’」』]{2,40})[\"'“”‘’」』]")
CLIP = 300


def _join(lines, limit=CLIP) -> str:
    text = " / ".join(t for t in lines if t)
    return text if len(text) <= limit else text[:limit] + "…"


def context_values(item: FigureItem, module_name: str = "") -> dict[str, str]:
    ctx = item.ctx
    return {"모듈명": module_name, "위치": ctx.region_path, "캡션": ctx.caption,
            "참조": _join(ctx.references), "앞": _join(ctx.before), "뒤": _join(ctx.after),
            "표": _join(ctx.table_context) if ctx.in_table else ""}


def _image(item: FigureItem) -> bytes:
    if not item.ctx.data:
        raise VisionError("그림 파일이 없음")
    try:
        return png_for_model(item.ctx.data)
    except Exception as error:  # noqa: BLE001
        raise VisionError(f"그림을 읽지 못함: {error}") from None


def _transfer_block(item: FigureItem) -> str:
    return "" if item.transfer == "허용" else f"외부 전송 금지 그림({item.transfer_reason})"


def _not_sent(error: VisionError) -> dict:
    return {"status": "미실행" if "미승인" in str(error) or "로컬 전용" in str(error) or "KEY" in str(error) else "실패",
            "reason": str(error)}


def _ask(item: FigureItem, model: VisionModel, module_name: str):
    system, text = build("fig_read", context_values(item, module_name))
    return model.ask(task="fig_read", system=system, text=text, image_png=_image(item), schema=BOTH_SCHEMA)


def _reading(item: FigureItem, answer) -> dict:
    data, problems = answer.data.get("판독") or {}, []
    if data.get("유형") not in TYPES:
        return {"status": "실패", "reason": f"유형이 목록 밖: {data.get('유형')}", "model": answer.model}
    description = (data.get("설명") or "").strip()
    if not description:
        problems.append("설명 없음")
    elif item.ctx.caption and re.sub(r"\s+", "", description) == re.sub(r"\s+", "", item.ctx.caption):
        problems.append("설명이 캡션을 그대로 옮김")
    if not data.get("키워드"):
        problems.append("키워드 없음")
    return {"status": "완료", **{k: data.get(k) for k in READ_SCHEMA["properties"]},
            "model": answer.model, "cached": answer.cached, "usage": answer.usage, "problems": problems}


def _caption(item: FigureItem, answer, cached: bool) -> dict:
    data = answer.data.get("캡션") or {}
    verdict = data.get("판정")
    if verdict not in ("match", "mismatch", "uncertain"):
        return {"status": "실패", "reason": f"판정이 목록 밖: {verdict}", "model": answer.model}
    read = " ".join(data.get("읽은 글자") or [])
    squash = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    invented = [q for q in QUOTED.findall(data.get("근거") or "") if squash(q) not in squash(read) and squash(q) not in squash(item.ctx.caption)]
    check = "통과" if not invented else f"근거에 인용한 글자가 '읽은 글자'에 없음: {', '.join(invented[:3])}"
    return {"status": "완료", "판정": verdict, "근거": data.get("근거", ""), "읽은 글자": data.get("읽은 글자") or [],
            "검증": check, "model": answer.model, "cached": cached, "usage": {} if cached else answer.usage}


def read_and_judge(item: FigureItem, model: VisionModel, *, module_name: str = "") -> tuple[dict, dict]:
    """호출 한 번 → (판독, 캡션 판정). 캡션 없는 그림의 캡션 판정은 '미실행'. 사용량은 판독 쪽에만 센다."""
    blocked = _transfer_block(item)
    if blocked:
        skipped = {"status": "미실행", "reason": blocked}
        return skipped, dict(skipped)
    try:
        answer = _ask(item, model, module_name)
    except VisionError as error:
        failed = _not_sent(error)
        return failed, dict(failed)
    caption = _caption(item, answer, cached=True) if item.ctx.caption else {"status": "미실행", "reason": "캡션 없는 그림"}
    return _reading(item, answer), caption


def read_figure(item: FigureItem, model: VisionModel, *, module_name: str = "") -> dict:
    """→ {'status': 완료|미실행|실패, 'reason', '유형', '설명', '그림 속 글자', '키워드', '맥락 요약', '확신도', 'model', 'cached', 'usage', 'problems'}"""
    blocked = _transfer_block(item)
    if blocked:
        return {"status": "미실행", "reason": blocked}
    try:
        return _reading(item, _ask(item, model, module_name))
    except VisionError as error:
        return _not_sent(error)


def judge_caption(item: FigureItem, model: VisionModel, *, module_name: str = "") -> dict:
    """→ {'status', '판정', '근거', '읽은 글자', '검증', 'model', 'cached', 'usage'}. 캡션 없는 그림은 부르지 않는다."""
    blocked = _transfer_block(item)
    if blocked:
        return {"status": "미실행", "reason": blocked}
    try:
        answer = _ask(item, model, module_name)
    except VisionError as error:
        return _not_sent(error)
    return _caption(item, answer, cached=answer.cached)


class RecordedCaptions:
    """이미 받은 ③ 캡션 판정을 다시 쓰는 대역(Resources.asker 자리). 새로 부르지 않는다 — 웹의 그림 판독 결과(read.json)를
    005 검수표 위험도에 넣을 때 쓴다. 판정이 없는 그림은 ③ 미실행 → 위험도 '판정 안 함'."""

    def __init__(self, judged: dict[str, dict], model: str = "", missing: str = "그림 판독을 아직 하지 않음"):
        self.judged = judged
        self.name = model or "판독 결과"
        self.missing = missing

    def recorded(self, item) -> dict:
        result = self.judged.get(item.image_id or "")
        if not result:
            return {"status": "미실행", "reason": self.missing}
        return {**result, "cached": True, "usage": {}}

    def ask(self, **_):
        raise VisionError("RecordedCaptions는 새로 묻지 않음")
