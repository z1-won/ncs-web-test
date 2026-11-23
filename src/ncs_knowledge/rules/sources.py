"""F02 필요지식 ⑧: 그림·표 출처 표기 — 존재(그림 필수, 표 선택) · '출처:' 머리말 · F14 템플릿 골격 · 마침표 구분.

그림의 생성형 AI 활용 표기(REQ-02-008, F08 AI 도구 사용 표기 예)도 여기서 본다. 그림 한 개의 순서는
    출처: 집필진 제작(2026)  →  ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.  →  [그림 1-1] 그림명
이고, AI 활용 줄이 있는 그림에만 체크 둘이 더 붙는다(없는 그림의 행은 그대로다 — AI를 썼는지는 원고만으로 알 수 없다).
  AI 활용 줄 형식     꼴과 순서가 맞으면 O. 일자가 없거나 달력에 없는 날, 출처 줄보다 위에 있으면 X(글자로 확정되는 형식 오류).
                      띄어쓰기·마침표가 표기 예와 다르거나 뒤에 다른 글이 붙으면 △, AI를 쓴 듯한 줄인데 활용 줄로 읽히지 않아도 △.
  AI 활용 방식 구분   '생성함'인데 출처 줄이 '집필진 제작(연도)'가 아니면 △(다른 자료를 고친 것이면 '수정 보완함' — 후보일 뿐 확정하지 않는다).
AI 활용 줄 읽기는 ncs_core.figures.parse_ai_mark(권리 증빙 점검, AI 활용 표기 넣기와 같은 읽기)를 쓴다.
"""

import re

from ncs_core import NA, O, TRI, X, visible
from ncs_core.figures import parse_ai_mark
from ncs_core.source_line import (  # noqa: F401 — source_check는 공개 이름 유지
    AI_LINE_EXAMPLE, CAPTION_START, OLD_AGENCY, SRC_HEAD, TEMPLATES, find_source_line, source_check)

from .common import row

# 출처 줄 읽기(SRC_HEAD·TEMPLATES·source_check·find_source_line)는 ncs_core.source_line이 유일한 원본이다. 여기에는 AI 활용 줄의 판정만 둔다.
# AI 도구 사용 표기 예(F08)의 AI 활용 줄 꼴 — 'ChatGPT를 활용하여 생성함. 2026. 7. 20.' 도구 이름의 마침표는 숫자 사이(판 번호)만.
# 코어의 AI_LINE은 느슨하게 읽는 정규식이고, 이것은 띄어쓰기·마침표까지 표기 예와 같은지 보는 꼴이다
AI_LINE_FORM = re.compile(r"^[^\s.。,](?:[^.。]|(?<=\d)\.(?=\d)){0,40}?[을를] 활용하여 (생성함|수정 보완함)\. \d{4}\. \d{1,2}\. \d{1,2}\.$")
AI_EXTRA = 12        # AI 활용 줄 뒤에 붙을 수 있는 글자 수 — 이보다 길면 본문 문장으로 본다(ncs_core.figures와 같은 값)
AI_HINT = re.compile(r"생성형\s*AI|AI\s*(?:로|으로|를)?\s*(?:생성|제작|수정|보정|활용)|GPT|Gemini|제미나이|미드저니|Midjourney|DALL")
AI_HINT_MAX = 60     # AI를 쓴 듯한 줄로 볼 길이 — 본문 문장은 빼기 위해
SENTENCE = re.compile(r"(다|요|까)\s*[.。?]\s*$")
AI_SUGGESTION = f"출처 줄 아래, 그림 번호 위에 {AI_LINE_EXAMPLE} 꼴로 적음(생성함 또는 수정 보완함, 활용 일자 포함)"


def _ai_mark(text: str):
    """문단이 AI 활용 줄이면 읽은 표기(ncs_core.figures.AiMark), 아니면 None. 본문 문장 속 '…를 활용하여 생성함'은 뺀다."""
    text = (text or "").strip()
    mark = parse_ai_mark(text)
    return mark if mark is not None and len(text) <= len(mark.text) + AI_EXTRA else None


