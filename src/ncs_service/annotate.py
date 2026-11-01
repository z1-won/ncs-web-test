"""원고 hwpx에 검수 결과를 한글 메모(fieldBegin type=MEMO)로 달아 돌려준다 — 집필진이 한글에서 메모를 따라가며 고치도록.

입력: 원고 hwpx 바이트 + 체크리스트 행(판정이 적합이 아닌 것). 행마다 문단 하나를 찾아 메모를 붙이고, 같은 문단에 여러 행이 오면
메모 하나에 합친다. 문단을 못 찾은 행은 문서 첫 문단의 '총괄 메모'에 목록으로 적는다. 원고 본문은 한 글자도 바꾸지 않는다.

문단 찾기(anchor)는 행의 '원고'(그 행이 본 문구)와 region_path(위치 경로)로 한다 — 엔진마다 원고 꼴이 달라(문자열·목록·딕셔너리) 순서대로 시도:
  1. 원고 문자열(또는 목록의 문자열들)과 같은 문단 → 포함 관계(6자 이상)
  2. region_path의 마지막 조각부터: '1-3. 이용정보 제공' 같은 소제목, '학습 1' 같은 머리, '수행 내용 2'(N번째), '참고 자료 > 1번'(N번째 항목)
  3. 못 찾으면 총괄 메모로
메모 XML은 한글이 저장한 실제 파일의 구조를 그대로 따른다(ctrl/fieldBegin[parameters, subList] … ctrl/fieldEnd). 메모 모양은 기본(65535).
"""

from __future__ import annotations

import io
import random
import re
import time
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from ncs_core.hwpx import HP, para_text, section_names
from ncs_core.text import PASS, visible

from . import export as _export  # 네임스페이스 등록을 공유한다(ET.register_namespace)

AUTHOR = "F02 자동검수"
MAX_MEMO_LINES = 12          # 한 메모에 싣는 최대 줄 수(행이 많이 겹친 문단)
MAX_LINE = 220               # 메모 한 줄 최대 길이
MAX_UNPLACED_LISTED = 40     # 총괄 메모에 나열하는 미배치 행 수


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", visible(text or ""))


@dataclass
class Para:
    section: int
    index: int           # 섹션 안 문단 순서(parse_section과 같은 iter 순서)
    element: ET.Element
    text: str            # 보이는 글(변경추적 반영)
    key: str = ""        # 비교용(공백 제거·기호 표시 변환)
    has_text: bool = False

    def __post_init__(self):
        self.key = _norm(self.text)
        self.has_text = bool(self.text.strip())


@dataclass
class Placement:
    rows: list[dict] = field(default_factory=list)


