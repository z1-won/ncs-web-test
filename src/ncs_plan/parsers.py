"""개발계획서(T01 양식)의 표를 읽는다 — 1~3쪽(기본 정보·NCS 변경 전후 대조표·총괄표·NCS-학습모듈의 위치)과 모듈 표(NCS 수정 금지 ⇰ NCS학습모듈).

판정은 하지 않는다. 셀은 Document.tables의 {(행, 열): 글} 사전이며 병합 셀은 왼쪽 위 칸에만 글이 있다.
라벨은 공백을 뺀 글로 찾는다(‘수 행 준 거’, ‘학 습 목 표’처럼 양식이 글자 사이를 띄운다).
"""

from __future__ import annotations

import re

from ncs_core.manuscript.patterns import PLAN_LESSON, PLAN_SUB
from ncs_core.manuscript.plan_table import ELEMENT_IN_CELL, GOAL_SPLIT

UNIT_CODE = re.compile(r"^\d{10}_\d{2}v\d+$")
LM_CODE = re.compile(r"^LM\d{10}_\d{2}v\d+$")
NUMBER_HEAD = re.compile(r"^\d{1,2}\.\s*")          # 위치 표의 '20. 정보통신'
FORM_MARK = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*")       # 양식 안내 번호가 값 칸에 남은 것: '① SW제품기획'
LESSON_CELL = re.compile(r"^(\d+)\.(?!\d)\s*(\S.*)$")   # 학습명 칸: '4. 기술 도입 평가하기' / '4.기술 도입 평가하기'(공백 누락도 읽는다; '4.1 …' 수행준거와는 구별)
SENTENCE_SPLIT = re.compile(r"\s*\n\s*|" + GOAL_SPLIT.pattern)  # 셀 안의 '1.1 … 1.2 …' 또는 줄바꿈


def squash(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "")


def _right_of(table: dict, r: int, c: int) -> str:
    """같은 행에서 오른쪽 첫 비어 있지 않은 칸."""
    cells = table["cells"]
    for col in range(c + 1, table["cols"]):
        value = (cells.get((r, col)) or "").strip()
        if value:
            return value
    return ""


def label_value(table: dict, label: str, *, prefix: bool = False) -> str | None:
    """라벨 칸(공백 무시, 정확히 또는 머리 일치)의 오른쪽 값. 라벨이 없으면 None."""
    target = squash(label)
    for (r, c), text in table["cells"].items():
        key = squash(text)
        if key == target or (prefix and key.startswith(target)):
            return _right_of(table, r, c)
    return None


MARKER_ONLY = re.compile(r"^\d+\.\d+\s*$")   # 셀 안에서 줄이 바뀌어 번호만 따로 떨어진 조각 '3.5'


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text or "") if s and s.strip() and not MARKER_ONLY.match(s.strip())]


# ── 1~3쪽 ──────────────────────────────────────────────────────────────────────

def _header_cols(table: dict, wanted: dict[str, tuple[str, ...]]) -> tuple[int, dict[str, int]] | None:
    """머리 행과 열 번호. wanted = {이름: (공백 없는 라벨 후보…)}. 모든 이름이 한 행에서 찾아지면 그 행."""
    cells = table["cells"]
    for r in range(table["rows"]):
        found: dict[str, int] = {}
        for c in range(table["cols"]):
            key = squash(cells.get((r, c)))
            for name, labels in wanted.items():
                if name not in found and key and any(key == lab or key.startswith(lab) for lab in labels):
                    found[name] = c
        if len(found) == len(wanted):
            return r, found
    return None


def read_basic(tables: list[dict]) -> dict:
    """기본 정보 — {'세분류명', '영문 세분류명', '신규/개선', '개발기관명'} (없는 항목은 None)."""
    out = {"세분류명": None, "영문 세분류명": None, "신규/개선": None, "개발기관명": None}
    for table in tables:
        if label_value(table, "(한글) 세분류명", prefix=True) is None:
            continue
        def value(label: str) -> str | None:
            text = FORM_MARK.sub("", label_value(table, label, prefix=True) or "").strip()
            return text or None

        out["세분류명"] = value("(한글) 세분류명")
        out["영문 세분류명"] = value("(영문) 세분류명")
        out["신규/개선"] = value("신규 / 개선")
        out["개발기관명"] = value("개발기관명")
        break
    return out


