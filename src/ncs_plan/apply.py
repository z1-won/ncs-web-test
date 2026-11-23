"""비교 결과 반영 — 계획서 비교(ncs_plan.compare)에서 사람이 고른 칸을 대상 계획서(hwpx)의 사본에 기준 글로 바꿔 넣는다. 사람 작업 6번 '누락·불일치를 고친다'.

무엇을 고칠지는 사람이 고른다. 프로그램은 고른 칸의 글만 바꾼다:
  - 대상 계획서의 표 안에서 '대상' 글과 같은 문단(또는 셀)을 찾아 '기준' 글로 바꾼다. 같은 글이 여럿이면 칸의 성격(NCS 쪽은 왼쪽, 학습모듈 쪽은 오른쪽)으로 고른다.
  - 한쪽이 빈 칸(기준에만/대상에만 있음)은 반영하지 않는다 — 어디에 넣거나 뺄지는 표 구조에 달려 있어 한글에서 직접 한다.
  - 찾지 못한 칸은 건드리지 않고 알린다. 원본 파일은 바꾸지 않는다.
띄어쓰기만 다른 NCS 쪽 칸은 호출하는 쪽(화면)이 기본으로 고르지 않는다 — NCS 원문(F22)과 받아 둔 기준정보의 띄어쓰기가 다른 사례가 있어 어느 쪽이 맞는지 확인이 먼저다.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

from .compare import _norm
from .fill import HP          # fill을 불러오면 hwpx 이름공간 접두사도 등록된다

RIGHT = {"학습명", "학습 내용명", "학습 목표", "학습모듈명", "학습모듈의 목표", "LM 명칭", "LM 코드", "개선 후 명칭", "분석 결과", "검토진", "능력단위와 학습모듈명"}
CODE = re.compile(r"\d{10}_\d{2}v\d+")
PREFIX = re.compile(r"^\s*(?:학습\s*)?\d+(?:\s*-\s*\d+)?\s*\.\s*")      # 학습명·학습 내용명 앞의 번호('2. ', '1-1. ') — 읽을 때 떼는 번호는 그대로 둔다


def _own_text(p: ET.Element) -> str:
    return "".join(t.text or "" for run in p.findall(HP + "run") for t in run.findall(HP + "t"))


def _set_text(p: ET.Element, text: str) -> None:
    runs = p.findall(HP + "run")
    first = None
    for run in runs:
        for t in run.findall(HP + "t"):
            if first is None:
                first = t
                t.text = text
                for child in list(t):
                    t.remove(child)
            else:
                run.remove(t)
    for child in list(p):
        if child.tag == HP + "linesegarray":
            p.remove(child)       # 배치 캐시 — 한글이 열 때 다시 계산한다


def _cells(root: ET.Element):
    """(표, 셀, 열 번호) — 문서 순서."""
    for table in root.iter(HP + "tbl"):
        for tr in table.findall(HP + "tr"):
            for tc in tr.findall(HP + "tc"):
                addr = tc.find(HP + "cellAddr")
                yield table, tc, int(addr.get("colAddr", "0")) if addr is not None else 0


def _table_text(table: ET.Element) -> str:
    return "".join(t.text or "" for t in table.iter(HP + "t"))


def apply_differences(target: bytes, rows: list[dict]) -> tuple[bytes, dict]:
    """target: 대상 계획서 hwpx 바이트. rows: compare의 '차이' 행 중 고른 것. → (반영한 사본 바이트, {'반영': n, '반영 못 함': [{…, '사유'}]})."""
    source = zipfile.ZipFile(io.BytesIO(target))
    sections = {name: ET.fromstring(source.read(name)) for name in source.namelist() if re.fullmatch(r"Contents/section\d+\.xml", name)}
    table_texts: dict[int, str] = {}
    applied, skipped = 0, []
    for row in rows:
        new, old = _norm(row.get("기준")), _norm(row.get("대상"))
        if not new or not old:
            skipped.append({**row, "사유": "한쪽이 빈 칸 — 한글에서 직접 적을 것"})
            continue
        code = CODE.search(row.get("자리") or "")
        matches = []      # (범위 안인가, 열, 순번, 바꾸는 함수)
        order = 0
        for name in sorted(sections):
            for table, tc, col in _cells(sections[name]):
                sub = tc.find(HP + "subList")
                if sub is None:
                    continue
                paragraphs = sub.findall(HP + "p")
                hit = None
                for p in paragraphs:
                    if p.find(f".//{HP}tbl") is not None:
                        continue
                    text = _own_text(p)
                    head = PREFIX.match(text)
                    if _norm(text) == old:
                        hit = (lambda p=p: _set_text(p, new))
                        break
                    if head and _norm(text[head.end():]) == old:
                        hit = (lambda p=p, lead=head.group(0): _set_text(p, lead + new))
                        break
                if hit is None and len(paragraphs) > 1 and _norm(" ".join(_own_text(p) for p in paragraphs)) == old and tc.find(f".//{HP}tbl") is None:
                    def hit(paragraphs=paragraphs, sub=sub):     # 셀 전체가 한 글(여러 문단) — 첫 문단에 모으고 나머지는 지운다
                        _set_text(paragraphs[0], new)
                        for extra in paragraphs[1:]:
                            sub.remove(extra)
                if hit is None:
                    continue
                order += 1
                if id(table) not in table_texts:
                    table_texts[id(table)] = _table_text(table)
                inside = bool(code) and code.group(0) in table_texts[id(table)]
                matches.append((inside, col, order, hit, table))
        if code and any(m[0] for m in matches):
            matches = [m for m in matches if m[0]]
        if not matches:
            skipped.append({**row, "사유": "대상 계획서에서 그 글을 찾지 못함"})
            continue
        right = row.get("칸") in RIGHT
        chosen = max(matches, key=lambda m: (m[1], -m[2])) if right else min(matches, key=lambda m: (m[1], m[2]))
        chosen[3]()
        table_texts.pop(id(chosen[4]), None)
        applied += 1
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename in sections:
                data = ET.tostring(sections[item.filename], encoding="utf-8", xml_declaration=True)
            archive.writestr(item.filename, data, compress_type=zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    return out.getvalue(), {"반영": applied, "반영 못 함": skipped}
