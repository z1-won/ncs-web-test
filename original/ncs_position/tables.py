"""문단 로더와 의존성을 명시한 표 추출기."""

import struct
import zlib
import zipfile
import re
import io
from .loader import detect_format, _read_cfb, _records, _hwp_para_text
from .xml_names import HP


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()


TAG_LIST_HEADER, TAG_PARA_TEXT, TAG_TABLE = 0x48, 0x43, 0x4D


def _hwpx_text(el):
    """변경추적 삭제 구간 제외, hp:t 안 tail 포함"""
    out, state = [], None
    for e in el.iter():
        tag = e.tag.replace(HP, "")
        if tag == "deleteBegin":
            state = "del"
        elif tag in ("deleteEnd", "insertEnd"):
            state = None
        elif tag == "insertBegin":
            state = "ins"
        if state == "del":
            continue
        if tag == "t":
            out.append(e.text or "")
        if e.tail and e.getparent() is not None and e.getparent().tag == HP + "t":
            out.append(e.tail)
        if tag == "p" and e is not el:
            out.append(" ")
    return _clean("".join(out))


def _hwpx_tables(path):
    from lxml import etree

    tables = []
    with zipfile.ZipFile(path) as z:
        names = sorted(
            [n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)],
            key=lambda n: int(re.search(r"\d+", n).group()),
        )
        for si, n in enumerate(names):
            root = etree.parse(io.BytesIO(z.read(n)))
            for tbl in root.iter(HP + "tbl"):
                cells = {}
                for tr in tbl.findall(HP + "tr"):
                    for tc in tr.findall(HP + "tc"):
                        a = tc.find(HP + "cellAddr")
                        cells[(int(a.get("rowAddr")), int(a.get("colAddr")))] = (
                            _hwpx_text(tc)
                        )
                tables.append(
                    {
                        "rows": int(tbl.get("rowCnt")),
                        "cols": int(tbl.get("colCnt")),
                        "cells": cells,
                        "section": si,
                    }
                )
    return tables


def _hwp_tables(path):
    with open(path, "rb") as stream:
        data = stream.read()
    read_stream, names = _read_cfb(data)
    flags = struct.unpack_from("<I", read_stream("FileHeader"), 36)[0]
    if flags & 2:
        raise ValueError("암호화된 hwp")
    tables = []
    for si, s in enumerate(
        sorted([n for n in names if n.startswith("Section")], key=lambda s: int(s[7:]))
    ):
        raw = read_stream(s)
        if flags & 1:
            raw = zlib.decompress(raw, -15)
        stack = []  # (level, table dict)
        cell = None  # (level, table, (row,col))
        for tag, level, payload in _records(raw):
            if tag == TAG_TABLE:
                rows, cols = struct.unpack_from("<HH", payload, 4)
                t = {"rows": rows, "cols": cols, "cells": {}, "section": si}
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, t))
                tables.append(t)
            elif tag == TAG_LIST_HEADER:
                while stack and stack[-1][0] > level:
                    stack.pop()  # 안쪽 표가 끝남
                if (
                    stack and stack[-1][0] == level and len(payload) >= 16
                ):  # 셀은 TABLE 레코드와 같은 레벨
                    col, row = struct.unpack_from("<HH", payload, 8)
                    t = stack[-1][1]
                    t["cells"].setdefault((row, col), "")
                    cell = (level, t, (row, col))
                else:
                    cell = None
            elif tag == TAG_PARA_TEXT and cell and level == cell[0] + 1:
                t, key = cell[1], cell[2]
                t["cells"][key] = _clean(
                    t["cells"][key] + " " + _hwp_para_text(payload)
                )
    return tables


def load_tables(path):
    fmt = detect_format(path)
    return fmt, (_hwp_tables(path) if fmt == "hwp" else _hwpx_tables(path))


def column(table, col, skip_header=False):
    """해당 열의 비어 있지 않은 셀을 행 순서대로"""
    vals = [(r, v) for (r, c), v in sorted(table["cells"].items()) if c == col and v]
    return [v for r, v in vals]


def find_table(tables, must_contain, after=None):
    """must_contain 문자열을 가진 셀이 있는 첫 표 (after 표 이후부터)"""
    start = tables.index(after) + 1 if after is not None else 0
    for t in tables[start:]:
        if any(must_contain in v for v in t["cells"].values()):
            return t
    return None
