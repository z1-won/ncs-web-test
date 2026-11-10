"""PDF 읽기 — 쪽마다 본문·머리말·꼬리말 줄과 인쇄된 쪽 번호. 원고의 '출력본'과 매뉴얼(RAG 자료) 둘 다 여기로 읽는다.

PDF는 hwp·hwpx와 달리 표 구조·문단 스타일·자동 번호가 없으므로 Document(원고)로 만들지 않는다.
hwpx가 유일하게 주지 못하는 "쪽"을 보태는 보조 입력이다(역할 'print'). 판정 정책은 두지 않는다.

- 외부 패키지 pypdf를 쓴다(선택 설치: pip install -e ".[pdf]"). 함수 안에서 import하므로 없으면 ValueError로 알린다.
- 글자의 y좌표로 위·아래 띠(기본 8 %)를 머리말·꼬리말로 분리한다. 학습모듈은 달리는 머리말에 학습명이 매 쪽 반복되어,
  띠를 빼지 않으면 '학습 1'이 모든 쪽에서 잡힌다. 띠 안이라도 그림·표 캡션은 본문으로 되돌린다.
- 쪽 번호(folio)는 꼬리말(없으면 머리말)의 숫자·로마 숫자 줄에서 읽는다. 못 읽은 쪽은 다수결 offset으로 추정하고 '추정'이라 표시한다.
- 글자를 거의 못 뽑는 PDF(스캔본, 글꼴 매핑 없음)는 text_ratio로 드러나며 load_pdf가 ValueError를 낸다. OCR은 하지 않는다.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .module_code import CODE_IN_NAME

PDF_MAGIC = b"%PDF-"
BAND = 0.08                       # 쪽 높이 대비 머리말·꼬리말 띠
MIN_TEXT_RATIO = 0.5              # 읽을 수 있는 글자 비율이 이보다 낮으면 '글자 추출 불가'
LINE_TOLERANCE = 2.5              # pt. 같은 줄로 묶는 y 차이
_READABLE = re.compile(r"[가-힣A-Za-z0-9]")
_ARABIC = re.compile(r"^\s*[-–—]?\s*(\d{1,4})\s*[-–—]?\s*$")
_ROMAN = re.compile(r"^\s*([ivxlcⅰ-ⅻⅠ-Ⅻ]{1,6})\s*$", re.I)
_EDGE_NUMBER = re.compile(r"^(\d{1,4})\s*[|·ㆍ∙‧\-–—]\s*\S|\S\s*[|·ㆍ∙‧\-–—]\s*(\d{1,4})$")  # '12 | 연회 관리' / '연회 관리 | 12'
_CAPTION = re.compile(r"^[\[\(〈<]?\s*(그림|표|서식)\s*\d")
_WS = re.compile(r"\s+")


class PdfUnavailable(ValueError):
    """pypdf가 설치되지 않음. 규칙은 이것을 △로 낸다."""


@dataclass(frozen=True)
class PdfPage:
    index: int                     # 물리 쪽(0부터)
    folio: str | None              # 인쇄된 쪽 번호('12', 'ⅲ'). 읽지도 추정하지도 못하면 None
    folio_source: str | None       # '읽음' | '추정' | None
    body: tuple[str, ...]          # 본문 줄(위에서 아래로)
    header: tuple[str, ...]        # 위 띠 줄
    footer: tuple[str, ...]        # 아래 띠 줄

    @property
    def lines(self) -> tuple[str, ...]:
        return self.header + self.body + self.footer

    @property
    def number(self) -> int:
        """사람이 부르는 물리 쪽 번호(1부터). folio가 없을 때 안내에 쓴다."""
        return self.index + 1


@dataclass(frozen=True)
class PdfDocument:
    path: Path
    pages: tuple[PdfPage, ...]
    text_ratio: float              # 공백 제외 글자 중 한글·영문·숫자 비율
    module_code: str | None        # 앞 3쪽에서 찾은 LM 코드(원고 동일성 확인용)

    def page_by_folio(self, folio: str) -> PdfPage | None:
        folio = str(folio).strip()
        for page in self.pages:
            if page.folio == folio:
                return page
        return None

    def find(self, pattern: re.Pattern | str, *, start: int = 0, where: str = "body"):
        """pattern에 맞는 줄을 (쪽, 줄, match)로 차례로 낸다. where: 'body' | 'all'."""
        regex = re.compile(pattern) if isinstance(pattern, str) else pattern
        for page in self.pages[start:]:
            for line in page.body if where == "body" else page.lines:
                match = regex.match(line)
                if match:
                    yield page, line, match


def is_pdf(path) -> bool:
    try:
        with Path(path).open("rb") as stream:
            return stream.read(5) == PDF_MAGIC
    except OSError:
        return False


def load_pdf(path, *, band: float = BAND, min_text_ratio: float = MIN_TEXT_RATIO) -> PdfDocument:
    """PDF 파일 → PdfDocument. pypdf가 없으면 PdfUnavailable, 글자를 못 뽑으면 ValueError."""
    path = Path(path)
    if not is_pdf(path):
        raise ValueError(f"PDF 파일이 아닙니다: {path.name}")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        raise PdfUnavailable("PDF 읽기에는 pypdf가 필요합니다: pip install -e \".[pdf]\"") from None
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            if reader.decrypt("") == 0:
                raise ValueError(f"암호가 걸린 PDF는 읽을 수 없습니다: {path.name}")
        raw_pages = [_read_page(page, band=band) for page in reader.pages]
    except PdfReadError as error:
        raise ValueError(f"PDF를 읽지 못했습니다: {path.name} ({error})") from None
    if not raw_pages:
        raise ValueError(f"쪽이 없는 PDF입니다: {path.name}")
    ratio = _text_ratio(raw_pages)
    if ratio < min_text_ratio:
        raise ValueError(f"글자를 추출할 수 없는 PDF입니다(스캔본이거나 글꼴 매핑이 없음): {path.name}")
    pages = _assign_folios(raw_pages)
    return PdfDocument(path, tuple(pages), ratio, _find_module_code(pages))


# --- 쪽 읽기 -------------------------------------------------------------------

def _read_page(page, *, band: float) -> dict:
    """한 쪽의 글자 조각을 y좌표로 줄로 묶고 머리말·본문·꼬리말로 나눈다."""
    height = float(page.mediabox.height) or 1.0
    rotation = (page.rotation or 0) % 360
    width = float(page.mediabox.width) or 1.0
    chunks: list[tuple[float, float, str]] = []

    def visit(text, cm, tm, font_dict, font_size):  # noqa: ARG001 — pypdf 콜백 서명
        if not text or not text.strip():
            return
        x, y = tm[4], tm[5]
        if rotation in (90, 270):      # 가로 쪽: 긴 변 기준으로 위아래를 정한다
            x, y = (y, width - x) if rotation == 90 else (height - y, x)
        chunks.append((y, x, text))

    page.extract_text(visitor_text=visit)
    if not chunks:
        return {"header": [], "body": [], "footer": []}
    extent = width if rotation in (90, 270) else height
    lines = _group_lines(chunks)
    out = {"header": [], "body": [], "footer": []}
    for y, text in lines:
        frac = y / extent
        zone = "header" if frac >= 1 - band else "footer" if frac <= band else "body"
        if zone != "body" and _CAPTION.match(text):
            zone = "body"
        out[zone].append(text)
    return out


def _group_lines(chunks: list[tuple[float, float, str]]) -> list[tuple[float, str]]:
    """y가 가까운 조각을 한 줄로. 위(큰 y)에서 아래로, 한 줄 안에서는 왼쪽부터."""
    chunks.sort(key=lambda c: (-c[0], c[1]))
    lines: list[tuple[float, list[tuple[float, str]]]] = []
    for y, x, text in chunks:
        if lines and abs(lines[-1][0] - y) <= LINE_TOLERANCE:
            lines[-1][1].append((x, text))
        else:
            lines.append((y, [(x, text)]))
    out = []
    for y, parts in lines:
        parts.sort(key=lambda p: p[0])
        text = _clean("".join(t for _, t in parts))
        if text:
            out.append((y, text))
    return out


def _clean(text: str) -> str:
    # 일부 글꼴 매핑은 2바이트 글자 사이에 NUL을 남긴다. 실제 본문에 NUL은 없으므로 지운다
    text = text.replace("\x00", "")
    text = unicodedata.normalize("NFC", text)
    return _WS.sub(" ", text).strip()


def _text_ratio(raw_pages: list[dict]) -> float:
    total = readable = 0
    for raw in raw_pages:
        for zone in ("header", "body", "footer"):
            for line in raw[zone]:
                compact = line.replace(" ", "")
                total += len(compact)
                readable += len(_READABLE.findall(compact))
    return readable / total if total >= 20 else 0.0


# --- 쪽 번호 -------------------------------------------------------------------

def read_folio(lines: list[str]) -> str | None:
    """띠의 줄에서 쪽 번호 하나. 단독 숫자 → 단독 로마 숫자 → '12 | 제목' 꼴의 가장자리 숫자 순."""
    for line in lines:
        match = _ARABIC.match(line)
        if match:
            return match.group(1)
    for line in lines:
        match = _ROMAN.match(line)
        if match:
            return match.group(1).lower()
    for line in lines:
        match = _EDGE_NUMBER.search(line)
        if match:
            return match.group(1) or match.group(2)
    return None


def _assign_folios(raw_pages: list[dict]) -> list[PdfPage]:
    read = [read_folio(raw["footer"]) or read_folio(raw["header"]) for raw in raw_pages]
    offsets = Counter(int(f) - i for i, f in enumerate(read) if f and f.isdigit())
    offset = offsets.most_common(1)[0][0] if offsets else None
    pages = []
    for i, raw in enumerate(raw_pages):
        folio, source = read[i], "읽음" if read[i] else None
        if folio is None and offset is not None and i + offset >= 1:
            folio, source = str(i + offset), "추정"
        pages.append(PdfPage(i, folio, source, tuple(raw["body"]), tuple(raw["header"]), tuple(raw["footer"])))
    return pages


def _find_module_code(pages: list[PdfPage], head_pages: int = 3) -> str | None:
    for page in pages[:head_pages]:
        for line in page.lines:
            match = CODE_IN_NAME.search(line)
            if match:
                return match.group(0)
    return None