def ai_checks(lines: list[tuple[int, str]], source_at: int | None, source_value: str | None, template: str | None) -> tuple[dict, dict]:
    """그림 캡션 위의 문단들(아래에서 위로: [(문단 번호, 글)])에서 AI 활용 줄을 찾아 (체크, 비고)를 만든다. 없으면 ({}, {}).

    source_at: 출처 줄의 문단 번호(없으면 None). source_value·template: 그 출처 줄의 형식 판정과 맞은 템플릿 이름.
    """
    found = next(((i, text.strip(), mark) for i, text in lines if (mark := _ai_mark(text)) is not None), None)
    if found is None:
        hint = next((text.strip() for i, text in lines if i != source_at and len(text.strip()) <= AI_HINT_MAX
                     and AI_HINT.search(text) and not SENTENCE.search(text)), None)
        if hint is None:
            return {}, {}
        return ({"AI 활용 줄 형식": TRI},
                {"AI 활용 줄 형식": f"원고 「{hint}」 — AI를 활용한 그림이면 {AI_LINE_EXAMPLE} 꼴의 AI 활용 줄인지 확인"})
    at, text, mark = found
    checks, notes = {}, {}
    if mark.on is None:
        checks["AI 활용 줄 형식"] = X
        notes["AI 활용 줄 형식"] = f"원고 「{text}」 — 활용 일자가 없거나 달력에 없는 날짜임"
    elif source_at is not None and at < source_at:
        checks["AI 활용 줄 형식"] = X
        notes["AI 활용 줄 형식"] = f"원고 「{text}」 — AI 활용 줄이 출처 줄 위에 있음(출처 줄 아래, 그림 번호 위에 적음)"
    elif not AI_LINE_FORM.match(text):
        checks["AI 활용 줄 형식"] = TRI
        notes["AI 활용 줄 형식"] = f"원고 「{text}」 — 띄어쓰기·마침표가 표기 예 {AI_LINE_EXAMPLE}와 다르거나 뒤에 다른 글이 있음. 확인 필요"
    else:
        checks["AI 활용 줄 형식"] = O
    if source_value == O:      # 출처 줄을 읽었을 때만 견준다
        if mark.mode == "generated" and template != TEMPLATES[0][0]:
            checks["AI 활용 방식 구분"] = TRI
            notes["AI 활용 방식 구분"] = (f"원고 「{text}」 — ‘생성함’인데 출처 줄이 집필진 제작(연도)가 아님. "
                                      "다른 자료를 AI로 고친 것이면 ‘수정 보완함’인지 확인")
        else:
            checks["AI 활용 방식 구분"] = O
    return checks, notes


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
        above = []      # 그림 캡션 위의 문단(아래에서 위로) — AI 활용 줄을 찾는다. 캡션과 한 문단에 붙은 AI 활용 줄도 본다
        if kind == "그림":
            before = body_raw[p].split("[", 1)[0] if body_raw[p] else ""
            above = [(p, before)] if before.strip() else []
            for i in range(p - 1, max(p - 2 - lookback, -1), -1):
                if is_figure_caption(i):
                    break
                if body_raw[i]:
                    above.append((i, body_raw[i]))
        if src_i is None:
            checks["출처 줄 존재"] = X if kind == "그림" else NA
            notes["출처 줄 존재"] = (
                '그림 바로 위에 출처 줄이 없음 — 집필진 제작도 "출처: 집필진 제작(연도)" 필수' if kind == "그림"
                else "표 아래 출처 없음 — 직접 작성한 표면 생략 가능(인용이면 필수)"
            )
            ai_check, ai_note = ai_checks(above, None, None, None)
            checks.update(ai_check)
            notes.update(ai_note)
            rows.append(row("⑧", region, cap["text"], checks, notes, "출처: 집필진 제작(연도) 또는 인용 문헌 형식으로 추가" if kind == "그림" else None, 위치=where))
            continue
        used.add(src_i)
        checks["출처 줄 존재"] = O
        value, note = source_check(body_raw[src_i])
        ai_check, ai_note = ai_checks(above, src_i, value, note if value == O else None)
        ai_at = next((i for i, text in above if _ai_mark(text) is not None), None)
        only_ai_between = ai_at is not None and all(j == ai_at or not body_raw[j] for j in range(src_i + 1, p))
        if kind == "그림" and src_i != p - 1 and not only_ai_between:      # 출처 줄과 캡션 사이의 AI 활용 줄은 제자리다
            notes["출처 줄 위치"] = f"출처 줄(p{src_i})과 캡션(p{p}) 사이에 다른 문단이 있음"
        checks["출처 형식 골격"] = value
        if value == O:
            notes["템플릿"] = note
        else:
            notes["출처 형식 골격"] = note
        checks.update(ai_check)
        notes.update(ai_note)
        if OLD_AGENCY.search(body_raw[src_i]):
            checks["기관명"], notes["기관명"] = TRI, "'한국직업능력개발원' → 현재 명칭 '한국직업능력연구원'(F14) 인지 확인"
        suggestions = [text for text in (
            "F14 출처 형식(저자(연도). 제목. 발행처. p.00. / 집필진 제작(연도) 등)으로 수정" if value != O else None,
            AI_SUGGESTION if any(mark != O for mark in ai_check.values()) else None) if text]
        rows.append(row("⑧", region, visible(body_raw[src_i]), checks, notes, " / ".join(suggestions) or None, 캡션=cap["text"], 위치=where))
    for i, line in enumerate(body_raw):  # 캡션과 짝이 없는 출처 줄
        if line and SRC_HEAD.match(line) and i not in used and not (table_paragraphs is not None and i in table_paragraphs):
            rows.append(row("⑧", f"section1 > p{i}", visible(line), {"캡션과 연결": TRI}, {"캡션과 연결": "이 출처 줄 앞뒤에 그림·표 캡션이 없음 — 캡션 누락 또는 떨어진 출처"}, 위치=""))
    return rows
