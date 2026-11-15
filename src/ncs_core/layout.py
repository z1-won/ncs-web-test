"""편집 체계 읽기 — hwpx의 구역별 용지·여백과 본문에 쓰인 글꼴(안내서 A-07 편집 서식).

기준값은 F14 집필 양식(KoPub 필수)과 요구사항정의서 REQ-02-002: A4(210×297㎜), 여백 좌우 25·위 20·아래 13·머리말 10·꼬리말 12㎜,
글꼴은 KoPub바탕체·KoPub돋움체 계열. 양식 hwpx의 pagePr 값(HWPUNIT = 1/7200인치)을 ㎜로 바꾸면 이 기준과 정확히 같다.
여기서는 읽기만 한다. 어긋났을 때 어떤 판정을 낼지는 ncs_misc.rules.editing이 정한다.
hwp(바이너리)는 읽지 않는다 — None을 돌려준다.
"""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from .hwpx import HH, HP, is_hwpx, section_names

MM_PER_UNIT = 25.4 / 7200
PAGE_MM = {"가로": 210.0, "세로": 297.0}
MARGINS_MM = {"왼쪽": 25.0, "오른쪽": 25.0, "위": 20.0, "아래": 13.0, "머리말": 10.0, "꼬리말": 12.0}
TOLERANCE_MM = 0.5
FONT_FAMILY = "KoPub"                      # 'KoPub바탕체 Light', 'KoPubWorld돋움체 Bold' 등 이름이 이 낱말로 시작하면 양식 글꼴
_MARGIN_ATTR = {"왼쪽": "left", "오른쪽": "right", "위": "top", "아래": "bottom", "머리말": "header", "꼬리말": "footer"}
_ASIDE = {"memo", "hiddenComment", "footNote", "endNote", "header", "footer"}   # 본문 밖 글 — 글꼴을 따지지 않는다
_LETTERS = re.compile(r"[가-힣A-Za-z0-9]")    # 글꼴을 따질 글자 — 기호 글꼴 문자·공백·문장 부호는 세지 않는다


def _mm(value: str | None) -> float | None:
    try:
        return round(int(value) * MM_PER_UNIT, 1)
    except (TypeError, ValueError):
        return None


def _page(root: ET.Element) -> dict | None:
    page = next(root.iter(HP + "pagePr"), None)
    if page is None:
        return None
    width, height = _mm(page.get("width")), _mm(page.get("height"))
    if page.get("landscape") == "NARROWLY":   # 가로 방향 용지는 가로·세로가 바뀌어 적힌다
        width, height = height, width
    margin = page.find(HP + "margin")
    margins = {name: _mm(margin.get(attr)) if margin is not None else None for name, attr in _MARGIN_ATTR.items()}
    return {"가로": width, "세로": height, "여백": margins}


def _fonts(root: ET.Element) -> dict[str, str | None]:
    """header.xml → charPr id → 한글 글꼴 이름."""
    faces = {}
    for face in root.iter(HH + "fontface"):
        if face.get("lang") == "HANGUL":
            for font in face.findall(HH + "font"):
                faces[font.get("id")] = font.get("face")
    out = {}
    for prop in root.iter(HH + "charPr"):
        ref = prop.find(HH + "fontRef")
        out[prop.get("id")] = faces.get(ref.get("hangul")) if ref is not None else None
    return out


def read_layout(path: Path | str) -> dict | None:
    """{'구역': [{'구역', '가로', '세로', '여백': {…}}], '글꼴': {글꼴 이름: 글자 수}, '예': {글꼴 이름: 그 글꼴로 적힌 첫 문구}}.
    구역은 원고에 저장된 구역 그대로(엔진이 앞부분·본문으로 맞추기 전)다. hwpx가 아니면 None."""
    path = Path(path)
    if not is_hwpx(path):
        return None
    pages, used, examples = [], Counter(), {}
    with zipfile.ZipFile(path) as archive:
        try:
            font_of = _fonts(ET.fromstring(archive.read("Contents/header.xml")))
        except KeyError:
            font_of = {}
        for index, name in enumerate(section_names(archive)):
            root = ET.fromstring(archive.read(name))
            page = _page(root)
            if page is not None:
                pages.append({"구역": index, **page})
            aside = {id(run) for element in root.iter() if element.tag.rsplit("}", 1)[-1] in _ASIDE for run in element.iter(HP + "run")}
            for run in root.iter(HP + "run"):
                if id(run) in aside:
                    continue
                text = "".join(t.text or "" for t in run.findall(HP + "t"))
                count = len(_LETTERS.findall(text))
                if not count:
                    continue
                font = font_of.get(run.get("charPrIDRef")) or "(글꼴 정보 없음)"
                used[font] += count
                examples.setdefault(font, text.strip()[:30])
    return {"구역": pages, "글꼴": dict(used.most_common()), "예": examples}


def page_problems(layout: dict) -> list[str]:
    """구역별로 기준과 다른 용지·여백을 문장으로. 없으면 빈 목록."""
    problems = []
    for page in layout["구역"]:
        wrong = [f"용지 {name} {page[name]}㎜(기준 {expected:g}㎜)" for name, expected in PAGE_MM.items()
                 if page[name] is None or abs(page[name] - expected) > TOLERANCE_MM]
        wrong += [f"{name} 여백 {page['여백'][name]}㎜(기준 {expected:g}㎜)" for name, expected in MARGINS_MM.items()
                  if page["여백"][name] is None or abs(page["여백"][name] - expected) > TOLERANCE_MM]
        if wrong:
            problems.append(f"구역 {page['구역']}: " + ", ".join(wrong))
    return problems


def other_fonts(layout: dict) -> list[tuple[str, int, str]]:
    """양식 글꼴(KoPub 계열)이 아닌 글꼴 — [(글꼴 이름, 글자 수, 예 문구)], 많이 쓰인 순."""
    return [(font, count, layout["예"].get(font, "")) for font, count in layout["글꼴"].items() if not font.startswith(FONT_FAMILY)]
