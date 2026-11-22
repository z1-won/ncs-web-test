"""F02 필요지식 ⑧: 그림·표 출처 표기 — 존재(그림 필수, 표 선택) · '출처:' 머리말 · F14 템플릿 골격 · 마침표 구분."""

import re

from ncs_core import NA, O, TRI, X, visible
from ncs_core.source_line import CAPTION_START, OLD_AGENCY, SRC_HEAD, find_source_line, source_check  # noqa: F401 — source_check는 공개 이름 유지

from .common import row


def check_sources(body_raw: list[str], body_section: int, caps: list[dict], table_paragraphs: set[int] | None, *,
                  lookback: int, lookahead: int, lesson_spans=None) -> list[dict]:
    """caps: figtab.collect_labels 의 캡션 목록. 그림: 캡션 바로 위 '출처' 줄. 표: 표 아래 첫 '출처' 줄(선택).

    표의 출처 줄은 표(틀) 안에 있어도 인정한다 — 캡션 자체가 틀(표) 안에 있는 양식이 흔하다. 단 그 줄 바로 아래
    lookback 줄 안에 그림 캡션이 오면 그 그림의 출처이므로 표의 것으로 세지 않는다.
    lesson_spans: [(학습, flat 시작, 끝)] — 확인서 비고용 위치('학습 N')에 쓴다.
    """
    rows, used = [], set()
    lesson_of = (lambda k: next((no for no, a, b in lesson_spans if a <= k < b), None)) if lesson_spans else (lambda k: None)
    is_figure_caption = lambda i: bool(body_raw[i]) and bool(re.match(r"^\[\s*그림", body_raw[i]))

    def figure_source_below(i: int) -> bool:
        return any(is_figure_caption(j) for j in range(i + 1, min(i + 1 + lookback, len(body_raw))))

    for cap in caps:
        if cap["sec"] != body_section:
            continue
        p, kind = cap["para"], cap["kind"]
        lesson = lesson_of(cap["k"])
        where = f"학습 {lesson}" if lesson else ""
        src_i = None
        if kind == "그림":
            src_i = find_source_line(body_raw, p, lookback=lookback)
        else:
            for i in range(p + 1, min(p + 1 + lookahead, len(body_raw))):
                if body_raw[i] and CAPTION_START.match(body_raw[i]):
                    break
                if body_raw[i] and SRC_HEAD.match(body_raw[i]):
                    if figure_source_below(i):
                        break  # 다음 그림의 출처 줄 — 이 표의 출처는 없음
                    src_i = i
                    break
        region = f"section1 > {cap['label']}"
        checks, notes = {}, {}
        if src_i is None:
            checks["출처 줄 존재"] = X if kind == "그림" else NA
            notes["출처 줄 존재"] = (
                '그림 바로 위에 출처 줄이 없음 — 집필진 제작도 "출처: 집필진 제작(연도)" 필수' if kind == "그림"
                else "표 아래 출처 없음 — 직접 작성한 표면 생략 가능(인용이면 필수)"
            )
            rows.append(row("⑧", region, cap["text"], checks, notes, "출처: 집필진 제작(연도) 또는 인용 문헌 형식으로 추가" if kind == "그림" else None, 위치=where))
            continue
        used.add(src_i)
        checks["출처 줄 존재"] = O
        if kind == "그림" and src_i != p - 1:
            notes["출처 줄 위치"] = f"출처 줄(p{src_i})과 캡션(p{p}) 사이에 다른 문단이 있음"
        value, note = source_check(body_raw[src_i])
        checks["출처 형식 골격"] = value
        if value == O:
            notes["템플릿"] = note
        else:
            notes["출처 형식 골격"] = note
        if OLD_AGENCY.search(body_raw[src_i]):
            checks["기관명"], notes["기관명"] = TRI, "'한국직업능력개발원' → 현재 명칭 '한국직업능력연구원'(F14) 인지 확인"
        rows.append(row("⑧", region, visible(body_raw[src_i]), checks, notes,
                        "F14 출처 형식(저자(연도). 제목. 발행처. p.00. / 집필진 제작(연도) 등)으로 수정" if value != O else None, 캡션=cap["text"], 위치=where))
    for i, line in enumerate(body_raw):  # 캡션과 짝이 없는 출처 줄
        if line and SRC_HEAD.match(line) and i not in used and not (table_paragraphs is not None and i in table_paragraphs):
            rows.append(row("⑧", f"section1 > p{i}", visible(line), {"캡션과 연결": TRI}, {"캡션과 연결": "이 출처 줄 앞뒤에 그림·표 캡션이 없음 — 캡션 누락 또는 떨어진 출처"}, 위치=""))
    return rows
