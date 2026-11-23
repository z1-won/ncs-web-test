"""② 그림 속 공공누리 마크·저작권 문구·스톡 워터마크 — 로컬 OCR로 그림 속 글자를 읽고 규칙으로 찾는다(외부 전송 없음).

OCR: Windows 내장 OCR(Windows.Media.Ocr, 한국어) — 설치·다운로드 없음. 다른 OCR(PaddleOCR·Tesseract)은 같은 read_many를 가진
클래스로 바꿔 끼운다. 결과는 그림(image_id)마다 캐시(.llm_cache/ocr)해 다시 돌릴 때 빠르다.

찾는 것(글자로 드러나는 것만):
- 공공누리 마크: '공공누리'·'KOGL'·'공공저작물 자유이용허락' + 조건 글자(출처표시·상업용금지·변경금지·자유이용·AI 학습)로 유형
- 저작권 문구: ©·Copyright·All rights reserved·무단 전재/복제·재배포 금지
- 스톡 사진 워터마크 글자: shutterstock·Getty·iStock·123RF·Alamy·Adobe Stock·Dreamstime·Depositphotos·클립아트코리아 등
못 찾는 것: 글자 없는 로고·무늬 워터마크, 너무 흐리거나 작은 글자 → 이미지 모델(로고 탐지·워터마크 판별)이 필요(설계 로컬 판독기).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from ncs_core.text import O, TRI

from .models import CheckOutcome

NAME = "②마크·워터마크"
SCRIPT = Path(__file__).with_name("data") / "win_ocr.ps1"
CACHE = Path(__file__).resolve().parents[2] / ".llm_cache" / "ocr"
MIN_SIDE = 1000                      # 작은 그림은 키워서 읽는다(Windows OCR은 글자가 작으면 못 읽음)
MAX_SIDE = 9500                      # Windows OCR 한도 10000px

KOGL = re.compile(r"공공누리|KOGL|공공저작물\s*자유\s*이용\s*허락", re.I)
# 모든 공공누리 마크에 '공공저작물 자유이용허락'이 들어 있으므로 '자유이용' 뒤에 '허락'이 오면 제0유형이 아니다.
# OCR이 흔히 틀리는 글자(출→줄, 처→저)도 받는다.
KOGL_LICENSE_PHRASE = re.compile(r"자\s*유\s*이\s*용\s*[허혀헤해]\s*[락낙라]")   # 모든 마크의 '자유이용허락' — 유형 판단 전에 뺀다
KOGL_FREE = re.compile(r"자\s*유\s*이\s*용|제\s*0\s*유형")
KOGL_AI = re.compile(r"AI\s*(학습|유형)|인공지능\s*학습")
KOGL_COMMERCIAL = re.compile(r"상\s*[업엽]\s*(용|적\s*이용)?\s*[금곰]\s*지|비\s*영\s*리")
KOGL_CHANGE = re.compile(r"[변번]\s*[경겸]\s*[금곰]\s*지")
KOGL_SOURCE = re.compile(r"[출줄춭]\s*[처저지져]\s*표\s*시|[처저]\s*표\s*시")
# OCR이 ©·영문을 흔히 틀리게 읽는다: ㉢·ⓒ, nghts·resetved·AII 등
COPYRIGHT = re.compile(r"©|Ⓒ|ⓒ|㉢|\([cC]\)\s*\d{4}|copy\s*right|r\s*[il1|]?\s*g?\s*hts\s*res|res[ea]?[rt]\s*ved|"
                       r"a[il1|]{2}\s*r[il1|n]?ghts|무단\s*(전재|복제|배포)|재\s*배포\s*금지|저작권\s*(자|소유|표시)", re.I)
STOCK = re.compile(r"shutter\s*stock|getty\s*images?|게티\s*이미지|istock|123\s*rf|alamy|adobe\s*stock|dreamstime|depositphotos|"
                   r"fotolia|bigstock|클립아트\s*코리아|이미지\s*투데이|imagetoday|freepik|pngtree", re.I)


def kogl_type(text: str) -> str | None:
    """마크 글자 → 기본 유형(0·1·2·3·4). 조건 글자를 못 읽으면 None. AI유형은 제1~4유형에 함께 붙는 표시라 kogl_ai로 따로 본다."""
    text = KOGL_LICENSE_PHRASE.sub(" ", text)
    if KOGL_FREE.search(text):
        return "0"
    commercial, change = bool(KOGL_COMMERCIAL.search(text)), bool(KOGL_CHANGE.search(text))
    if commercial and change:
        return "4"
    if change:
        return "3"
    if commercial:
        return "2"
    if KOGL_SOURCE.search(text):
        return "1"
    return None


def kogl_ai(text: str) -> bool:
    """AI유형 표시(인공지능 학습 이용 허용)가 함께 있나 — 2026.1 신설, 제1~4유형과 나란히 붙는다."""
    return bool(KOGL_AI.search(text))


def analyze(lines: list[str]) -> dict:
    """OCR 줄 → {'kogl': bool, 'kogl_type', 'kogl_ai', 'copyright': [..], 'stock': [..]}."""
    text = " ".join(lines)
    out = {"kogl": bool(KOGL.search(text)), "kogl_type": None, "kogl_ai": False, "copyright": [], "stock": []}
    if out["kogl"]:
        out["kogl_type"] = kogl_type(text)
        out["kogl_ai"] = kogl_ai(text)
    out["copyright"] = list(dict.fromkeys(m.group(0) for m in COPYRIGHT.finditer(text)))[:3]
    out["stock"] = list(dict.fromkeys(m.group(0) for m in STOCK.finditer(text)))[:3]
    return out


def _prepared_png(data: bytes) -> bytes | None:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = image.convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    w, h = image.size
    scale = 1.0
    if max(w, h) < MIN_SIDE:
        scale = min(MIN_SIDE / max(w, h), 4.0)
    if max(w, h) * scale > MAX_SIDE:
        scale = MAX_SIDE / max(w, h)
    if scale != 1.0:
        image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


VIEWS = ("full", "top", "bottom", "contrast", "light")
STRIP = 0.22                         # 위·아래 띠 높이 비율


def views(data: bytes) -> dict[str, bytes]:
    """OCR에 넣을 네 가지 모습(PNG). 띠는 작은 글자가 읽히게 두 배로 키운다."""
    from PIL import ImageEnhance, ImageOps
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = image.convert("RGB")
    except Exception:  # noqa: BLE001
        return {}
    w, h = image.size
    strip = max(1, int(h * STRIP))
    top, bottom = image.crop((0, 0, w, strip)), image.crop((0, h - strip, w, h))
    gray = ImageOps.grayscale(image)
    contrast = ImageEnhance.Contrast(gray).enhance(3.0)
    # 반투명 워터마크는 흰 바탕 위에서 옅은 회색이 된다 — 옅은 회색 층만 검게, 나머지는 희게 남겨 읽게 한다
    light = gray.point(lambda v: 0 if 150 <= v <= 228 else 255)
    out = {}
    for name, im in (("full", image), ("top", top.resize((w * 2, strip * 2))), ("bottom", bottom.resize((w * 2, strip * 2))),
                     ("contrast", contrast), ("light", light)):
        buffer = io.BytesIO()
        im.save(buffer, "PNG")
        out[name] = buffer.getvalue()
    return out


class WindowsOcr:
    """Windows 내장 OCR. 여러 그림을 PowerShell 한 번에 읽는다(시작에 1초 정도)."""

    name = "Windows OCR(ko)"

    @staticmethod
    def available() -> str:
        """쓸 수 없으면 이유, 쓸 수 있으면 ''."""
        if sys.platform != "win32":
            return "Windows가 아님 — 다른 OCR(PaddleOCR·Tesseract)을 붙여야 함"
        if not SCRIPT.is_file():
            return "OCR 스크립트가 없음"
        return ""

    def read_many(self, images: dict[str, bytes]) -> dict[str, list[str] | None]:
        out: dict[str, list[str] | None] = {}
        todo: dict[str, bytes] = {}
        for key, data in images.items():
            hit = CACHE / f"{key}.json"
            if hit.is_file():
                out[key] = json.loads(hit.read_text(encoding="utf-8"))
            else:
                todo[key] = data
        if not todo:
            return out
        CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for key, data in todo.items():
                png = _prepared_png(data)
                if png is None:
                    out[key] = None
                    continue
                path = Path(tmp) / f"{key}.png"
                path.write_bytes(png)
                paths[str(path)] = key
            if paths:
                listing = Path(tmp) / "list.txt"
                listing.write_text("\n".join(paths), encoding="utf-8")
                result = Path(tmp) / "out.json"
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                                "-ListFile", str(listing), "-OutFile", str(result)],
                               capture_output=True, timeout=60 + 3 * len(paths), check=False)
                read = json.loads(result.read_text(encoding="utf-8-sig")) if result.is_file() else {}
                for path, key in paths.items():
                    lines = read.get(path)
                    if isinstance(lines, str):
                        lines = [lines]
                    if lines and any(str(x).startswith("__ERROR__") for x in lines):
                        lines = None
                    out[key] = lines
                    if lines is not None:
                        (CACHE / f"{key}.json").write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
        return out


class MarkReader:
    """Resources.marks 자리. prefetch로 원고 그림을 한 번에 읽고, check에서 그림 하나의 결과를 준다."""

    def __init__(self, ocr=None):
        self.ocr = ocr or WindowsOcr()
        self.name = getattr(self.ocr, "name", "OCR")
        self.lines: dict[str, list[str] | None] = {}

    @staticmethod
    def _key(item) -> str:
        return item.image_id or hashlib.sha256(item.ctx.data or b"").hexdigest()[:16]

    def prefetch(self, items) -> None:
        """그림 하나를 네 번 읽어 합친다: 전체 / 위 띠 / 아래 띠(키워서) / 대비를 높인 전체.
        저작권 문구·워터마크는 가장자리에 작게, 또는 흐리게 들어가 전체 그림 한 번으로는 잘 안 읽힌다."""
        todo = [i for i in items if i.ctx.data and self._key(i) not in self.lines]
        if not todo:
            return
        jobs: dict[str, bytes] = {}
        for item in todo:
            for part, data in views(item.ctx.data).items():
                jobs[f"{self._key(item)}_{part}"] = data
        read = self.ocr.read_many(jobs)
        for item in todo:
            key = self._key(item)
            parts = [read.get(f"{key}_{part}") for part in VIEWS]
            if all(p is None for p in parts):
                self.lines[key] = None
            else:
                self.lines[key] = list(dict.fromkeys(line for p in parts if p for line in p))

    def read(self, item) -> list[str] | None:
        key = self._key(item)
        if key not in self.lines:
            self.prefetch([item])
        return self.lines.get(key)


def open_marks():
    """쓸 수 있으면 MarkReader, 아니면 None(② 미실행)."""
    if os.getenv("FIG_OCR", "1") == "0" or WindowsOcr.available():
        return None
    return MarkReader()


def check_marks(item, res, cfg, prior) -> list[CheckOutcome]:
    lines = res.marks.read(item)
    if lines is None:
        return [CheckOutcome(NAME, None, skipped="OCR로 그림을 읽지 못함")]
    found = analyze(lines)
    prior["ocr_lines"] = lines
    prior["marks_found"] = found               # 위험도 규칙(H1 저작권 문구·H5 스톡 워터마크)이 쓴다
    notes, value, fixes = [], O, []
    if found["kogl"]:
        stated = item.source.kogl_type if item.source else None
        if stated == "AI":
            stated = None                                    # 출처에 AI유형만 적힌 경우 — 기본 유형은 모름
        seen = found["kogl_type"]
        if found["kogl_ai"]:
            notes.append("그림 속 공공누리 마크에 AI유형(인공지능 학습 이용 허용) 표시도 있음")
        if seen is None:
            value = TRI
            notes.append("그림 속에 공공누리 마크가 보이나 유형을 못 읽음 — 출처의 공공누리 유형과 맞는지 확인")
        elif stated is None:
            value = TRI
            notes.append(f"그림 속 공공누리 제{seen}유형 마크가 있는데 출처 줄에 공공누리 유형 표기가 없음")
            fixes.append(f"출처에 '공공누리 제{seen}유형' 표기 추가")
        elif stated != seen:
            value = TRI
            notes.append(f"그림 속 공공누리 마크는 제{seen}유형인데 출처 줄은 제{stated}유형")
            fixes.append("출처의 공공누리 유형을 원 저작물 마크와 맞추기")
        else:
            notes.append(f"그림 속 공공누리 제{seen}유형 마크 — 출처 표기와 같음")
    if found["copyright"]:
        value = TRI
        notes.append(f"그림 속 저작권 문구: {', '.join(found['copyright'])} — 저작권자 이용허락 확인")
        fixes.append("저작권 문구가 있는 그림은 이용허락을 확인하거나 다른 그림으로 바꾸기")
    if found["stock"]:
        value = TRI
        notes.append(f"그림 속 스톡 사진 워터마크 글자: {', '.join(found['stock'])} — 구매·이용허락 확인")
        fixes.append("워터마크가 있는 스톡 그림은 정식 구매본으로 바꾸거나 다른 그림으로 바꾸기")
    if not notes:
        notes.append("그림 속 글자에서 공공누리 마크·저작권 문구·워터마크 글자 없음 (OCR — 글자 없는 로고·무늬 워터마크는 못 봄)")
    return [CheckOutcome(NAME, value, " / ".join(notes), suggestion=" / ".join(fixes) or None, model=res.marks.name)]
