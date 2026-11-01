"""본문 끝의 개발 이력 표와 판권 표 읽기.

개발 이력 표(머리 'NCS학습모듈 개발이력'): '발행일' 행마다 블록 하나. 신규 양식은 블록 1개(세분류명), 개선 양식은 블록 2개 이상
(이전 이력 + 이번 개선: 학습모듈명). 판권 표: 첫 셀 '학습모듈명(LM코드)', 저작권자/연구사업기관/발행일/ISBN 행.
"""

import re

LM_CODE = re.compile(r"LM(\d{10})_(\d{2})v(\d+)")
PLACEHOLDER = re.compile(r"○|XX|20XX|\(세분류 코드번호\)|\(학습모듈 코드번호\)")


def _label(text: str) -> str:
    return re.sub(r"\s", "", text or "")


def read_histories(tables: list[dict]) -> list[dict]:
    """→ [{'paragraph', 'blocks': [{'발행일','세분류명','학습모듈명','개발기관','집필진': [...], '검토진': [...], 'rows': (a, b)}]}]"""
    out = []
    for table in tables:
        cells = table["cells"]
        if not any(_label(v).startswith("NCS학습모듈개발이력") for v in cells.values()):
            continue
        rows = sorted({r for r, _ in cells})
        blocks, current = [], None
        for r in rows:
            label = _label(cells.get((r, 0), ""))
            value = (cells.get((r, 1)) or "").strip()
            if label == "발행일":
                current = {"발행일": value, "세분류명": None, "학습모듈명": None, "개발기관": None, "집필진": [], "검토진": [], "rows": (r, r)}
                blocks.append(current)
                continue
            if current is None:
                continue
            current["rows"] = (current["rows"][0], r)
            if label in ("세분류명", "학습모듈명", "개발기관"):
                current[label] = value
            if label == "집필진" or (label == "" and value and current["집필진"]):
                if value and not value.startswith("*"):
                    current["집필진"].append(value)
            reviewer = (cells.get((r, 3)) or "").strip()
            if _label(cells.get((r, 2), "")) == "검토진" or (reviewer and current["검토진"]) or (reviewer and _label(cells.get((r, 2), "")) == ""):
                if reviewer and not reviewer.startswith("*"):
                    current["검토진"].append(reviewer)
        out.append({"paragraph": table["paragraph"], "blocks": blocks})
    return out


def read_colophons(tables: list[dict]) -> list[dict]:
    """→ [{'paragraph', '학습모듈명', 'code', '저작권자', '연구사업기관', '발행일', 'ISBN'(행 존재), 'isbn_value'}]"""
    out = []
    for table in tables:
        cells = table["cells"]
        labels = {_label(v) for v in cells.values()}
        if not ({"저작권자", "발행일"} <= labels and any(l.startswith("연구사업기관") or l.startswith("연구기관") for l in labels)):
            continue
        head = (cells.get((0, 0)) or "").strip()
        code = LM_CODE.search(head)
        info = {"paragraph": table["paragraph"], "학습모듈명": head, "code": code.group() if code else None,
                "저작권자": None, "연구사업기관": None, "발행일": None, "ISBN": False, "isbn_value": None}
        for (r, c), v in sorted(cells.items()):
            label = _label(v)
            value = (cells.get((r, c + 1)) or "").strip()
            if label == "저작권자":
                info["저작권자"] = value
            elif label.startswith("연구사업기관") or label.startswith("연구기관"):
                info["연구사업기관"] = value
            elif label == "발행일":
                info["발행일"] = value
            elif label == "ISBN":
                info["ISBN"], info["isbn_value"] = True, value
        out.append(info)
    return out
