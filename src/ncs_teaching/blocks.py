"""본문에서 학습별 '교수·학습 방법' 블록을 잘라 교수 방법·학습 방법 항목 문장을 모은다.

실데이터 구조:
    학습 N                         ← 학습 머리(이 블록이 속한 학습)
    …
    교수·학습 방법                 ← HEAD (⋅ · ･ 등 가운뎃점 변형 허용)
    교수 방법                      ← 소제목
    • … 설명한다.                  ← 항목(글머리 문단) ×N
    학습 방법                      ← 소제목
    • … 숙지한다.                  ← 항목 ×N
    평가 / 학습 N+1                ← 블록 끝
학습 번호: F02 양식은 학습마다 교수·학습 방법이 한 번씩 나오므로 블록의 순번을 학습 번호로 쓴다. 본문의 '학습 N' 줄은
내비게이터(모든 학습명 나열)에도 나와 믿기 어렵고, 참고용으로 마지막에 본 번호를 'lesson_line'에 남긴다.
항목으로 세는 문단: 글머리표가 텍스트에 있거나(•) 한글 자동 글머리(Document.numbers)가 달렸거나 스타일 이름에 '불릿'이 있는 것.
표 안·본문 밖(메모) 문단과 에디터 메모 줄(★▶※, '要')은 제외한다. 글머리 없는 바탕글은 세지 않되 '기타 문단'으로 남긴다.
"""

import re

HEAD = re.compile(r"^교수\s*\W{0,3}\s*학습\s*방법$")
TEACH = re.compile(r"^교수\s*방법$")
LEARN = re.compile(r"^학습\s*방법$")
LESSON = re.compile(r"^학습\s*(\d+)(?:\s*[.．]?\s*(\S.*))?$")
BLOCK_END = re.compile(r"^평\s*가$")
BULLET_TEXT = re.compile(r"^[•·▪ㆍ‧◦○\-–]\s*")
MEMO = re.compile(r"^[★▶※]|要")

SUBHEADS = (("교수", TEACH), ("학습", LEARN))


def split_teaching_blocks(paragraphs: list[str], *, styles: list[str] | None = None, numbers: list[str | None] | None = None,
                          table_paragraphs=None, aside_paragraphs=None) -> list[dict]:
    """→ [{'block_id', 'lesson'(순번), 'lesson_line'(본문 '학습 N' 줄에서 본 번호), 'head_idx',
           '교수': [{'idx','text'}], '학습': [...], '소제목 누락': [...], '기타 문단': [...]}]"""
    blocks, lesson, current, part = [], None, None, None
    table_paragraphs = table_paragraphs or frozenset()
    aside_paragraphs = aside_paragraphs or frozenset()

    def is_item(i: int, text: str) -> bool:
        if BULLET_TEXT.match(text):
            return True
        if numbers is not None and i < len(numbers) and numbers[i]:
            return True
        return bool(styles) and i < len(styles) and "불릿" in (styles[i] or "")

    for i, raw in enumerate(paragraphs):
        text = (raw or "").strip()
        if not text:
            continue
        if (m := LESSON.match(text)) and i not in table_paragraphs:
            # '학습 N' 줄: 블록이 열려 있으면 닫는다(다음 학습 시작). 번호는 참고로만 기억한다
            if current is not None:
                blocks.append(current)
                current, part = None, None
            lesson = int(m.group(1))
            continue
        if HEAD.match(text):
            if current is not None:
                blocks.append(current)
            ordinal = len(blocks) + 1
            current = {"block_id": f"학습 {ordinal} 교수·학습 방법", "lesson": ordinal, "lesson_line": lesson, "head_idx": i,
                       "교수": [], "학습": [], "소제목 누락": [], "기타 문단": []}
            part = None
            continue
        if current is None:
            continue
        if BLOCK_END.match(text):
            blocks.append(current)
            current, part = None, None
            continue
        if i in table_paragraphs or i in aside_paragraphs or MEMO.search(text):
            continue
        matched = next((name for name, pattern in SUBHEADS if pattern.match(text)), None)
        if matched:
            part = matched
            continue
        if part is None:
            continue
        if is_item(i, text):
            current[part].append({"idx": i, "text": text})
        else:
            current["기타 문단"].append({"idx": i, "part": part, "text": text})
    if current is not None:
        blocks.append(current)
    for block in blocks:
        block["소제목 누락"] = [name for name, _ in SUBHEADS if not block[name] and not _subhead_seen(block, name)]
    return blocks


def _subhead_seen(block: dict, name: str) -> bool:
    """소제목은 있었는데 항목이 0개인 경우와 소제목 자체가 없는 경우를 구분하지 않는다 — 둘 다 '없음'으로 본다."""
    return False
