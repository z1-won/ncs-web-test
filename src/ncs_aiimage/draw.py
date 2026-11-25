"""도표·표 명세(diagram.Spec)를 PNG로 그린다(REQ-02-006 ① AI 생성) — 그리는 것은 코드이고 생성형 AI가 아니다.

  render(spec, width_mm=150, dpi=300) → Rendered(png, 가로·세로 픽셀, dpi, 쓴 글꼴)
같은 명세·같은 폭·같은 글꼴이면 같은 바이트가 나온다(시각·난수를 쓰지 않는다).
크기는 '놓을 폭(mm)'에서 정한다: 가로 픽셀 = 폭 ÷ 25.4 × dpi. 그림 검수의 실효 DPI 판정(놓인 크기 기준 300)과 같은 기준이다.
글자 크기는 인쇄 크기(pt)로 정해 두었으므로 폭을 바꿔도 글자의 인쇄 크기는 같다.
색은 회색 단계만 쓴다(흑백 인쇄에서도 같게 보이도록).

글꼴: KoPub 돋움체(Medium, Bold)를 먼저 찾고, 없으면 그 밖의 한글 고딕을 찾는다. 찾는 곳은 NCS_FONT_DIR, 저장소의 fonts/, 시스템 글꼴 폴더 순이다.
글꼴 파일은 저장소에 넣지 않는다(각자 둔다, .gitignore의 /fonts/). 하나도 없으면 FontError.
"""

import io
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .diagram import Spec, read_spec

ROOT = Path(__file__).resolve().parents[2]
REGULAR = ("KoPub Dotum Medium.ttf", "KoPubDotumMedium.ttf", "KoPubWorld Dotum Medium.ttf", "KoPubWorldDotumMedium.ttf",
           "Pretendard-Regular.otf", "NotoSansKR-Regular.otf", "NotoSansCJK-Regular.ttc", "NotoSansCJKkr-Regular.otf", "NanumGothic.ttf",
           "malgun.ttf", "AppleSDGothicNeo.ttc")
BOLD = ("KoPub Dotum Bold.ttf", "KoPubDotumBold.ttf", "KoPubWorld Dotum Bold.ttf", "KoPubWorldDotumBold.ttf",
        "Pretendard-Bold.otf", "NotoSansKR-Bold.otf", "NotoSansCJK-Bold.ttc", "NotoSansCJKkr-Bold.otf", "NanumGothicBold.ttf",
        "malgunbd.ttf", "AppleSDGothicNeo.ttc")
SYSTEM_DIRS = ("/usr/share/fonts", "/usr/local/share/fonts", "/Library/Fonts", "/System/Library/Fonts", "~/Library/Fonts", "~/.fonts",
               "~/.local/share/fonts", "C:/Windows/Fonts")
WIDTH_RANGE = (40.0, 170.0)      # 놓을 폭(mm). A4 본문 폭 안
DPI_RANGE = (72, 600)
DEFAULT_WIDTH = 150.0
DEFAULT_DPI = 300

INK = (30, 33, 36)
LINE = (88, 97, 106)
SOFT = (244, 245, 246)
HEAD = (228, 231, 234)
DARK = (70, 76, 83)
WHITE = (255, 255, 255)

BODY_PT = 9.0
SMALL_PT = 8.0
LABEL_PT = 9.5
PAD_PT = 5.0
GAP_PT = 16.0        # 칸 사이(화살표 자리)
MARGIN_PT = 3.0
LINE_PT = 0.6
LEADING = 1.38


class FontError(RuntimeError):
    """한글 글꼴을 찾지 못했다."""


@dataclass(frozen=True)
class Rendered:
    png: bytes
    width: int
    height: int
    dpi: int
    font: str


def _font_dirs() -> list[Path]:
    given = os.getenv("NCS_FONT_DIR", "").strip()
    dirs = ([Path(given)] if given else []) + [ROOT / "fonts"] + [Path(d).expanduser() for d in SYSTEM_DIRS]
    return [d for d in dirs if d.is_dir()]


