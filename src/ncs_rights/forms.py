"""제출 서류 읽기 — 작성된 한글 양식(hwp·hwpx)의 표에서 행을 꺼낸다. 판정은 하지 않는다.

계약서 한 파일에 붙임이 여러 개 들어 있으므로(원고 집필 계약서 = 붙임 2·3·4), 파일 단위가 아니라 표 단위로 본다:
문서의 표를 모두 훑어 머리 칸의 글로 어떤 양식인지 알아낸다.

  수록 현황 목록(F07 붙임 2)   머리 '시각적 자료 제목' + '저작물 제작 방식'. 제작 방식 칸의 ✓ 위치로 방식을 읽는다
  제작 목록(F06 붙임 1)        머리 '저작물명' + '자료 유형'
  이용허락 동의서(F07 붙임 3)  머리 '저작물 제목' + '출처'
  AI 결과물 현황(F09 붙임)     머리 '결과물 명' + '활용 AI'
열 위치는 숫자로 박아 두지 않고 머리 칸의 글에서 찾는다 — 제출본에서 열을 더하거나 폭을 바꿔도 읽히게.
양도 동의서·초상권 동의서·서약서 본문은 표가 아니라 서명 문서라 여기서 읽지 않는다(제출 여부는 화면에서 받는다).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ncs_core.figures import parse_label

MARKS = set("✓✔√vVoO○●◯◎■☑✅")
PLACEHOLDER = re.compile(r"O{3,}|○{3,}|0{4,}")        # 양식의 자리표시('그림 OOOO', 'p.00'은 제외)
# 수록 현황 목록의 제작 방식 묶음: 머리 글에 든 낱말 → 방식 코드(이미지 저작권 DB의 분류 체계와 같은 코드 + ai)
METHOD_GROUPS = (("직접제작", "author_made"), ("제작의뢰", "commissioned"), ("공공", "public_license"),
                 ("포괄", "blanket_license"), ("기개발", "prior_module"), ("AI", "ai"))
METHOD_NAMES = {"author_made": "집필자 직접제작", "commissioned": "외부 제작의뢰", "public_license": "공공누리·공유마당",
                "blanket_license": "포괄적 이용허락", "prior_module": "기개발 학습모듈", "ai": "AI 활용"}


def squash(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def title_key(text: str) -> str:
    """제목 대조용 열쇠 — 띄어쓰기·기호 차이는 같은 것으로 본다."""
    return re.sub(r"[\W_]+", "", str(text or "")).lower()


@dataclass
class Forms:
    """읽어 낸 제출 서류. 각 목록의 행은 dict, sources는 {양식 이름: [그 양식이 나온 파일 이름]}."""
    inclusion: list[dict] = field(default_factory=list)      # [{'module', 'rows': [{'no', 'label', 'title', 'raw', 'methods', 'subs'}], 'file'}]
    production: list[dict] = field(default_factory=list)     # [{'label', 'title', 'raw', 'type', 'file'}]
    license: list[dict] = field(default_factory=list)        # [{'title', 'source', 'module', 'file'}]
    ai_results: list[dict] = field(default_factory=list)     # [{'name', 'label', 'title', 'page', 'tool', 'note', 'file'}]
    sources: dict[str, list[str]] = field(default_factory=dict)


def _grid(table: dict) -> dict[tuple[int, int], str]:
    return {key: str(value or "").strip() for key, value in table["cells"].items()}


def _find(grid: dict, *words: str) -> tuple[int, int] | None:
    """글(공백 무시)에 words가 모두 든 첫 칸의 (행, 열)."""
    for key in sorted(grid):
        text = squash(grid[key])
        if all(word in text for word in words):
            return key
    return None


def _marked(text: str) -> bool:
    text = squash(text)
    return bool(text) and len(text) <= 2 and any(ch in MARKS for ch in text)


# 괄호 없이 적은 그림 번호. 뒤 번호는 줄표에 바로 붙은 숫자이거나, 띄어 썼다면 그 뒤가 띄어쓰기·문장부호·끝일 때만 번호로 본다 —
# 뒤 번호를 비운 '그림 2- 6LoWPAN 프로토콜 스택'의 6은 제목이다
BARE_LABEL = re.compile(r"^\s*그림\s*(\d+)\s*[-–—－‐](?:(\d+)|\s+(\d+)(?=\s|$|[.:：]))?\s*[.:：]?\s*")


def _figure(raw: str) -> dict:
    """'[그림 1-1] NCS학습모듈 개념도' → 번호와 제목. 괄호 없이 '그림 1-1 개념도'로 적은 것도 읽는다. 번호가 없으면 제목만."""
    raw = raw.strip()
    found = parse_label(raw)
    if found is None and (bare := BARE_LABEL.match(raw)) is not None:
        minor = bare.group(2) or bare.group(3)
        found = (int(bare.group(1)), int(minor) if minor else None, raw[bare.end():].strip())
    if found is None:
        return {"label": "", "title": raw, "raw": raw}
    major, minor, title = found
    return {"label": f"그림 {major}-{minor if minor is not None else ''}", "title": title, "raw": raw}


def read_inclusion(table: dict) -> dict | None:
    """수록 현황 목록 표 → {'module', 'rows'}. 그 양식이 아니면 None."""
    grid = _grid(table)
    title_at, group_at = _find(grid, "시각적자료제목"), _find(grid, "직접제작")
    if title_at is None or group_at is None or _find(grid, "제작방식") is None:
        return None
    group_row, sub_row = group_at[0], group_at[0] + 1
    groups = {}                                           # 묶음이 시작하는 열 → 방식 코드
    for (r, c), text in grid.items():
        if r == group_row:
            code = next((code for word, code in METHOD_GROUPS if word in squash(text)), None)
            if code:
                groups[c] = code
    first = min(groups)

    def method_of(col: int) -> tuple[str, str] | None:
        if col < first:
            return None
        start = max(c for c in groups if c <= col)
        return groups[start], squash(grid.get((sub_row, col), ""))

    module = ""
    module_at = _find(grid, "NCS학습모듈명")
    if module_at is not None:
        module = re.sub(r"^.*?NCS\s*학습모듈명\s*[:：]?\s*", "", grid[module_at]).strip()
    rows = []
    for r in sorted({key[0] for key in grid if key[0] > sub_row}):
        raw = grid.get((r, title_at[1]), "")
        if not raw or PLACEHOLDER.search(raw):
            continue
        marked = [method_of(c) for (rr, c), text in sorted(grid.items()) if rr == r and _marked(text)]
        marked = [item for item in marked if item is not None]
        rows.append({**_figure(raw), "no": grid.get((r, title_at[1] - 1), "") if title_at[1] else "",
                     "methods": list(dict.fromkeys(code for code, _ in marked)),
                     "subs": {code: sub for code, sub in marked if sub}})
    return {"module": module, "rows": rows}


def read_production(table: dict) -> list[dict] | None:
    """사진·삽화 제작 목록 표 → [{'label', 'title', 'type'}]."""
    grid = _grid(table)
    name_at = _find(grid, "저작물명")
    if name_at is None or _find(grid, "자료유형") is None:
        return None
    types = {c: squash(text) for (r, c), text in grid.items()
             if name_at[0] <= r <= name_at[0] + 1 and squash(text) in ("사진", "삽화")}
    rows = []
    for r in sorted({key[0] for key in grid if key[0] > name_at[0]}):
        raw = grid.get((r, name_at[1]), "")
        if not raw or squash(raw) in ("사진", "삽화") or squash(raw).startswith("합계") or PLACEHOLDER.search(raw):
            continue
        kind = next((types[c] for (rr, c), text in sorted(grid.items()) if rr == r and c in types and _marked(text)), "")
        rows.append({**_figure(raw), "type": kind})
    return rows


def read_license(table: dict) -> list[dict] | None:
    """지식재산권 이용허락 동의서의 저작물 표 → [{'title', 'source', 'module'}]."""
    grid = _grid(table)
    title_at, source_at = _find(grid, "저작물제목"), _find(grid, "출처")
    if title_at is None or source_at is None or title_at[0] != source_at[0]:
        return None
    module_at = _find(grid, "활용", "학습모듈명")
    rows = []
    for r in sorted({key[0] for key in grid if key[0] > title_at[0]}):
        raw = grid.get((r, title_at[1]), "")
        if not raw or PLACEHOLDER.search(raw):
            continue
        rows.append({**_figure(raw), "source": grid.get((r, source_at[1]), ""),
                     "module": grid.get((r, module_at[1]), "") if module_at else ""})
    return rows


def read_ai_results(table: dict) -> list[dict] | None:
    """생성형 AI 결과물 현황 표 → [{'name', 'label', 'title', 'page', 'tool', 'note'}]. 양식의 예시 행('그림 OOOO')은 뺀다."""
    grid = _grid(table)
    name_at, tool_at = _find(grid, "결과물명"), _find(grid, "활용AI")
    if name_at is None or tool_at is None:
        return None
    page_at, note_at = _find(grid, "쪽수"), _find(grid, "비고")
    rows = []
    for r in sorted({key[0] for key in grid if key[0] > name_at[0]}):
        raw = grid.get((r, name_at[1]), "")
        if not raw or PLACEHOLDER.search(raw):
            continue
        figure = _figure(raw)
        rows.append({"name": raw, "label": figure["label"], "title": figure["title"] or raw,
                     "page": grid.get((r, page_at[1]), "") if page_at else "",
                     "tool": grid.get((r, tool_at[1]), ""), "note": grid.get((r, note_at[1]), "") if note_at else ""})
    return rows


FORM_NAMES = {"inclusion": "사진·삽화 수록 현황 목록", "production": "사진·삽화 제작 목록",
              "license": "지식재산권 이용허락 동의서", "ai_results": "생성형 AI 결과물 현황"}


def read_forms(documents: list[tuple[str, object]]) -> Forms:
    """[(파일 이름, Document)] → Forms. 한 파일에 여러 양식이 있어도, 같은 양식이 여러 파일에 있어도 모두 모은다."""
    forms = Forms()

    def seen(kind: str, name: str):
        names = forms.sources.setdefault(FORM_NAMES[kind], [])
        if name not in names:
            names.append(name)

    for name, document in documents:
        for table in document.tables:
            if (found := read_inclusion(table)) is not None:
                forms.inclusion.append({**found, "file": name})
                seen("inclusion", name)
            elif (rows := read_production(table)) is not None:
                forms.production += [{**row, "file": name} for row in rows]
                seen("production", name)
            elif (rows := read_ai_results(table)) is not None:
                forms.ai_results += [{**row, "file": name} for row in rows]
                seen("ai_results", name)
            elif (rows := read_license(table)) is not None:
                forms.license += [{**row, "file": name} for row in rows]
                seen("license", name)
    return forms