def read_change_table(tables: list[dict]) -> list[dict] | None:
    """NCS 변경 전·후 대조표 → [{'개선 전 코드','개선 전 명칭','개선 후 코드','개선 후 명칭','분석 결과'}]. 표가 없으면 None."""
    for table in tables:
        if not squash(table["cells"].get((0, 0))).startswith("①NCS개선전"):
            continue
        header = _header_cols(table, {"전코드": ("능력단위번호",), "전명": ("능력단위명",)})
        if header is None:
            return []
        head_row, _ = header
        cells, rows = table["cells"], []
        for r in range(head_row + 1, table["rows"]):
            values = [(cells.get((r, c)) or "").strip() for c in range(table["cols"])]
            if not any(values):
                continue
            rows.append({"행": r, "개선 전 코드": values[0], "개선 전 명칭": values[1] if len(values) > 1 else "",
                         "개선 후 코드": values[2] if len(values) > 2 else "", "개선 후 명칭": values[3] if len(values) > 3 else "",
                         "분석 결과": values[4] if len(values) > 4 else ""})
        return rows
    return None


def read_summary_table(tables: list[dict]) -> list[dict] | None:
    """개발계획 총괄표 → [{'코드','명칭','개선 유형','LM 코드','LM 명칭','집필진','검토진'}]. 표가 없으면 None."""
    for table in tables:
        # 기존 개선 양식: ① NCS | ② 개선 유형 | ③ NCS학습모듈 | ④ 집필진 | ⑤ 검토진 / 신규 개발 양식: ① NCS | ② NCS학습모듈 | ③ 집필진 | ④ 검토진
        header = _header_cols(table, {"코드": ("능력단위번호",), "명칭": ("능력단위명",), "LM코드": ("NCS학습모듈코드번호",), "LM명": ("NCS학습모듈명",)})
        if header is None:
            continue
        head_row, col = header
        labels = {squash(v): c for (r, c), v in table["cells"].items() if r < head_row}
        type_col = next((c for k, c in labels.items() if "개선유형" in k), None)
        writer_col = next((c for k, c in labels.items() if "담당집필진" in k), None)
        reviewer_col = next((c for k, c in labels.items() if "담당검토진" in k), None)
        cells, rows = table["cells"], []
        for r in range(head_row + 1, table["rows"]):
            code = (cells.get((r, col["코드"])) or "").strip()
            if not code and not (cells.get((r, col["LM코드"])) or "").strip():
                continue
            get = lambda c: (cells.get((r, c)) or "").strip() if c is not None else ""  # noqa: E731
            rows.append({"행": r, "코드": code, "명칭": get(col["명칭"]), "개선 유형": get(type_col) if type_col is not None else None,
                         "LM 코드": get(col["LM코드"]), "LM 명칭": get(col["LM명"]), "집필진": get(writer_col), "검토진": get(reviewer_col)})
        return rows
    return None


def read_position(tables: list[dict]) -> dict:
    """NCS-학습모듈의 위치 → {'대분류','중분류','소분류','세분류':[…],'모듈':[{'능력단위','학습모듈명'}]}."""
    out: dict = {"대분류": None, "중분류": None, "소분류": None, "세분류": [], "모듈": []}
    for table in tables:
        cells = table["cells"]
        first = squash(cells.get((0, 0)))
        if first == "대분류" and table["rows"] <= 4:
            for r in range(table["rows"]):
                label = squash(cells.get((r, 0)))
                if label in ("대분류", "중분류", "소분류"):
                    out[label] = NUMBER_HEAD.sub("", _right_of(table, r, 0)) or None
        elif first == "세분류":
            header = _header_cols(table, {"능력단위": ("능력단위",), "학습모듈명": ("학습모듈명",)})
            if header is None:
                continue
            head_row, col = header
            for r in range(1, table["rows"]):
                name = (cells.get((r, 0)) or "").strip()
                if name and squash(name) != "세분류":
                    out["세분류"].append(name)
                if r > head_row:
                    unit = (cells.get((r, col["능력단위"])) or "").strip()
                    module = (cells.get((r, col["학습모듈명"])) or "").strip()
                    if unit or module:
                        out["모듈"].append({"능력단위": unit, "학습모듈명": module})
    return out


# ── 모듈 표 ─────────────────────────────────────────────────────────────────────

PLACEHOLDER_CODE = re.compile(r"^0{10}_")   # 양식의 작성 예시 '0000000000_20v2'


def is_module_table(table: dict) -> bool:
    """'능력단위 코드번호' 라벨이 있는 표. 양식의 작성 예시(코드 0000000000_…)와 라벨만 있는 안내 표는 제외."""
    code = label_value(table, "능력단위 코드번호")
    if code is None or PLACEHOLDER_CODE.match(code.strip()):
        return False
    return any(squash(v).startswith("능력단위코드번호") for v in table["cells"].values())