@lru_cache(maxsize=4)
def _find(names: tuple[str, ...], dirs: tuple[str, ...]) -> str:
    listing: dict[str, str] = {}
    for folder in dirs:
        for path in sorted(Path(folder).rglob("*")):
            if path.suffix.lower() in (".ttf", ".otf", ".ttc"):
                listing.setdefault(path.name.lower(), str(path))
    for name in names:
        if name.lower() in listing:
            return listing[name.lower()]
    return ""


def font_paths() -> tuple[str, str]:
    """(보통, 굵은) 글꼴 파일. 굵은 것이 없으면 보통 것을 함께 쓴다. 하나도 없으면 FontError."""
    dirs = tuple(str(d) for d in _font_dirs())
    regular = _find(REGULAR, dirs)
    if not regular:
        raise FontError("한글 글꼴을 찾지 못했습니다 — KoPub 돋움체(KoPub Dotum Medium.ttf, KoPub Dotum Bold.ttf)를 fonts/ 폴더에 두거나 "
                        "NCS_FONT_DIR에 글꼴 폴더를 적습니다")
    return regular, _find(BOLD, dirs) or regular


def font_available() -> bool:
    try:
        font_paths()
        return True
    except FontError:
        return False


class _Pen:
    """한 번 그릴 때 쓰는 값과 도구(픽셀 단위로 바꾼 크기, 글꼴, 줄바꿈)."""

    def __init__(self, width_px: int, dpi: int):
        from PIL import ImageFont

        self.w = width_px
        self.u = dpi / 72.0                       # 1pt의 픽셀
        self.regular_path, self.bold_path = font_paths()
        self._fonts: dict = {}
        self._truetype = ImageFont.truetype
        self.pad = round(PAD_PT * self.u)
        self.gap = round(GAP_PT * self.u)
        self.margin = round(MARGIN_PT * self.u)
        self.line = max(1, round(LINE_PT * self.u))

    def font(self, pt: float, bold: bool = False):
        key = (pt, bold)
        if key not in self._fonts:
            path = self.bold_path if bold else self.regular_path
            index = 1 if path.lower().endswith(".ttc") and "cjk" in path.lower() else 0      # Noto CJK 묶음의 한국어 글꼴
            self._fonts[key] = self._truetype(path, max(6, round(pt * self.u)), index=index)
        return self._fonts[key]

    def text_width(self, text: str, font) -> int:
        return math.ceil(font.getlength(text))

    def line_height(self, pt: float) -> int:
        return round(pt * self.u * LEADING)

    def wrap(self, text: str, font, width: int) -> list[str]:
        """낱말 사이에서 끊고, 한 낱말이 폭보다 길면 글자에서 끊는다."""
        lines, current = [], ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if self.text_width(trial, font) <= width:
                current = trial
                continue
            if current:
                lines.append(current)
            current = ""
            for ch in word:
                if current and self.text_width(current + ch, font) > width:
                    lines.append(current)
                    current = ""
                current += ch
        if current:
            lines.append(current)
        return lines or [""]


@dataclass
class _Block:
    """줄바꿈을 끝낸 글 한 덩이."""
    lines: list[str]
    pt: float
    bold: bool = False

    def height(self, pen: _Pen) -> int:
        return len(self.lines) * pen.line_height(self.pt)


def _block(pen: _Pen, text: str, width: int, pt: float, bold: bool = False) -> _Block:
    return _Block(pen.wrap(text, pen.font(pt, bold), width), pt, bold)


