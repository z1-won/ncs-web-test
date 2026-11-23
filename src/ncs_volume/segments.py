"""최상위 문단(Block)을 학습모듈 구성(위치·차례·개요·학습·교수·학습 방법·평가·참고 자료·활용 서식·부록 …)으로 나눈다.

구성의 시작은 제목 글로 안다. 제목은 대개 표(배너) 안에 있어 표는 앞 두 칸의 글로 본다.
- 차례 면의 줄('참고 자료 63')은 쪽 번호가 붙어 있어 제목으로 보지 않고, 꼬리 구성(참고 자료·활용 서식·부록)의 목록만 읽어 둔다.
- 꼬리 구성의 제목이 글 없는 배너 그림뿐이면(실제 hwp 원고), 마지막 평가 뒤에서 쪽 맨 위에 놓인 '캡션 없는 그림'을 차례에 적힌 순서대로 다음 꼬리 구성의 시작으로 본다.
- 첫 제목 앞은 표지(산정 제외). 'NCS학습모듈의 이해'·개발 이력·판권(ISBN)도 제외.
판정은 하지 않는다. 구성을 하나도 찾지 못하면 pipeline이 '판단불가'로 알린다.
"""

from __future__ import annotations

import re

from .layout import Block

TAIL = ("참고 자료", "활용 서식", "부록")
OPTIONAL = ("활용 서식", "부록")      # 필수 집필 사항이 아니다(F11 매뉴얼 인쇄 20~21쪽) — 쓰지 않으면 차례에서도 지운다
_TOC_TAIL = re.compile(r"(참고자료|활용서식|부록)\d+")
_NOT_WORD = re.compile(r"[^0-9A-Za-z가-힣]")
_LESSON = re.compile(r"학습\s*(\d+)")


def norm(text: str) -> str:
    """한글·영문·숫자만 남긴다(띄어쓰기·가운뎃점·괄호·기호 글꼴 문자 제거)."""
    return _NOT_WORD.sub("", text or "")


def _tail_name(key: str) -> str | None:
    for name in TAIL:
        if key == norm(name) or (name == "부록" and re.fullmatch(r"부록\d*", key)):
            return name
    return None


def heading(block: Block, state: str) -> str | None:
    """이 문단이 시작하는 구성 이름(아니면 None). state는 지금까지의 구성."""
    key = norm(block.head)
    if not key or len(key) > 80:
        return None
    if key.startswith("NCS학습모듈의이해") or key == "학습모듈의이해":
        return "NCS학습모듈의 이해"
    if "개발이력" in key[:12] or (block.kind == "table" and "ISBN" in block.full):
        return "개발진(개발 이력·판권)"
    if state == "NCS학습모듈의 이해":
        # 'NCS학습모듈의 이해'는 '1. NCS학습모듈의 위치', '[NCS-학습모듈의 위치]' 예시, '학습2 평 가' 같은 양식 설명을 담는다.
        # 그 뒤에는 위치(새 쪽 맨 위) 또는 차례가 오므로 그 둘만 다음 구성의 시작으로 본다.
        if "학습모듈의위치" in key and len(key) <= 20 and block.page_top:
            return "NCS-학습모듈의 위치"
        return "차례" if key == "차례" else None
    if "학습모듈의위치" in key and len(key) <= 20:
        return "NCS-학습모듈의 위치"
    if key == "차례":
        return "차례"
    if key.endswith("학습모듈의개요") and len(key) <= 60:
        return "학습모듈의 개요"
    if key.endswith("교수학습방법") and len(key) <= 20:
        return "교수·학습 방법"
    if key.endswith("평가") and len(key) <= 10 and state in ("교수·학습 방법", "학습 — 필요 지식", "학습 — 수행 내용"):
        return "평가"
    if state.startswith("학습") or state in ("교수·학습 방법", "평가", "학습모듈의 개요"):
        if key.startswith("필요지식") and (block.kind == "table" or len(key) <= 6):
            return "학습 — 필요 지식"
        if key.startswith("수행내용") and (block.kind == "table" or len(key) <= 6):
            return "학습 — 수행 내용"
    # 내비게이터: 표 안에 '학습 N'이 둘 이상(학습 묶음), 또는 문단 글이 '학습 N' 하나뿐
    if state != "차례" and ((block.kind == "table" and len(set(_LESSON.findall(block.full))) >= 2 and key.startswith("학습"))
                           or re.fullmatch(r"학습\d+", key)):
        return "학습 — 필요 지식"
    if state != "차례" and len(key) <= 8:
        return _tail_name(key)
    return None


def assign(blocks: list[Block]) -> tuple[list[str], list[str]]:
    """(문단마다 구성 이름, 찾은 구성 이름 순서)."""
    state, out, found = "표지", [], []
    pending = list(TAIL)          # 차례에서 읽으면 그 목록으로 바꾼다
    toc_tail: list[str] = []
    for block in blocks:
        name = heading(block, state)
        if name is None and state == "차례":
            match = _TOC_TAIL.fullmatch(norm(block.head))
            if match:
                toc_tail.append(_tail_name(match.group(1)) or "")
        if (name is None and block.kind == "picture" and not block.has_caption and block.page_top
                and state in ("평가", "참고 자료", "활용 서식") and pending):
            name = pending[0]     # 글 없는 배너 그림으로 시작하는 꼬리 구성
        if name is not None:
            if state == "차례" and toc_tail:
                pending = [n for n in TAIL if n in toc_tail]
            if name in TAIL:
                pending = pending[pending.index(name) + 1:] if name in pending else pending
            state = name
            if name not in found:
                found.append(name)
        out.append(state)
    return out, found


def toc_tail(blocks: list[Block], names: list[str]) -> list[str]:
    """차례 면 줄('참고 자료 63')에서 읽은 꼬리 구성 이름(차례 순서). 읽지 못했으면 빈 목록."""
    out = []
    for block, name in zip(blocks, names):
        match = _TOC_TAIL.fullmatch(norm(block.head)) if name == "차례" else None
        if match and _tail_name(match.group(1)) not in out:
            out.append(_tail_name(match.group(1)))
    return out
