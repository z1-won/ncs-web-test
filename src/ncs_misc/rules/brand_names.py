"""기타 ③: 본문 텍스트 및 그림에 특정 상호, 상품명, 제품 모델명, 모델 번호, 특정 프로그램명, 인물 등이 노출되지는 않았는가.

체크리스트가 직접 금지하고 예시까지 든다("엑셀, 아래아 한글 → 스프레드시트 프로그램") → 본문에 나오면 X.
  - 사전(ncs_core.brands — 수행 내용 ②와 함께 씀)의 명확한 제품·서비스·회사명, ®·™ 표시 → X(일반 명칭 제안을 붙임)
  - 일반 낱말과 겹치는 이름(AMBIGUOUS: 한글·워드·윈도우·오피스·줌 …) → △(뜻이 제품명인지 사람 확인)
  - 제외: '출처:' 줄(F14가 스크린 숏 출처에 프로그램명을 쓰게 함, F08 AI 도구 표기), 참고 자료 구역(서지), 메모
  - 그림 속 노출(로고·상품·인물)은 볼 수 없다 → 그림이 있으면 '그림 N개 사람 확인' △를 함께 둔다
SW제품기획 최종본(사람 검수 통과)에도 본문 제품명이 많다(엑셀 14, Windows 11 …) — 체크리스트 문구를 따라 X로 둔다(결정 2026-11-05).
사전은 공식 목록이 아니다. 사전에 없는 이름은 잡지 못한다(LLM 후보).
"""

import re

from ncs_core import O, TRI, X, visible
from ncs_core.brands import find_brands
from ncs_core.pictures import picture_records
from .common import row

CHECK = "③ 본문 상호·상품명·프로그램명"
PICTURES = "③ 그림 속 노출(사람 확인)"
SRC = re.compile(r"^\s*출\s*처\s*[:：]")

COLOPHON = re.compile(r"^(?:NCS\s*학습모듈\s*)?개발\s*이력")  # 개발 이력·판권: 집필진·검토진 소속(회사명)을 적게 되어 있다


def _reference_range(context) -> tuple[int, int] | None:
    found = context.presence.get("참고 자료") or {}
    if not found.get("있음") or found.get("k") is None:
        return None
    return found["k"], found.get("end") or len(context.manuscript.sections[context.config.body_section])


def check_brand_names(context) -> list[dict]:
    manuscript, config = context.manuscript, context.config
    body = manuscript.sections[config.body_section]
    aside = manuscript.section_aside_paragraphs(config.body_section) or frozenset()
    refs = _reference_range(context)
    colophon = next((i for i, t in enumerate(body) if COLOPHON.match((t or "").strip())), len(body))
    rows, hard, soft = [], 0, 0
    for i, text in enumerate(body[:colophon]):
        text = text or ""
        if not text.strip() or i in aside or SRC.match(text) or (refs and refs[0] <= i <= refs[1]):
            continue
        found, unsure = find_brands(text)
        if found:
            hard += 1
            names = ", ".join(f"「{n}」→{g}" for n, g in found)
            rows.append(row("③", f"section1 > 문단 {i}", f"문단 {i}", visible(text.strip())[:120], {CHECK: X},
                            {CHECK: f"문단 {i} {names}: 「{visible(text.strip())[:50]}」"},
                            "특정 상호·상품명·프로그램명을 일반 명칭으로 바꿈(예: 엑셀 → 스프레드시트 프로그램)"))
            continue
        if unsure:
            soft += 1
            rows.append(row("③", f"section1 > 문단 {i}", f"문단 {i}", visible(text.strip())[:120], {CHECK: TRI},
                            {CHECK: f"문단 {i} " + " / ".join(f"「{n}」 {why} 사람 확인" for n, why in unsure)
                                    + f": 「{visible(text.strip())[:50]}」"},
                            "제품·프로그램명이면 일반 명칭으로 바꿈"))
    pictures = len(picture_records(manuscript)) if manuscript.format == "hwpx" else None
    if pictures is None or pictures:
        note = "hwp는 그림을 읽을 수 없음" if pictures is None else f"그림 {pictures}개"
        rows.append(row("③", "section1 > 그림", "", {"그림": pictures}, {PICTURES: TRI},
                        {PICTURES: f"{note} — 그림 속 상호·상품·로고·인물 노출은 사람 확인(블러·삭제 필요 여부)"}))
    if not hard and not soft:
        rows.append(row("③", "section1", "", None, {CHECK: O}, {CHECK: "본문에서 사전에 있는 상호·상품명·프로그램명을 찾지 못함"}))
    return rows
