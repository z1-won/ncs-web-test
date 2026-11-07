"""본문을 '수행 내용' 블록으로 나눈다. 규칙 ①②③④는 블록만 받는다.

양식(F14 p.4~8): 학습 내용 N-M 아래에 [수행 내용 (n)] 머리(표) → 제목 → 재료·자료 → 기기(장비·공구) →
안전·유의 사항 → 수행 순서(네모 번호 󰊱 제목 + 하위 번호) → (수행 tip 상자) 가 반복된다.
앵커는 텍스트 패턴을 우선하고 스타일 이름을 보조로 쓴다(hwp에는 스타일이 없다).
"""

import re

HEAD = re.compile(r"^수행\s*내용(?:\s*(\d+))?$")
UNIT = re.compile(r"^(\d+)\s*-\s*(\d+)\s*\.\s*(.*)$")  # 1-1. 명 (명이 다음 문단일 수 있음)
SUBHEAD = {
    "재료": re.compile(r"^재\s*료"),
    "기기": re.compile(r"^기\s*기"),
    "안전": re.compile(r"^안\s*전"),
    "수행순서": re.compile(r"^수\s*행\s*순\s*서$"),
}
BLOCK_END = re.compile(r"^(교수\s*\W{0,3}\s*학습\s*방법|평\s*가)$")
# 네모 번호 글자: 한글 기호 글꼴의 사용자 영역 U+F02B1~(󰊱 󰊲 …). 스타일이 없을 때 첫 글자로 수준 1을 추정한다
BOX_NUMBER = re.compile(r"^[\U000F02B0-\U000F02CF]")
BULLET = re.compile(r"^[•·ㆍ‧◦○\-]\s*")
# hwp 본문(UTF-16)은 코어가 2바이트씩 chr()로 읽어, 보조 평면 글자가 서로게이트 두 개(U+DB80 U+DEB1)로 갈라져 온다
SURROGATE_PAIR = re.compile("[\ud800-\udbff][\udc00-\udfff]")


def join_surrogates(text: str) -> str:
    """갈라진 서로게이트 쌍을 원래 글자 하나로 합친다(U+DB80 U+DEB1 → U+F02B1). 짝 없는 서로게이트는 그대로 둔다."""
    return SURROGATE_PAIR.sub(lambda m: m.group().encode("utf-16-le", "surrogatepass").decode("utf-16-le"), text or "")


def _level1(text: str, style: str) -> bool:
    """수행 순서의 네모 번호(수준 1) 제목 줄인가. 스타일 '󰊱제목' 우선, 없으면 첫 글자."""
    if style:
        return style.startswith("\U000F02B1") and "제목" in style
    return bool(BOX_NUMBER.match(text))


def _table_column_head(i: int, n: int, candidates: list[int], texts: list[str], in_table, aside) -> bool:
    """표 안의 '수행 내용'이 블록 머리가 아니라 본문 표의 열 제목인가.

    SW제품기획 최종본 0408: 필요 지식 본문의 '게시자 | 구독자 | 수신자' 표 열 제목 '수행 내용'을 머리로 보아
    제목('게시자')·소제목 없는 가짜 블록이 생겨 수행 ①④가 X였다. 진짜 머리는 표(틀) 안에 있어도 뒤에
    재료·기기·안전·수행 순서 소제목이 따른다 → 표 안이면서 다음 후보 전까지 소제목이 하나도 없으면 열 제목으로 본다.
    """
    if i not in in_table:
        return False
    stop = candidates[n + 1] if n + 1 < len(candidates) else len(texts)
    for j in range(i + 1, stop):
        if j in aside or j in in_table:
            continue
        if BLOCK_END.match(texts[j]):
            break
        if any(p.match(texts[j]) and len(texts[j]) <= 20 for p in SUBHEAD.values()):
            return False
    return True