def _draw_block(draw, pen: _Pen, block: _Block, x: int, y: int, width: int, *, align: str = "center", fill=INK) -> int:
    font = pen.font(block.pt, block.bold)
    step = pen.line_height(block.pt)
    for line in block.lines:
        dx = (width - pen.text_width(line, font)) // 2 if align == "center" else 0
        draw.text((x + dx, y + (step - round(block.pt * pen.u)) // 2), line, font=font, fill=fill)
        y += step
    return y


def _bullets(pen: _Pen, texts, width: int) -> list[tuple[_Block, int]]:
    indent = pen.text_width("• ", pen.font(SMALL_PT))
    return [(_block(pen, text, width - indent, SMALL_PT), indent) for text in texts]


def _draw_bullets(draw, pen: _Pen, bullets, x: int, y: int) -> int:
    font = pen.font(SMALL_PT)
    for block, indent in bullets:
        draw.text((x, y + (pen.line_height(SMALL_PT) - round(SMALL_PT * pen.u)) // 2), "•", font=font, fill=INK)
        y = _draw_block(draw, pen, block, x + indent, y, 0, align="left") + round(1.5 * pen.u)
    return y


def _bullets_height(pen: _Pen, bullets) -> int:
    return sum(block.height(pen) + round(1.5 * pen.u) for block, _ in bullets)


def _box(draw, pen: _Pen, x: int, y: int, w: int, h: int, *, fill=WHITE, outline=LINE) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=round(2.5 * pen.u), fill=fill, outline=outline, width=pen.line)


def _arrow(draw, pen: _Pen, start: tuple[float, float], end: tuple[float, float]) -> None:
    (x0, y0), (x1, y1) = start, end
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    head = min(4.5 * pen.u, length * 0.6)
    bx, by = x1 - ux * head, y1 - uy * head
    draw.line((round(x0), round(y0), round(bx), round(by)), fill=LINE, width=max(2, round(0.9 * pen.u)))
    half = head * 0.5
    draw.polygon([(round(x1), round(y1)), (round(bx - uy * half), round(by + ux * half)), (round(bx + uy * half), round(by - ux * half))], fill=LINE)


def _canvas(width: int, height: int):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, max(1, height)), WHITE)
    return image, ImageDraw.Draw(image)


def _cells(pen: _Pen, spec: Spec, inner: int) -> list[tuple[_Block, _Block | None]]:
    return [(_block(pen, item.label, inner, LABEL_PT, True), _block(pen, item.note, inner, SMALL_PT) if item.note else None)
            for item in spec.items]


def _cell_height(pen: _Pen, cell) -> int:
    label, note = cell
    return label.height(pen) + (round(2 * pen.u) + note.height(pen) if note else 0)


def _draw_cell(draw, pen: _Pen, cell, x: int, y: int, w: int, h: int, *, fill=SOFT) -> None:
    label, note = cell
    _box(draw, pen, x, y, w, h, fill=fill)
    top = y + (h - _cell_height(pen, cell)) // 2
    top = _draw_block(draw, pen, label, x + pen.pad, top, w - 2 * pen.pad)
    if note:
        _draw_block(draw, pen, note, x + pen.pad, top + round(2 * pen.u), w - 2 * pen.pad)


def _sequence(pen: _Pen, spec: Spec):
    n, m = len(spec.items), pen.margin
    if n <= 5:                                                     # 가로로 한 줄
        box_w = (pen.w - 2 * m - (n - 1) * pen.gap) // n
        cells = _cells(pen, spec, box_w - 2 * pen.pad)
        box_h = max(_cell_height(pen, cell) for cell in cells) + 2 * pen.pad
        image, draw = _canvas(pen.w, box_h + 2 * m)
        for i, cell in enumerate(cells):
            x = m + i * (box_w + pen.gap)
            _draw_cell(draw, pen, cell, x, m, box_w, box_h)
            if i:
                _arrow(draw, pen, (x - pen.gap + 2 * pen.u, m + box_h / 2), (x - 2 * pen.u, m + box_h / 2))
        return image
    box_w = pen.w - 2 * m                                          # 세로로 쌓는다(6칸 이상)
    cells = _cells(pen, spec, box_w - 2 * pen.pad)
    heights = [_cell_height(pen, cell) + 2 * pen.pad for cell in cells]
    image, draw = _canvas(pen.w, sum(heights) + (n - 1) * pen.gap + 2 * m)
    y = m
    for i, (cell, h) in enumerate(zip(cells, heights)):
        if i:
            _arrow(draw, pen, (pen.w / 2, y - pen.gap + 2 * pen.u), (pen.w / 2, y - 2 * pen.u))
        _draw_cell(draw, pen, cell, m, y, box_w, h)
        y += h + pen.gap
    return image


def _edge(cx: float, cy: float, w: float, h: float, tx: float, ty: float, pad: float) -> tuple[float, float]:
    """네모(가운데 cx,cy)에서 (tx,ty) 쪽으로 나가는 선이 네모의 가장자리(+pad)와 만나는 점."""
    dx, dy = tx - cx, ty - cy
    if not dx and not dy:
        return cx, cy
    scale = min((w / 2 + pad) / abs(dx) if dx else math.inf, (h / 2 + pad) / abs(dy) if dy else math.inf)
    return cx + dx * scale, cy + dy * scale


def _cycle(pen: _Pen, spec: Spec):
    n, m = len(spec.items), pen.margin
    box_w = round(pen.w * (0.30 if n <= 4 else 0.25))
    cells = _cells(pen, spec, box_w - 2 * pen.pad)
    box_h = max(_cell_height(pen, cell) for cell in cells) + 2 * pen.pad
    radius_x = (pen.w - 2 * m - box_w) / 2
    radius_y = max(box_h * (1.25 if n <= 4 else 1.7), radius_x * 0.5)
    height = round(2 * radius_y + box_h + 2 * m)
    image, draw = _canvas(pen.w, height)
    cx, cy = pen.w / 2, height / 2
    centers = [(cx + radius_x * math.cos(math.radians(-90 + 360 * i / n)), cy + radius_y * math.sin(math.radians(-90 + 360 * i / n)))
               for i in range(n)]
    for i in range(n):
        (ax, ay), (bx, by) = centers[i], centers[(i + 1) % n]
        _arrow(draw, pen, _edge(ax, ay, box_w, box_h, bx, by, 2 * pen.u), _edge(bx, by, box_w, box_h, ax, ay, 2 * pen.u))
    for cell, (x, y) in zip(cells, centers):
        _draw_cell(draw, pen, cell, round(x - box_w / 2), round(y - box_h / 2), box_w, box_h)
    return image


def _columns(pen: _Pen, spec: Spec, top: int, *, dark_head: bool):
    """갈래(열)마다 머리 칸 + 아래 글 줄. (그린 뒤의 높이, 열 가운데 x들)를 돌려주는 그리기 함수와 전체 높이."""
    n, m = len(spec.items), pen.margin
    gap = round(pen.gap * 0.5)
    col_w = (pen.w - 2 * m - (n - 1) * gap) // n
    inner = col_w - 2 * pen.pad
    heads = [_block(pen, item.label, inner, LABEL_PT, True) for item in spec.items]
    head_h = max(block.height(pen) for block in heads) + 2 * pen.pad
    bodies = [_bullets(pen, item.children, inner) for item in spec.items]
    body_h = max(_bullets_height(pen, body) for body in bodies)
    body_h = body_h + 2 * pen.pad if body_h else 0
    centers = [m + i * (col_w + gap) + col_w // 2 for i in range(n)]

    def paint(draw) -> None:
        for i, (head, body) in enumerate(zip(heads, bodies)):
            x = m + i * (col_w + gap)
            if body_h:
                _box(draw, pen, x, top, col_w, head_h + body_h, fill=WHITE)
            _box(draw, pen, x, top, col_w, head_h, fill=DARK if dark_head else SOFT, outline=DARK if dark_head else LINE)
            _draw_block(draw, pen, head, x + pen.pad, top + (head_h - head.height(pen)) // 2, inner, fill=WHITE if dark_head else INK)
            if body:
                _draw_bullets(draw, pen, body, x + pen.pad, top + head_h + pen.pad)

    return paint, top + head_h + body_h, centers


def _structure(pen: _Pen, spec: Spec):
    m = pen.margin
    root_w = round(pen.w * 0.36)
    root = _block(pen, spec.root, root_w - 2 * pen.pad, LABEL_PT, True)
    root_h = root.height(pen) + 2 * pen.pad
    top = m + root_h + pen.gap
    paint, bottom, centers = _columns(pen, spec, top, dark_head=False)
    image, draw = _canvas(pen.w, bottom + m)
    x = (pen.w - root_w) // 2
    _box(draw, pen, x, m, root_w, root_h, fill=DARK, outline=DARK)
    _draw_block(draw, pen, root, x + pen.pad, m + pen.pad, root_w - 2 * pen.pad, fill=WHITE)
    bus = m + root_h + pen.gap // 2
    width = max(2, round(0.9 * pen.u))
    draw.line((pen.w // 2, m + root_h, pen.w // 2, bus), fill=LINE, width=width)
    draw.line((centers[0], bus, centers[-1], bus), fill=LINE, width=width)
    for center in centers:
        draw.line((center, bus, center, top), fill=LINE, width=width)
    paint(draw)
    return image


def _compare(pen: _Pen, spec: Spec):
    paint, bottom, _ = _columns(pen, spec, pen.margin, dark_head=True)
    image, draw = _canvas(pen.w, bottom + pen.margin)
    paint(draw)
    return image


def _table(pen: _Pen, spec: Spec):
    m, cols = pen.margin, len(spec.header)
    avail = pen.w - 2 * m
    body_font, head_font = pen.font(BODY_PT), pen.font(BODY_PT, True)
    natural = []
    for c in range(cols):
        widest = max([pen.text_width(spec.header[c], head_font)] + [pen.text_width(row[c], body_font) for row in spec.rows])
        natural.append(min(max(widest + 2 * pen.pad, avail * 0.10), avail * 0.55))
    widths = [math.floor(avail * w / sum(natural)) for w in natural]
    widths[-1] += avail - sum(widths)
    heads = [_block(pen, cell, widths[c] - 2 * pen.pad, BODY_PT, True) for c, cell in enumerate(spec.header)]
    rows = [[_block(pen, cell, widths[c] - 2 * pen.pad, BODY_PT) for c, cell in enumerate(row)] for row in spec.rows]
    # 열마다 한 가지로 맞춘다: 모든 칸이 짧은 한 줄이면 가운데, 아니면 왼쪽(같은 열에서 줄마다 달라지지 않게)
    aligns = ["center" if all(len(row[c].lines) == 1 and pen.text_width(row[c].lines[0], body_font) < widths[c] * 0.5 for row in rows) else "left"
              for c in range(cols)]
    head_h = max(block.height(pen) for block in heads) + 2 * pen.pad
    row_hs = [max(block.height(pen) for block in row) + 2 * pen.pad for row in rows]
    height = head_h + sum(row_hs)
    image, draw = _canvas(pen.w, height + 2 * m)
    draw.rectangle((m, m, m + avail, m + head_h), fill=HEAD)
    x = m
    for c, block in enumerate(heads):
        _draw_block(draw, pen, block, x + pen.pad, m + (head_h - block.height(pen)) // 2, widths[c] - 2 * pen.pad)
        x += widths[c]
    y = m + head_h
    for row, h in zip(rows, row_hs):
        x = m
        for c, block in enumerate(row):
            _draw_block(draw, pen, block, x + pen.pad, y + (h - block.height(pen)) // 2, widths[c] - 2 * pen.pad,
                        align=aligns[c])
            x += widths[c]
        y += h
    thick = max(2, round(1.0 * pen.u))
    y = m + head_h
    draw.line((m, y, m + avail, y), fill=LINE, width=pen.line)
    for h in row_hs[:-1]:
        y += h
        draw.line((m, y, m + avail, y), fill=LINE, width=pen.line)
    x = m
    for w in widths[:-1]:
        x += w
        draw.line((x, m, x, m + height), fill=LINE, width=pen.line)
    draw.line((m, m, m + avail, m), fill=INK, width=thick)
    draw.line((m, m + height, m + avail, m + height), fill=INK, width=thick)
    return image


LAYOUTS = {"sequence": _sequence, "cycle": _cycle, "structure": _structure, "compare": _compare, "table": _table}


def render(spec, *, width_mm: float = DEFAULT_WIDTH, dpi: int = DEFAULT_DPI) -> Rendered:
    """명세 → PNG. spec은 Spec이나 JSON에서 읽은 dict(모양이 틀리면 SpecError)."""
    spec = read_spec(spec)
    if not WIDTH_RANGE[0] <= width_mm <= WIDTH_RANGE[1]:
        raise ValueError(f"놓을 폭은 {WIDTH_RANGE[0]:g}~{WIDTH_RANGE[1]:g}mm여야 합니다")
    if not DPI_RANGE[0] <= dpi <= DPI_RANGE[1]:
        raise ValueError(f"dpi는 {DPI_RANGE[0]}~{DPI_RANGE[1]}이어야 합니다")
    pen = _Pen(round(width_mm / 25.4 * dpi), int(dpi))
    image = LAYOUTS[spec.kind](pen, spec)
    out = io.BytesIO()
    image.save(out, "PNG", dpi=(dpi, dpi))
    return Rendered(out.getvalue(), image.width, image.height, int(dpi), Path(pen.regular_path).name)