class Annotator:
    def __init__(self, source: bytes, *, author: str = AUTHOR):
        self.author = author
        self.archive = zipfile.ZipFile(io.BytesIO(source))
        self.sections: list[tuple[str, ET.Element]] = []
        self.paras: list[Para] = []
        for index, name in enumerate(section_names(self.archive)):
            root = ET.fromstring(self.archive.read(name))
            self.sections.append((name, root))
            for i, p in enumerate(root.iter(HP + "p")):
                self.paras.append(Para(index, i, p, para_text(p)))
        self.body_section = max(range(len(self.sections)), key=lambda i: sum(1 for p in self.paras if p.section == i)) if self.sections else 0
        existing = sum(1 for p in self.paras for fb in p.element.iter(HP + "fieldBegin") if fb.get("type") == "MEMO")
        self.next_number = existing + 1
        self.placed: dict[int, Placement] = {}   # 문단(전체 순번) → 행들
        self.unplaced: list[dict] = []

    # ───────── 문단 찾기 ─────────

    def _texts_of(self, value) -> list[str]:
        """'원고' 값에서 문단 찾기에 쓸 문자열 후보(긴 것부터)."""
        out: list[str] = []

        def walk(v, depth=0):
            if isinstance(v, str):
                s = re.sub(r"^\[(재료|기기|안전)\]\s*", "", v).strip()
                if len(_norm(s)) >= 2:
                    out.append(s)
            elif isinstance(v, list) and depth < 2:
                for item in v:
                    walk(item, depth + 1)
            elif isinstance(v, dict) and depth < 1:
                for item in v.values():
                    walk(item, depth + 1)

        walk(value)
        return sorted(dict.fromkeys(out), key=len, reverse=True)

    WINDOW = 120   # 위치 경로로 찾은 머리 뒤에서 원고 문구를 먼저 찾는 범위(문단 수)

    def _find_text(self, candidates: list[str], pool: list[Para] | None = None) -> Para | None:
        """후보 문구와 같은 문단 → 포함하는 문단 → 안에 들어가는 문단. pool이 있으면 그 안에서만."""
        paras = [p for p in (pool if pool is not None else self.paras) if p.has_text]
        for cand in candidates:
            key = _norm(cand)
            if not key:
                continue
            exact = [p for p in paras if p.key == key]
            if exact:
                return self._prefer_body(exact)
            if len(key) >= 6:
                contains = [p for p in paras if key in p.key]
                if contains:
                    return self._prefer_body(contains)
                inside = [p for p in paras if len(p.key) >= 6 and p.key in key]
                if inside:
                    return self._prefer_body(inside)
        return None

    def _prefer_body(self, found: list[Para]) -> Para:
        body = [p for p in found if p.section == self.body_section]
        return (body or found)[0]

    def _find_region(self, region_path: str) -> Para | None:
        segments = [s.strip() for s in (region_path or "").split(">")]
        segments = [s for s in segments if s and not re.match(r"^section\d+$", s) and "None" not in s]
        if not segments:
            return None
        body = [p for p in self.paras if p.section == self.body_section and p.has_text]
        start = 0
        anchor: Para | None = None
        for seg in segments:
            base = re.sub(r"\s*\(.*?\)\s*$", "", seg)           # '내비게이터 (학습마다 반복 5회)' → '내비게이터'
            m_nth = re.match(r"^(.*?)\s*(\d+)\s*번?$", base)      # '수행 내용 2', '1번'
            head_key = _norm(base)
            if re.match(r"^\d+-\d+", base):                      # '1-3. 이용정보 제공' / '1-1' → 그 소제목 문단
                code = re.match(r"^\d+-\d+", base).group(0)
                hit = next((p for p in body[start:] if re.match(rf"^{re.escape(code)}(\.|\s|$)", p.text.strip())), None)
            elif re.match(r"^학습\s*\d+$", base):                 # '학습 1' → 본문의 '학습 1' 머리(내비게이터)
                hit = next((p for p in body[start:] if p.key == head_key), None)
            elif m_nth and _norm(m_nth.group(1)) in ("수행내용", "학습내용", "평가", "교수학습방법"):
                n = int(m_nth.group(2))
                hits = [p for p in body[start:] if p.key.startswith(_norm(m_nth.group(1)))]
                hit = hits[n - 1] if len(hits) >= n else (hits[0] if hits else None)
            elif m_nth and anchor is not None:                    # '참고 자료 > 1번' → 앞 머리 뒤의 n번째 글 문단
                n = int(m_nth.group(2))
                after = [p for p in body[start:] if p.has_text]
                hit = after[n] if len(after) > n else None
            else:
                hit = next((p for p in body[start:] if p.key == head_key), None) \
                    or next((p for p in body[start:] if head_key and p.key.startswith(head_key)), None)
            if hit is not None:
                anchor = hit
                start = body.index(hit) + 1
        return anchor

    def place(self, row: dict) -> None:
        """위치 경로의 머리를 먼저 찾고, 그 뒤 범위 안에서 원고 문구를 찾는다(같은 문구가 여러 수행 내용에 반복되므로).
        머리를 못 찾으면 문서 전체에서 문구를 찾고, 그것도 없으면 머리 문단 자체에 단다."""
        candidates = self._texts_of(row.get("원고"))
        head = self._find_region(row.get("region_path", ""))
        para = None
        if head is not None:
            at = self.paras.index(head)
            para = self._find_text(candidates, self.paras[at:at + self.WINDOW])
        if para is None:
            para = self._find_text(candidates) if head is None else None
        if para is None:
            para = head
        if para is None or not para.has_text:
            self.unplaced.append(row)
            return
        self.placed.setdefault(self.paras.index(para), Placement()).rows.append(row)

    # ───────── 메모 글 ─────────

    @staticmethod
    def memo_lines(row: dict) -> list[str]:
        label = row["item_id"].replace("F02-", "")
        lines = [f"[{label}] {row['판정']}"]
        notes = row.get("비고") or {}
        checks = row.get("체크") or {}
        if isinstance(notes, dict):
            for name, value in checks.items():
                if value in ("X", "△") and notes.get(name):
                    lines.append(f"• {name}: {notes[name]}"[:MAX_LINE])
            for name, note in notes.items():
                if name not in checks and note:
                    lines.append(f"• {name}: {note}"[:MAX_LINE])
        elif notes:
            lines.append(f"• {notes}"[:MAX_LINE])
        if row.get("수정 제안"):
            lines.append(f"→ 수정 제안: {row['수정 제안']}"[:MAX_LINE])
        return lines

    def summary_lines(self, rows: list[dict]) -> list[str]:
        fail = sum(1 for r in rows if r["판정"] == "부적합")
        undecided = sum(1 for r in rows if r["판정"] == "판단불가")
        lines = [f"[F02 자동검수 총괄] 부적합 {fail}건 · 판단불가 {undecided}건 — 본문의 메모({len(self.placed)}곳)를 따라가며 확인하세요."
                 " 판단불가는 사람이 확정하는 항목입니다."]
        if self.unplaced:
            lines.append(f"문단을 특정하지 못한 지적 {len(self.unplaced)}건(검수 화면·확인서에서 확인):")
            for r in self.unplaced[:MAX_UNPLACED_LISTED]:
                first = self.memo_lines(r)
                lines.append(f"  {first[0]} @ {r.get('region_path', '')}" + (f" — {first[1][2:]}" if len(first) > 1 else ""))
            if len(self.unplaced) > MAX_UNPLACED_LISTED:
                lines.append(f"  … 외 {len(self.unplaced) - MAX_UNPLACED_LISTED}건")
        return [line[:MAX_LINE * 2] for line in lines]

    # ───────── XML 삽입 ─────────

    def _attach(self, para: Para, lines: list[str]) -> None:
        p = para.element
        runs = p.findall(HP + "run")
        if not runs:
            runs = [ET.SubElement(p, HP + "run", {"charPrIDRef": "0"})]
        first, last = runs[0], runs[-1]
        number = self.next_number
        self.next_number += 1
        begin_id = str(random.randint(10**9, 2**31 - 1))
        field_id = str(random.randint(10**8, 2**31 - 1))
        ctrl = ET.Element(HP + "ctrl")
        begin = ET.SubElement(ctrl, HP + "fieldBegin", {"id": begin_id, "type": "MEMO", "name": "", "editable": "1", "dirty": "0",
                                                        "zorder": str(number), "fieldid": field_id, "metaTag": ""})
        params = ET.SubElement(begin, HP + "parameters", {"cnt": "7", "name": ""})
        ET.SubElement(params, HP + "integerParam", {"name": "Prop"}).text = "0"
        ET.SubElement(params, HP + "stringParam", {"name": "Command"}).text = f"MEMO/65535/{number}/{random.randint(10**9, 4 * 10**9)}/{random.randint(10**7, 10**8)}/{self.author}/\\;;"
        ET.SubElement(params, HP + "stringParam", {"name": "ID"}).text = f"memo{number}"
        ET.SubElement(params, HP + "integerParam", {"name": "Number"}).text = str(number)
        ET.SubElement(params, HP + "stringParam", {"name": "Author"}).text = self.author
        ET.SubElement(params, HP + "stringParam", {"name": "MemoShapeIDRef"}).text = "65535"
        ET.SubElement(params, HP + "stringParam", {"name": "CreateDateTime"}).text = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        sub = ET.SubElement(begin, HP + "subList", {"id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK", "vertAlign": "TOP",
                                                    "linkListIDRef": "0", "linkListNextIDRef": "0", "textWidth": "0", "textHeight": "0",
                                                    "hasTextRef": "0", "hasNumRef": "0"})
        for line in lines[:MAX_MEMO_LINES] + ([f"… 외 {len(lines) - MAX_MEMO_LINES}줄"] if len(lines) > MAX_MEMO_LINES else []):
            mp = ET.SubElement(sub, HP + "p", {"id": "0", "paraPrIDRef": "0", "styleIDRef": "0", "pageBreak": "0", "columnBreak": "0", "merged": "0"})
            run = ET.SubElement(mp, HP + "run", {"charPrIDRef": "0"})
            ET.SubElement(run, HP + "t").text = line
        first.insert(0, ctrl)
        end = ET.Element(HP + "ctrl")
        ET.SubElement(end, HP + "fieldEnd", {"beginIDRef": begin_id, "fieldid": field_id})
        last.append(end)

    def build(self, rows: list[dict]) -> bytes:
        rows = [r for r in rows if r.get("판정") and r["판정"] != PASS]
        for row in rows:
            self.place(row)
        for order, placement in sorted(self.placed.items()):
            lines: list[str] = []
            for row in placement.rows:
                lines.extend(self.memo_lines(row))
            self._attach(self.paras[order], lines)
        # 총괄 메모: 본문 섹션의 첫 글 문단(또는 문서 첫 글 문단)
        top = next((p for p in self.paras if p.section == self.body_section and p.has_text), None) or next((p for p in self.paras if p.has_text), None)
        if top is not None:
            self._attach(top, self.summary_lines(rows))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            section_xml = {name: ET.tostring(root, encoding="utf-8", xml_declaration=True) for name, root in self.sections}
            for item in self.archive.infolist():
                data = section_xml.get(item.filename) or self.archive.read(item.filename)
                compress = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
                target.writestr(item, data, compress_type=compress)
        return out.getvalue()


def annotate_hwpx(source: bytes, rows: list[dict], *, author: str = AUTHOR) -> tuple[bytes, dict]:
    """메모를 단 hwpx 바이트와 요약 {'placed', 'memos', 'unplaced'}."""
    worker = Annotator(source, author=author)
    content = worker.build(rows)
    return content, {"placed": sum(len(p.rows) for p in worker.placed.values()), "memos": len(worker.placed) + 1,
                     "unplaced": len(worker.unplaced)}
