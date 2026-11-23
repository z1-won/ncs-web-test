"""표기 문구 자동 삽입(REQ-02-006 ③) — 원고(hwpx)의 그림 캡션 위에 AI 활용 줄을 넣은 사본을 만든다. 원고의 다른 글은 바꾸지 않는다.

그림 한 개의 표기 순서(F14 집필 양식, F08 AI 도구 사용 표기 예):
    (그림)
    출처: 집필진 제작(2026)                       ← 있던 줄 그대로
    ChatGPT를 활용하여 수정 보완함. 2026. 7. 20.  ← 여기서 넣는 줄(캡션 문단 바로 앞에 새 문단)
    [그림 1-1] 생산 설비 주요 구성 요소           ← 있던 줄 그대로
새 문단의 문단 모양과 글자 모양은 출처 줄의 것을 따르고, 출처 줄이 없으면 캡션의 것을 따른다. 출처 줄은 지어내지 않는다.
이미 AI 활용 줄이 있는 그림에는 넣지 않는다(두 번 적히지 않게). 넣은 줄은 ncs_core.figures.parse_ai_mark로 다시 읽어 같은 값인지 확인한다.

문단 번호는 읽은 문서(ncs_core.documents.Document)의 (구역, 문단)으로 받는다. 읽은 문서의 구역은 파일의 구역과 다를 수 있어
(앞부분과 본문으로 다시 나눈다), 파일에서는 문서 전체에서 몇 번째 <hp:p>인지로 찾는다(표 안 문단 포함, 문서 순서).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from ncs_core.documents import load_document
from ncs_core.figures import LOOKBACK, SOURCE, Figure, ai_line, clean_tool, manuscript_figures, parse_ai_mark, parse_label
from ncs_core.hwpx import HP, para_text, register_namespaces, section_names
from ncs_core.pictures import picture_records, pictures_by_caption

register_namespaces()

SOURCE_MAX = 500


@dataclass(frozen=True)
class Mark:
    """캡션 자리(구역, 문단)에 넣을 AI 활용 줄 하나."""
    section: int
    para: int
    tool: str
    mode: str          # 'generated'(생성함) | 'modified'(수정 보완함)
    on: date


def _template(paragraphs: list[ET.Element], para: int, captions: set[int]) -> ET.Element:
    """새 문단이 모양을 따를 문단 — 캡션 위 LOOKBACK개 문단 안의 출처 줄, 없으면 캡션."""
    seen = 0
    for j in range(para - 1, -1, -1):
        if j in captions:
            break
        text = para_text(paragraphs[j]).strip()
        if not text:
            continue
        seen += 1
        if seen > LOOKBACK:
            break
        if SOURCE.match(text):
            return paragraphs[j]
    return paragraphs[para]


def _new_paragraph(template: ET.Element, text: str) -> ET.Element:
    attributes = {**template.attrib, "id": "0", "pageBreak": "0", "columnBreak": "0"}
    paragraph = ET.Element(HP + "p", attributes)
    runs = template.findall(HP + "run")
    styled = next((run for run in runs if any((t.text or "").strip() for t in run.findall(HP + "t"))), runs[0] if runs else None)
    run = ET.SubElement(paragraph, HP + "run", {"charPrIDRef": styled.get("charPrIDRef", "0") if styled is not None else "0"})
    ET.SubElement(run, HP + "t").text = text
    return paragraph


def _edit(source: bytes, wanted: dict[int, object], known: dict[int, Figure], section_sizes: list[int], decide) -> tuple[bytes, list, list]:
    """캡션 자리(문서 전체에서 몇 번째 문단)마다 새 문단 하나를 넣는다. → (hwpx 바이트, 넣은 것 [(그림, 요청, 새 문단)], 넣지 못한 것 [{그림, 이유}]).

    decide(figure, paragraphs, para, captions, request) → (앞에 넣을 문단, 모양을 따를 문단, 넣을 글) 또는 넣지 않는 까닭(문자열).
    읽은 문서의 구역은 파일의 구역과 다를 수 있다(ncs_core.documents.normalize_sections가 앞부분과 본문으로 다시 나눈다).
    문단의 순서는 같으므로 문서 전체에서 몇 번째 문단인지로 맞추고, 파일의 문단 수가 읽은 것과 다르면 아무것도 넣지 않는다.
    """
    done, failed, changed = [], [], {}
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        roots = [(name, ET.fromstring(archive.read(name))) for name in section_names(archive)]
        counts = [sum(1 for _ in root.iter(HP + "p")) for _, root in roots]
        if sum(counts) != sum(section_sizes):
            return source, [], [{"그림": known[place].label, "이유": "원고의 문단 수가 읽은 것과 달라 자리를 정하지 못했습니다"} for place in sorted(wanted)]
        base = 0
        for (name, root), count in zip(roots, counts):
            here = {place - base: request for place, request in wanted.items() if base <= place < base + count}
            captions = {place - base for place in known if base <= place < base + count}
            start, base = base, base + count
            if not here:
                continue
            parents = {child: parent for parent in root.iter() for child in parent}
            paragraphs = list(root.iter(HP + "p"))
            inserted = False
            for para, request in sorted(here.items()):
                figure = known[para + start]
                if parse_label(para_text(paragraphs[para])) is None:
                    failed.append({"그림": figure.label, "이유": "그 자리에서 그림 캡션을 찾지 못했습니다"})
                    continue
                decided = decide(figure, paragraphs, para, captions, request)
                if isinstance(decided, str):
                    failed.append({"그림": figure.label, "이유": decided})
                    continue
                anchor, template, text = decided
                parent = parents.get(anchor)
                if parent is None or anchor.find(f".//{HP}secPr") is not None:
                    failed.append({"그림": figure.label, "이유": "구역의 첫 문단이라 그 앞에 줄을 넣을 수 없습니다. 한글에서 직접 적어 주세요"})
                    continue
                new = _new_paragraph(template, text)
                parent.insert(list(parent).index(anchor), new)
                done.append((figure, request, new))
                inserted = True
            if inserted:
                changed[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        if not changed:
            return source, done, failed
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            for item in archive.infolist():
                data = changed.get(item.filename)
                if data is None:
                    data = archive.read(item.filename)
                target.writestr(item, data, compress_type=zipfile.ZIP_STORED if item.filename == "mimetype" else item.compress_type)
    return out.getvalue(), done, failed


def _places(figures: list[Figure], section_sizes: list[int]):
    """(문서 전체에서 몇 번째 문단인지 내는 함수, {그 번호: 그림})."""
    starts = [sum(section_sizes[:index]) for index in range(len(section_sizes))]

    def flat(section: int, para: int) -> int | None:
        return starts[section] + para if 0 <= section < len(section_sizes) and 0 <= para < section_sizes[section] else None

    return flat, {flat(figure.section, figure.para): figure for figure in figures}


ALREADY = "이미 있음"


def insert_marks(source: bytes, marks: list[Mark], figures: list[Figure], section_sizes: list[int]) -> tuple[bytes, dict]:
    """AI 활용 줄을 넣은 hwpx 바이트와 요약.

    figures: 그 원고의 manuscript_figures 결과(캡션 자리와 이미 있는 AI 표기를 안다).
    section_sizes: 읽은 문서의 구역별 문단 수([len(s) for s in document.sections]).
    요약: {'넣음': [{'그림', '줄'}], '이미 있음': [그림 번호…], '넣지 못함': [{'그림', '이유'}], '다시 읽기': 넣은 줄 가운데 같은 값으로 다시 읽힌 수}
    """
    flat, known = _places(figures, section_sizes)
    summary: dict = {"넣음": [], "이미 있음": [], "넣지 못함": [], "다시 읽기": 0}
    wanted: dict[int, Mark] = {}
    for mark in marks:
        place = flat(mark.section, mark.para)
        if place is None or place not in known:
            summary["넣지 못함"].append({"그림": f"구역 {mark.section} 문단 {mark.para}", "이유": "그 자리에서 그림 캡션을 찾지 못했습니다"})
        else:
            wanted[place] = mark

    def decide(figure, paragraphs, para, captions, mark):
        if figure.ai is not None:
            return ALREADY
        return paragraphs[para], _template(paragraphs, para, captions), ai_line(mark.tool, mark.mode, mark.on)

    content, done, failed = _edit(source, wanted, known, section_sizes, decide)
    summary["이미 있음"] = [item["그림"] for item in failed if item["이유"] == ALREADY]
    summary["넣지 못함"] += [item for item in failed if item["이유"] != ALREADY]
    for figure, mark, new in done:
        read = parse_ai_mark(para_text(new))
        if read is not None and (read.tool, read.mode, read.on) == (clean_tool(mark.tool), mark.mode, mark.on):
            summary["다시 읽기"] += 1
        summary["넣음"].append({"그림": figure.label, "줄": para_text(new)})
    return content, summary


def insert_source_line(source: bytes, section: int, para: int, text: str, figures: list[Figure], section_sizes: list[int]) -> tuple[bytes, dict]:
    """출처 줄이 없는 그림의 캡션 위에 출처 줄을 넣은 hwpx 바이트와 요약 {'넣음': 그림 번호 또는 None, '줄', '이유'}.

    이미지 추천(REQ-02-011 '출처 표기 자동 삽입')이 쓴다 — 넣는 글은 이미지 저작권 DB의 출처 문구다. 이미 출처 줄이 있는 그림에는 넣지 않는다.
    그림에 AI 활용 줄이 있으면 그 위에 넣는다(출처 줄 → AI 활용 줄 → 그림 번호 순서). 새 문단의 모양은 캡션을 따른다.
    """
    text = " ".join((text or "").split())
    if not SOURCE.match(text):
        raise ValueError("출처 줄은 ‘출처: ’로 시작해야 합니다")
    if len(text) > SOURCE_MAX:
        raise ValueError(f"출처 줄은 {SOURCE_MAX}자까지 넣을 수 있습니다")
    flat, known = _places(figures, section_sizes)
    place = flat(section, para)
    if place is None or place not in known:
        return source, {"넣음": None, "줄": text, "이유": "그 자리에서 그림 캡션을 찾지 못했습니다"}

    def decide(figure, paragraphs, at, captions, line):
        if figure.source_line:
            return "이미 출처 줄이 있습니다"
        anchor, seen = paragraphs[at], 0
        for j in range(at - 1, -1, -1):          # 캡션 바로 위의 AI 활용 줄을 찾는다
            if j in captions:
                break
            above = para_text(paragraphs[j]).strip()
            if not above:
                continue
            seen += 1
            if seen > LOOKBACK:
                break
            mark = parse_ai_mark(above)
            if mark is not None and len(above) <= len(mark.text) + 12:
                anchor = paragraphs[j]
                break
        return anchor, paragraphs[at], line

    content, done, failed = _edit(source, {place: text}, known, section_sizes, decide)
    if not done:
        return source, {"넣음": None, "줄": text, "이유": failed[0]["이유"] if failed else "넣지 못했습니다"}
    return content, {"넣음": done[0][0].label, "줄": para_text(done[0][2]), "이유": ""}


def mark_pictures(manuscript: str | Path, content: bytes, tools: dict[str, str], *, on: date, mode: str = "modified") -> tuple[bytes, dict]:
    """그림 파일(bin_id)로 고른 그림의 캡션에 AI 활용 줄을 넣는다 — 화질 보정(업스케일) 제안본에 표기를 함께 넣을 때 쓴다.

    manuscript: 원래 원고(캡션과 그림의 자리를 읽는다). content: 그 원고에서 그림 파일만 바꾼 hwpx 바이트(구역 XML이 같아야 한다).
    tools: {bin_id: 도구 이름}. 요약에는 insert_marks의 것에 '캡션 없음'(캡션을 찾지 못한 bin_id)이 더해진다.
    """
    document = load_document(manuscript)
    figures = manuscript_figures(document)
    paired = pictures_by_caption(picture_records(document), [(figure.section, figure.para) for figure in figures])
    marks, found = [], set()
    for (section, para), record in paired.items():
        if record["bin_id"] in tools:
            marks.append(Mark(section, para, tools[record["bin_id"]], mode, on))
            found.add(record["bin_id"])
    content, summary = insert_marks(content, marks, figures, [len(section) for section in document.sections])
    summary["캡션 없음"] = sorted(set(tools) - found)
    return content, summary