def split_perform_blocks(
    paragraphs: list[str],
    *,
    styles: list[str] | None = None,
    table_paragraphs: frozenset[int] | None = None,
    aside_paragraphs: frozenset[int] | None = None,
) -> list[dict]:
    """→ [{'block_id','lesson','unit','unit_title','perform_no','head','title','title_idx',
          '재료','기기','안전','수행순서'(각 [{'idx','text'[,'level1']}]), 'span':(start,end), '소제목 누락':[...]}]"""
    styles = styles or [""] * len(paragraphs)
    in_table = table_paragraphs or frozenset()
    aside = aside_paragraphs or frozenset()
    texts = [join_surrogates(t).strip() for t in paragraphs]

    candidates = [i for i, t in enumerate(texts) if HEAD.match(t) and i not in aside]
    heads = [i for n, i in enumerate(candidates) if not _table_column_head(i, n, candidates, texts, in_table, aside)]
    head_set = set(heads)
    blocks = []
    for n, head in enumerate(heads):
        # 블록 끝: 다음 수행 내용 머리 / 다음 N-M 머리 / 교수·학습 방법·평가 제목
        end = len(texts)
        for j in range(head + 1, len(texts)):
            if j in aside:
                continue
            if (HEAD.match(texts[j]) and j in head_set) or BLOCK_END.match(texts[j]):
                end = j
                break
            if UNIT.match(texts[j]) and len(texts[j]) < 60 and not re.search(r"\s\d+$", texts[j]):
                end = j
                break
        # 소속 학습 내용(N-M): 머리 앞에서 가장 가까운 N-M 머리. '1-1.'과 명칭이 두 문단으로 갈린 경우 포함
        unit, unit_title = None, ""
        for j in range(head - 1, -1, -1):
            if j in aside:
                continue
            m = UNIT.match(texts[j])
            if m and len(texts[j]) < 60 and not re.search(r"\s\d+$", texts[j]):
                unit = f"{m.group(1)}-{m.group(2)}"
                unit_title = m.group(3).strip() or next((texts[k] for k in range(j + 1, min(j + 3, head)) if texts[k]), "")
                break
        number = HEAD.match(texts[head]).group(1)
        # 제목: 머리 다음의 비어 있지 않은 문단('/' 같은 구분 글자는 건너뜀)
        title_idx, title = None, ""
        for j in range(head + 1, min(head + 6, end)):
            if j in aside or not texts[j] or re.fullmatch(r"[/／|│]+", texts[j]):
                continue
            title_idx, title = j, texts[j]
            break
        # 소제목 구간
        marks = []
        for j in range(head + 1, end):
            if j in aside or j in in_table:
                continue
            for key, pattern in SUBHEAD.items():
                if pattern.match(texts[j]) and len(texts[j]) <= 20:
                    marks.append((j, key))
                    break
        parts = {key: [] for key in SUBHEAD}
        for order, (j, key) in enumerate(marks):
            stop = marks[order + 1][0] if order + 1 < len(marks) else end
            for k in range(j + 1, stop):
                if k in aside or not texts[k]:
                    continue
                if key == "수행순서":
                    if k in in_table:  # 수행 tip·스크립트 상자, 표 본문은 문장 검사 대상이 아니다
                        continue
                    parts[key].append({"idx": k, "text": texts[k], "level1": _level1(texts[k], styles[k])})
                elif k not in in_table:
                    parts[key].append({"idx": k, "text": BULLET.sub("", texts[k])})
        blocks.append(
            {
                "block_id": f"학습 내용 {unit or '?'} > 수행 내용{(' ' + number) if number else ''}",
                "unit": unit,
                "unit_title": unit_title,
                "perform_no": int(number) if number else None,
                "head": head,
                "title_idx": title_idx,
                "title": title,
                "재료": parts["재료"],
                "기기": parts["기기"],
                "안전": parts["안전"],
                "수행순서": parts["수행순서"],
                "span": (head, end),
                "소제목 누락": [k for k in SUBHEAD if k not in {key for _, key in marks}],
            }
        )
    return blocks
