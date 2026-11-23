"""원고 → 원고 정보 + 항목별 구조 조각. 파싱은 코어·엔진 함수를 그대로 쓴다.

조각: {'조각', '위치', '블록_제목', '검수 대상': [{'n', '글'}], ...참고}. n = 본문 구역 안 문단 번호(앞 구역은 100000 + 문단).
학습 1이 차례 구역에서 시작하는 원고(SW제품기획 최종본 등)는 코어 구역 맞춤(normalize_sections (e))이 본문으로 옮긴다.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

from ncs_core import load_document
from ncs_core.field_terms import field_of
from ncs_core.manuscript.overview import parse_overview
from ncs_core.ncs_catalog import catalog
from ncs_perform.config import DEFAULT_CONFIG as PERFORM_CONFIG
from ncs_perform.pipeline import prepare_review as prepare_perform

CODE = re.compile(r"LM\d{10}_\d{2}v\d+")
UNIT_HEAD = re.compile(r"^\d+-\d+\.")
BODY = PERFORM_CONFIG.body_section
OFFSET = 100000


def number(section: int, idx: int) -> int:
    return idx if section == BODY else (section + 1) * OFFSET + idx


def where(n: int) -> tuple[int, int]:
    """n → (구역, 문단) — 메모를 달 자리."""
    return (BODY, n) if n < OFFSET else (n // OFFSET - 1, n % OFFSET)


def module_code(doc, given: str = "") -> str:
    if given:
        return given
    in_name = CODE.findall(Path(doc.path).name)
    if len(set(in_name)) == 1:
        return in_name[0]
    counts = collections.Counter(c for s in doc.sections for line in s for c in CODE.findall(line or ""))
    return counts.most_common(1)[0][0] if counts else ""


def module_info(doc, code: str) -> dict:
    found = field_of(code)
    unit = catalog().unit(code) if code and catalog() else None
    goal = ""
    for s in range(len(doc.sections)):
        try:
            got = parse_overview(doc, s).get("목표")
        except Exception:      # noqa: BLE001 — 개요가 없는 구역
            got = None
        if got and got.get("text"):
            goal = got["text"]
            break
    return {"code": code, "name": unit.name if unit else Path(doc.path).stem,
            "field": " > ".join(found.path), "field8": found.code, "goal": goal, "terms": list(found.terms)}


def load(path, code: str = ""):
    doc = load_document(path)
    code = module_code(doc, code)
    return doc, code, module_info(doc, code)


def _blocks(doc, code: str) -> list[dict]:
    return prepare_perform(doc, module_code=code or "LM0101010101_01v1").blocks


def _where(block: dict) -> str:
    unit = block.get("unit") or "?"
    no = block.get("perform_no")
    return f"학습 {unit.split('-')[0]} > {unit} {block.get('unit_title', '')}".rstrip() + f" > 수행 내용{(' ' + str(no)) if no else ''}"


def perform3_chunks(doc, code: str) -> list[dict]:
    chunks = []
    for block in _blocks(doc, code):
        if not block["안전"]:
            continue
        steps = [s["text"] for s in block["수행순서"] if s.get("level1")][:8]
        chunks.append({"조각": len(chunks) + 1, "위치": _where(block), "블록_제목": block.get("title", ""),
                       "참고_수행순서": steps, "검수 대상": [{"n": s["idx"], "글": s["text"]} for s in block["안전"]]})
    return chunks


def perform2_chunks(doc, code: str) -> list[dict]:
    chunks = []
    for block in _blocks(doc, code):
        items = [{"n": s["idx"], "글": s["text"]} for key in ("재료", "기기") for s in block[key] if (s.get("text") or "").strip()]
        if items:
            chunks.append({"조각": len(chunks) + 1, "위치": _where(block), "블록_제목": block.get("title", ""), "검수 대상": items})
    return chunks


def _unbullet(text) -> str:
    return re.sub(r"^\s*[-–•·∙◦▪]\s*", "", (text or "").strip())


def eval4_chunks(doc, code: str) -> list[dict]:
    import ncs_evaluation
    context = ncs_evaluation.prepare_review(doc, None, module_code=code or "LM0101010101_01v1")
    paragraphs = doc.sections[BODY]
    chunks = []
    for region in context.regions:
        if not region.get("found"):
            continue
        goals = [g for table in region.get("criteria", []) for unit in table for g in unit["goals"]]
        used, items = set(), []
        for table in region.get("method_items", []):
            for item in table:
                text = _unbullet(item["item"])
                n = next((i for i in range(region["start"], region["end"]) if i not in used and _unbullet(paragraphs[i]) == text), None)
                if n is None:
                    continue
                used.add(n)
                items.append({"n": n, "글": (paragraphs[n] or "").strip()})
        if items:
            chunks.append({"조각": len(chunks) + 1, "위치": f"학습 {region['lesson']} > 평가 > 평가 방법",
                           "블록_제목": "", "학습_목표": goals, "검수 대상": items})
    return chunks


def overview2_chunks(doc, code: str) -> list[dict]:
    for s in range(len(doc.sections) - 1, -1, -1):
        lines = [(t or "").strip() for t in doc.sections[s]]
        heads = [i for i, t in enumerate(lines) if t == "선수학습"]
        for i in reversed(heads):
            stop = next((j for j in range(i + 1, min(i + 15, len(lines)))
                         if lines[j].startswith(("학습모듈의 내용체계", "학습모듈의 내용 체계", "핵심 용어"))), None)
            if stop is None:
                continue
            items = [{"n": number(s, j), "글": lines[j]} for j in range(i + 1, stop) if lines[j]]
            goal = next((lines[j + 1] for j in range(max(0, i - 6), i) if lines[j] == "학습모듈의 목표" and j + 1 < i), "")
            if items:
                return [{"조각": 1, "위치": "학습모듈의 개요 > 선수학습", "블록_제목": "", "참고_학습모듈_목표": goal, "검수 대상": items}]
    return []


def misc3_chunks(doc, code: str) -> list[dict]:
    lines = [(t or "").strip() for t in doc.sections[BODY]]
    aside = doc.aside_paragraphs[BODY] if doc.aside_paragraphs else frozenset()
    skip = {s["idx"] for b in _blocks(doc, code) for key in ("재료", "기기") for s in b[key]}
    refs = next((i for i, t in enumerate(lines) if re.fullmatch(r"참고\s*자료|국내\s*자료|국외\s*자료|NCS\s*학습모듈\s*개발이력", t)), len(lines))
    chunks, current = [], None
    for i, text in enumerate(lines[:refs]):
        if not text or i in aside or i in skip or text.startswith(("출처", "[출처", "※ 출처")):
            continue
        if UNIT_HEAD.match(text) and len(text) < 60:
            current = {"조각": len(chunks) + 1, "위치": f"학습 {text.split('-')[0]} > {text[:40]}", "블록_제목": "", "검수 대상": []}
            chunks.append(current)
        if current is None:
            continue
        current["검수 대상"].append({"n": i, "글": text})
    return [c for c in chunks if c["검수 대상"]]


# 출처 검토(REQ-02-008) — 출처 표시 없는 인용. 규칙이 이미 보는 것(출처 줄이 붙은 문단, 같은 문단의 (저자, 연도)·'에 따르면',
# 인용 부호로 묶은 긴 문장)은 빼고 남은 본문 문단만 보낸다. 한 조각은 소단원(1-1.) 하나, 너무 길면 SRC_CHUNK 문단씩 나눈다.
SRC_HEAD = re.compile(r"^\s*[\[※]?\s*출\s*처\s*[:：]")
CITE = re.compile(r"\([^()]{1,40}?,\s*\d{4}[a-z]?(?:,\s*pp?\.\s*\d+)?\)|[가-힣A-Za-z]\s*\(\d{4}[a-z]?\)|에\s*따르면|재인용|출\s*처\s*[:：]")
QUOTED = re.compile(r"[“\"「『][^”\"」』]{30,}[”\"」』]")
SRC_CHUNK = 30
SRC_MIN = 25


def src_unquoted_chunks(doc, code: str) -> list[dict]:
    lines = [(t or "").strip() for t in doc.sections[BODY]]
    aside = doc.aside_paragraphs[BODY] if doc.aside_paragraphs else frozenset()
    in_table = doc.section_table_paragraphs(BODY) or frozenset()
    refs = next((i for i, t in enumerate(lines) if re.fullmatch(r"참고\s*자료|국내\s*자료|국외\s*자료|NCS\s*학습모듈\s*개발이력", t)), len(lines))
    nxt = {}
    last = None
    for i in range(refs - 1, -1, -1):           # 문단마다 다음 비지 않은 문단
        nxt[i] = last
        if lines[i]:
            last = lines[i]
    chunks, current, unit = [], None, None
    for i, text in enumerate(lines[:refs]):
        if UNIT_HEAD.match(text) and len(text) < 60:
            unit, current = text[:40], None
            continue
        if (not text or len(text) < SRC_MIN or i in aside or i in in_table or SRC_HEAD.match(text)
                or CITE.search(text) or QUOTED.search(text) or (nxt.get(i) and SRC_HEAD.match(nxt[i]))):
            continue
        if unit is None:
            continue
        if current is None or len(current["검수 대상"]) >= SRC_CHUNK:
            current = {"조각": len(chunks) + 1, "위치": f"학습 {unit.split('-')[0]} > {unit}", "블록_제목": "", "검수 대상": []}
            chunks.append(current)
        current["검수 대상"].append({"n": i, "글": text})
    return chunks


_BASE = {"perform2_brands": perform2_chunks, "perform3_safety": perform3_chunks, "eval4_items": eval4_chunks,
         "overview2_prereq": overview2_chunks, "misc3_names": misc3_chunks, "src_unquoted": src_unquoted_chunks}
EXTRACTORS = dict(_BASE)
