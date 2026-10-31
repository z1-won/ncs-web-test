"""HWPX 서식 추출. 서식 판정 정책과 분리한다."""

import re
import io
import zipfile
from .loader import detect_format
from .xml_names import HP, HH, HC

_NOFILL = (None, "", "none", "#FFFFFF", "#ffffff")


def _hwpx_header_styles(z):
    """header.xml → (charPr: id→{bold, font}, borderFill: id→faceColor or None)"""
    from lxml import etree

    hdr = etree.parse(io.BytesIO(z.read("Contents/header.xml")))
    fonts = {}
    for ff in hdr.iter(HH + "fontface"):
        if ff.get("lang") == "HANGUL":
            for f in ff.findall(HH + "font"):
                fonts[f.get("id")] = f.get("face")
    charpr = {}
    for cp in hdr.iter(HH + "charPr"):
        fr = cp.find(HH + "fontRef")
        charpr[cp.get("id")] = {
            "bold": cp.find(HH + "bold") is not None,
            "font": fonts.get(fr.get("hangul")) if fr is not None else None,
        }
    fills = {}
    for b in hdr.iter(HH + "borderFill"):
        wb = b.find(".//" + HC + "winBrush")
        c = wb.get("faceColor") if wb is not None else None
        fills[b.get("id")] = None if c in _NOFILL else c.upper()
    return charpr, fills


def load_table_formats(path):
    """hwpx 표 목록(문서 순서). 표 = {'cells': {(r,c): {'text', 'fill', 'runs': [{'text','font','bold'}]}}, 'section': i}
    hwp 이면 None (서식 미지원)"""
    if detect_format(path) != "hwpx":
        return None
    from lxml import etree

    out = []
    with zipfile.ZipFile(path) as z:
        charpr, fills = _hwpx_header_styles(z)
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
                        runs = []
                        for r in tc.iter(HP + "run"):
                            t = re.sub(
                                r"\s+",
                                " ",
                                "".join(x.text or "" for x in r.iter(HP + "t")),
                            ).strip()
                            if t:
                                runs.append(
                                    {
                                        "text": t,
                                        **charpr.get(
                                            r.get("charPrIDRef"),
                                            {"bold": False, "font": None},
                                        ),
                                    }
                                )
                        cells[(int(a.get("rowAddr")), int(a.get("colAddr")))] = {
                            "text": " ".join(x["text"] for x in runs),
                            "fill": fills.get(tc.get("borderFillIDRef")),
                            "runs": runs,
                        }
                out.append({"cells": cells, "section": si})
    return out