def read_module(table: dict) -> dict:
    """모듈 표 하나 → {'코드','명칭','학습모듈명','정의','목표','요소':[{'코드','번호','명칭','수행준거':[…],'행'}],
    '학습':[{'번호','명칭','행','내용':[{'번호','소번호','명칭','목표':[…],'행'}]}], '표': 문단 번호}.
    요소와 학습은 행 위치로 짝짓는다(학습 N의 행부터 다음 학습 행 전까지의 요소는 그 학습에 배정)."""
    out = {
        "표": table.get("paragraph"),
        "코드": (label_value(table, "능력단위 코드번호") or "").strip(),
        "명칭": (label_value(table, "능력단위명") or "").strip(),
        "학습모듈명": (label_value(table, "학습모듈명") or "").strip(),
        "정의": (label_value(table, "능력단위 정의") or "").strip(),
        "목표": (label_value(table, "학습모듈의 목표") or "").strip(),
        "요소": [], "학습": [], "머리행": None,
    }
    header = _header_cols(table, {"요소": ("코드번호",), "수행준거": ("수행준거",), "학습명": ("학습명",), "내용명": ("학습내용명",), "목표": ("학습목표",)})
    if header is None:
        return out
    head_row, col = header
    out["머리행"] = head_row
    cells = table["cells"]
    name_col = next((c for c in range(table["cols"]) if squash(cells.get((head_row, c))) == "능력단위요소명"), None)
    lessons: list[dict] = []
    for r in range(head_row + 1, table["rows"]):
        element = (cells.get((r, col["요소"])) or "").strip()
        if m := ELEMENT_IN_CELL.match(element):
            name = (m.group(3) or "").strip()
            if not name and name_col is not None:
                name = (cells.get((r, name_col)) or "").strip()
            out["요소"].append({"행": r, "코드": f"{m.group(1)}.{m.group(2)}", "능력단위": m.group(1), "번호": int(m.group(2)), "명칭": name,
                               "수행준거": split_sentences(cells.get((r, col["수행준거"])) or "")})
        lesson = (cells.get((r, col["학습명"])) or "").strip()
        if m := LESSON_CELL.match(lesson):
            lessons.append({"행": r, "번호": int(m.group(1)), "명칭": m.group(2).strip(), "내용": [], "요소": []})
        sub = (cells.get((r, col["내용명"])) or "").strip()
        goals = split_sentences(cells.get((r, col["목표"])) or "")
        if m := PLAN_SUB.match(sub):
            entry = {"행": r, "번호": int(m.group(1)), "소번호": int(m.group(2)), "명칭": (m.group(3) or "").strip(), "목표": goals, "번호 표기": sub.split(" ")[0]}
            owner = next((l for l in lessons if l["번호"] == entry["번호"]), None)
            if owner is None:
                owner = {"행": r, "번호": entry["번호"], "명칭": "", "내용": [], "요소": []}
                lessons.append(owner)
            owner["내용"].append(entry)
        elif sub or goals:
            # 'N-M.' 꼴이 아닌 학습 내용 행('1.1 …', 번호 없음 등). 목표 문장은 살려 두고 번호 오류는 ⑦이 지적한다
            owner = lessons[-1] if lessons else None
            if owner is None:
                owner = {"행": r, "번호": 0, "명칭": "", "내용": [], "요소": []}
                lessons.append(owner)
            owner["내용"].append({"행": r, "번호": owner["번호"], "소번호": None, "명칭": sub, "목표": goals, "번호 표기": None})
    lessons.sort(key=lambda l: l["행"])
    # 요소 ↔ 학습 짝짓기: 학습명 행부터 다음 학습명 행 전까지의 요소 행은 그 학습의 것(병합 셀은 왼쪽 위 칸에만 글이 있으므로
    # 요소 2개를 합친 학습은 두 번째 요소 행에 학습명이 없다). 첫 학습명보다 위에 있는 요소는 어디에도 배정하지 않는다(④가 지적).
    for element in out["요소"]:
        owner = None
        for lesson in lessons:
            if lesson["행"] <= element["행"]:
                owner = lesson
        if owner is not None:
            owner["요소"].append(element["코드"])
    out["학습"] = sorted(lessons, key=lambda l: l["번호"])
    return out


def read_modules(tables: list[dict]) -> list[dict]:
    return [read_module(t) for t in tables if is_module_table(t)]


def read_plan(tables: list[dict]) -> dict:
    """계획서 전체 — {'기본': …, '대조표': …, '총괄표': …, '위치': …, '모듈': […]}."""
    return {"기본": read_basic(tables), "대조표": read_change_table(tables), "총괄표": read_summary_table(tables),
            "위치": read_position(tables), "모듈": read_modules(tables)}
