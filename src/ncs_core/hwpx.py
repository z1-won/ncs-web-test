"""HWPX(zip+XML) 읽기. 표준 ElementTree만 사용한다.

한 섹션 XML을 한 번 순회해 문단 텍스트, 표(셀 텍스트와 서식), 그림 이름을 함께 꺼낸다.
"""

import re
import zipfile
from xml.etree import ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

SECTION_NAME = re.compile(r"Contents/section(\d+)\.xml")
IMAGE_NAME = re.compile(r"원본 그림의 이름:\s*([^\n]+)")
NO_FILL = (None, "", "none", "#FFFFFF", "#ffffff")


def is_hwpx(path) -> bool:
    with zipfile.ZipFile(path) as archive:
        return any(SECTION_NAME.fullmatch(n) for n in archive.namelist())


def section_names(archive: zipfile.ZipFile) -> list[str]:
    names = [n for n in archive.namelist() if SECTION_NAME.fullmatch(n)]
    return sorted(names, key=lambda n: int(SECTION_NAME.fullmatch(n).group(1)))


def para_text(paragraph: ET.Element) -> str:
    """변경추적 반영본 텍스트. deleteBegin~deleteEnd 구간은 버린다.

    표 셀·캡션 안에 중첩된 <hp:p>는 내려가지 않는다. 그 문단들은 섹션 순회에서
    따로 나오므로, 내려가면 바깥 문단에 셀 텍스트가 전부 합쳐진다.
    <hp:t> 안 인라인 요소 뒤의 tail 텍스트는 포함한다.
    """
    out, state = [], None

    def walk(element: ET.Element) -> None:
        nonlocal state
        for child in element:
            tag = child.tag.replace(HP, "")
            if tag == "p":
                continue
            if tag == "deleteBegin":
                state = "del"
            elif tag in ("deleteEnd", "insertEnd"):
                state = None
            elif tag == "insertBegin":
                state = "ins"
            if state != "del" and tag == "t":
                out.append(child.text or "")
            walk(child)
            if state != "del" and child.tail and element.tag == HP + "t":
                out.append(child.tail)

    walk(paragraph)
    return "".join(out)


def header_styles(archive: zipfile.ZipFile) -> tuple[dict, dict]:
    """header.xml → (charPr id→{bold, font}, borderFill id→면색 또는 None)."""
    root = ET.fromstring(archive.read("Contents/header.xml"))
    fonts = {}
    for face in root.iter(HH + "fontface"):
        if face.get("lang") == "HANGUL":
            for font in face.findall(HH + "font"):
                fonts[font.get("id")] = font.get("face")
    char_props = {}
    for prop in root.iter(HH + "charPr"):
        ref = prop.find(HH + "fontRef")
        char_props[prop.get("id")] = {
            "bold": prop.find(HH + "bold") is not None,
            "font": fonts.get(ref.get("hangul")) if ref is not None else None,
        }
    fills = {}
    for border_fill in root.iter(HH + "borderFill"):
        brush = border_fill.find(".//" + HC + "winBrush")
        color = brush.get("faceColor") if brush is not None else None
        fills[border_fill.get("id")] = None if color in NO_FILL else color.upper()
    return char_props, fills


def _cell_runs(cell: ET.Element, own_paragraphs: list[ET.Element], char_props: dict) -> list[dict]:
    runs = []
    for paragraph in own_paragraphs:
        for run in paragraph.iter(HP + "run"):
            # itertext: <hp:t>교수<hp:fwSpace/>․학습</hp:t> 처럼 인라인 요소 뒤의 꼬리 텍스트도 읽는다
            text = re.sub(r"\s+", " ", "".join("".join(t.itertext()) for t in run.iter(HP + "t"))).strip()
            if text:
                runs.append(
                    {
                        "text": text,
                        **char_props.get(run.get("charPrIDRef"), {"bold": False, "font": None}),
                    }
                )
    return runs


def parse_section(root: ET.Element, section_index: int, styles: tuple[dict, dict] | None):
    """(문단 텍스트 목록, 표 목록, 그림 목록)을 돌려준다.

    표: {'section', 'paragraph', 'rows', 'cols', 'cells': {(r,c): 텍스트},
         'styles': {(r,c): {'fill', 'runs': [{'text','font','bold'}]}} (styles 없으면 None)}
    그림: (문단 인덱스, 원본 그림 이름)
    """
    parents = {child: parent for parent in root.iter() for child in parent}
    paragraphs = list(root.iter(HP + "p"))
    positions = {p: i for i, p in enumerate(paragraphs)}

    def owner_paragraph(element: ET.Element) -> ET.Element | None:
        current = parents.get(element)
        while current is not None and current.tag != HP + "p":
            current = parents.get(current)
        return current

    def owner_cell(paragraph: ET.Element) -> ET.Element | None:
        current = parents.get(paragraph)
        while current is not None and current.tag != HP + "tc":
            current = parents.get(current)
        return current

    images = []
    for comment in root.iter(HP + "shapeComment"):
        match = IMAGE_NAME.search(comment.text or "")
        paragraph = owner_paragraph(comment)
        if match and paragraph in positions:
            images.append((positions[paragraph], match.group(1).strip()))

    tables = []
    for table in root.iter(HP + "tbl"):
        paragraph = owner_paragraph(table)
        if paragraph not in positions:
            continue
        cells, cell_styles = {}, {}
        for row in table.findall(HP + "tr"):
            for cell in row.findall(HP + "tc"):
                address = cell.find(HP + "cellAddr")
                if address is None:
                    raise ValueError("HWPX 표 셀에 cellAddr가 없습니다")
                key = (int(address.get("rowAddr")), int(address.get("colAddr")))
                # 중첩 표는 자체 표로 처리하므로 바깥 셀에 합치지 않는다.
                own = [p for p in cell.iter(HP + "p") if owner_cell(p) is cell]
                cells[key] = re.sub(r"\s+", " ", " ".join(para_text(p) for p in own)).strip()
                if styles is not None:
                    char_props, fills = styles
                    cell_styles[key] = {
                        "fill": fills.get(cell.get("borderFillIDRef")),
                        "runs": _cell_runs(cell, own, char_props),
                    }
        tables.append(
            {
                "section": section_index,
                "paragraph": positions[paragraph],
                "rows": int(table.get("rowCnt") or 0),
                "cols": int(table.get("colCnt") or 0),
                "cells": cells,
                "styles": cell_styles if styles is not None else None,
            }
        )
    return [para_text(p) for p in paragraphs], tables, images


def load_hwpx(path):
    """(섹션별 문단, 표, 그림) — 그림은 (섹션, 문단, 이름)."""
    sections, tables, images = [], [], []
    with zipfile.ZipFile(path) as archive:
        try:
            styles = header_styles(archive)
        except KeyError:
            styles = None
        for index, name in enumerate(section_names(archive)):
            root = ET.fromstring(archive.read(name))
            paragraphs, section_tables, section_images = parse_section(root, index, styles)
            sections.append(paragraphs)
            tables.extend(section_tables)
            images.extend((index, paragraph, image) for paragraph, image in section_images)
    return sections, tables, images
