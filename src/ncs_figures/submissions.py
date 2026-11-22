"""집필자 제출 서류 읽기 — ⑥ 수록 현황·증빙, ⑦ AI 결과물 현황 대조의 입력.

양식(캡스톤 자료의 2026년 계약서·서약서 원본 그대로, hwp·hwpx):
- 사진·삽화 수록 현황 목록   원고 집필 계약서(F07) 붙임 2 — 순번 / 시각적 자료 제목(그림 번호·제목) / 제작 방식 ✓
                             (집필자 직접제작 사진·삽화, 외부 제작의뢰 사진·삽화, 공공누리·공유마당, 포괄적 이용 허락, 기개발 학습모듈)
- 지식재산권 이용허락 동의서 F07 붙임 3 — 저작물 제목 / 출처 / 활용 학습모듈명 (포괄적 이용 허락의 증빙)
- 사진·삽화 제작 목록        사진·삽화 제작 계약서(F06) 붙임 1 — 저작물명 / 사진·삽화 (외부 제작의뢰의 증빙)
- 초상권 사용 동의서          F06 붙임 2 — 인물이 든 사진의 증빙(있는지만 본다)
- 생성형 AI 결과물 현황       집필자 서약서(F09) — 결과물 명 / 학습모듈 해당 쪽수 / 활용 AI
- 출력본 PDF                  그림이 실제로 몇 쪽에 있는지(서약서 쪽수와 맞대기)
한 파일에 여러 양식이 들어 있어도 된다 — 표의 머리 글자로 어느 양식인지 알아낸다. 양식 예시 줄('OOOO', 'p.00')은 뺀다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LABEL = re.compile(r"그림\s*(\d+)\s*[-‐–]\s*(\d+)")
CHECK = re.compile(r"[✓✔√vVoO○●◯☑■▣]")
PLACEHOLDER = re.compile(r"O{3,}|○{3,}|p\.\s*00\b|^-+$")
METHODS = (  # (머리 글자, 방식 이름)
    ("직접", "집필자 직접제작"), ("외부", "외부 제작의뢰"), ("공공", "공공누리·공유마당"), ("공유", "공공누리·공유마당"),
    ("포괄", "포괄적 이용 허락"), ("기개발", "기개발 학습모듈"),
)


def label_of(text: str) -> str | None:
    m = LABEL.search(text or "")
    return f"그림 {m.group(1)}-{m.group(2)}" if m else None


def _norm(text: str) -> str:
    return re.sub(r"[\s\[\]<>()·.,:\-]", "", text or "")


@dataclass
class StatusEntry:
    title: str
    label: str | None
    method: str | None          # METHODS의 방식 이름
    kind: str | None            # 사진·삽화(직접·외부 제작일 때)


@dataclass
class AiEntry:
    name: str
    label: str | None
    page: str | None
    tool: str | None
    note: str = ""


@dataclass
class Submissions:
    """제출 서류에서 읽은 목록. 비어 있는 목록은 '제출 안 함'(점검을 미실행으로)."""

    status: list[StatusEntry] = field(default_factory=list)
    production: list[StatusEntry] = field(default_factory=list)
    permissions: list[dict] = field(default_factory=list)
    portrait_consents: int = 0
    ai: list[AiEntry] = field(default_factory=list)
    print_pdf: object | None = None
    files: list[str] = field(default_factory=list)
    name: str = "제출 서류"

    # ---------------------------------------------------------------- 찾기
    @staticmethod
    def _match(entries, label: str | None, title: str | None):
        if label:
            hit = next((e for e in entries if e.label == label), None)
            if hit:
                return hit
        if title:
            key = _norm(title)
            return next((e for e in entries if key and (key in _norm(e.title) or _norm(e.title).endswith(key))), None)
        return None

    def status_of(self, label, title):
        return self._match(self.status, label, title)

    def production_of(self, label, title):
        return self._match(self.production, label, title)

    def ai_of(self, label, title):
        if label:
            hit = next((e for e in self.ai if e.label == label), None)
            if hit:
                return hit
        key = _norm(title or "")
        return next((e for e in self.ai if key and key in _norm(e.name)), None)

    def permission_of(self, label, title) -> dict | None:
        key = _norm(title or "")
        for p in self.permissions:
            if (label and label_of(p["title"]) == label) or (key and key in _norm(p["title"])):
                return p
        return None

    def page_of(self, label: str | None) -> str | None:
        """출력본 PDF에서 그림 캡션이 있는 인쇄 쪽."""
        if self.print_pdf is None or not label:
            return None
        n, m = label.split()[1].split("-")
        pattern = re.compile(rf"^\s*[\[〈<]?\s*그림\s*{n}\s*-\s*{m}(?!\d)")
        for page, _line, _m in self.print_pdf.find(pattern, where="all"):
            return page.folio or str(page.number)
        return None

    def unmatched(self, labels: set[str]) -> dict[str, list[str]]:
        """원고에 없는 목록 항목 — 목록에만 있음(누락·번호 불일치)."""
        out = {}
        for name, entries in (("수록 현황 목록", self.status), ("제작 목록", self.production)):
            only = [e.title for e in entries if e.label and e.label not in labels]
            if only:
                out[name] = only
        only_ai = [e.name for e in self.ai if e.label and e.label not in labels]
        if only_ai:
            out["AI 결과물 현황"] = only_ai
        return out


# ---------------------------------------------------------------- 양식 읽기

def _cells(table) -> dict[tuple[int, int], str]:
    return {k: (v or "").strip() for k, v in table["cells"].items()}


def _header_row(cells, rows, word) -> int | None:
    return next((r for r in range(min(rows, 5)) if any(word in v for (rr, _), v in cells.items() if rr == r)), None)


def _read_status(table, *, production=False) -> list[StatusEntry]:
    """수록 현황 목록(제작 방식 ✓) 또는 제작 목록(사진·삽화 ✓)."""
    cells, rows, cols = _cells(table), table["rows"], table["cols"]
    # 열마다 방식·유형: 머리 줄(최대 4줄)의 글자를 왼쪽 열에서 이어받는다(병합 칸은 첫 칸에만 글자가 있다)
    method_of, kind_of = {}, {}
    for r in range(min(rows, 5)):
        last = None
        for c in range(cols):
            text = cells.get((r, c), "")
            name = next((n for key, n in METHODS if key in text), None)
            if name:
                last = name
            if last and not production:
                method_of.setdefault(c, last) if c not in method_of else None
            if "사진" in text or "삽화" in text:
                kind_of[c] = "사진" if "사진" in text else "삽화"
    if not production:
        # 병합 칸: 방식 머리 다음 열이 비어 있으면 같은 방식(사진·삽화 둘로 나뉜 경우)
        for c in range(cols):
            if c not in method_of and c - 1 in method_of and c in kind_of:
                method_of[c] = method_of[c - 1]
    out = []
    for r in range(rows):
        first = cells.get((r, 0), "")
        if not re.fullmatch(r"\d+", first):
            continue
        title = cells.get((r, 1), "")
        if not title or PLACEHOLDER.search(title):
            continue
        marked = [c for c in range(2, cols) if CHECK.search(cells.get((r, c), ""))]
        method = next((method_of.get(c) for c in marked if method_of.get(c)), None)
        kind = next((kind_of.get(c) for c in marked if kind_of.get(c)), None)
        out.append(StatusEntry(title=title, label=label_of(title), method="외부 제작의뢰" if production else method, kind=kind))
    return out


def _read_ai(table) -> list[AiEntry]:
    cells, rows, cols = _cells(table), table["rows"], table["cols"]
    head = _header_row(cells, rows, "결과물") or 0
    col = {}
    for c in range(cols):
        text = cells.get((head, c), "")
        if "결과물" in text:
            col["name"] = c
        elif "쪽" in text:
            col["page"] = c
        elif "AI" in text.upper():
            col["tool"] = c
        elif "비고" in text:
            col["note"] = c
    out = []
    for r in range(head + 1, rows):
        name = cells.get((r, col.get("name", 1)), "")
        if not name or PLACEHOLDER.search(name):
            continue
        page = cells.get((r, col.get("page", 2)), "")
        page = None if PLACEHOLDER.search(page) else (re.search(r"\d+", page).group(0) if re.search(r"\d+", page) else None)
        out.append(AiEntry(name=name, label=label_of(name), page=page, tool=cells.get((r, col.get("tool", 3)), "") or None,
                           note=cells.get((r, col.get("note", 4)), "")))
    return out


def _read_permissions(table) -> list[dict]:
    cells, rows, cols = _cells(table), table["rows"], table["cols"]
    head = _header_row(cells, rows, "저작물 제목") or 0
    out = []
    for r in range(head + 1, rows):
        title = cells.get((r, 1), "")
        if title and not PLACEHOLDER.search(title):
            out.append({"title": title, "source": cells.get((r, 2), ""), "module": cells.get((r, 3), "")})
    return out


def read_documents(paths) -> Submissions:
    """제출 서류 파일들(hwp·hwpx·pdf) → Submissions. PDF는 출력본으로 본다."""
    from ncs_core.documents import load_document
    sub = Submissions()
    for path in map(Path, paths):
        sub.files.append(path.name)
        if path.suffix.lower() == ".pdf":
            from ncs_core.pdf import load_pdf
            sub.print_pdf = load_pdf(path)
            continue
        document = load_document(path)
        text = " ".join(t for s in document.sections for t in s)
        sub.portrait_consents += len(re.findall(r"초상권\s*사용\s*동의서", text)) and _filled_consents(document)
        for table in document.tables:
            joined = " ".join(table["cells"].values())
            if "시각적 자료 제목" in joined or ("제작 방식" in joined and "순번" in joined):
                sub.status += _read_status(table)
            elif "저작물명" in joined and "자료 유형" in joined:
                sub.production += _read_status(table, production=True)
            elif "결과물 명" in joined or ("결과물" in joined and "활용 AI" in joined):
                sub.ai += _read_ai(table)
            elif "저작물 제목" in joined and "출처" in joined:
                sub.permissions += _read_permissions(table)
    sub.name = f"제출 서류 {len(sub.files)}개"
    return sub


def _filled_consents(document) -> int:
    """초상권 동의서 중 협약자 이름이 채워진 것의 수(양식 그대로면 0)."""
    lines = [t for s in document.sections for t in s]
    return sum(1 for t in lines if re.search(r"협약자\s*\(초상권자\)\s*[:：]\s*\S{2,}", t) and "(인)" not in t.split(":", 1)[-1][:3])
