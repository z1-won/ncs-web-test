"""② 그림 속 공공누리 마크·저작권 문구·스톡 워터마크 — 로컬 OCR로 그림 속 글자를 읽고 규칙으로 찾는다(외부 전송 없음).

OCR 엔진은 둘이고 같은 read_many를 가진 클래스라 바꿔 끼운다(pick_ocr가 고른다 — FIG_OCR=windows|paddle|0, 비우면 자동):
- Windows 내장 OCR(Windows.Media.Ocr, 한국어) — 설치·다운로드 없음. Windows에서만. 자동일 때 Windows면 이것.
- PaddleOCR(검출 PP-OCRv5_server_det + 인식 korean_PP-OCRv5_mobile_rec) — macOS·Linux·Windows. data/paddle_ocr.py를
  따로 돌린다(paddlepaddle이 검수 서버의 파이썬 3.14용으로는 나오지 않기 때문). 돌리는 곳은 차례로:
    FIG_OCR_DOCKER=이미지   도커 이미지(docker/ocr/Dockerfile — 모델이 들어 있어 --network none으로 돈다)
    FIG_OCR_PYTHON=경로     PaddleOCR을 깐 파이썬
    저장소의 .venv-ocr      같은 것을 정해 둔 자리에 둔 경우
    지금 파이썬             paddleocr이 깔려 있을 때(3.13 이하)
  도커가 아니면 모델 파일을 처음 한 번 내려받는다(그때만 네트워크). 모델을 바꾸려면 FIG_OCR_DET·FIG_OCR_REC
  (도커는 그 모델이 든 이미지를 --build-arg로 다시 만들어야 한다).
  모델을 돌리는 엔진은 FIG_OCR_ENGINE(paddle·onnxruntime). 비우면 도커는 onnxruntime, 그 밖은 PaddleOCR 기본(paddle) —
  리눅스 ARM64(Apple Silicon의 도커)에서 paddle 엔진이 읽다가 Segmentation fault로 죽기 때문이다(data/paddle_ocr.py 머리말).
결과는 그림(image_id)마다 엔진별로 캐시(.llm_cache/ocr, PaddleOCR은 그 아래 paddle*)해 다시 돌릴 때 빠르다.

찾는 것(글자로 드러나는 것만):
- 공공누리 마크: '공공누리'·'KOGL'·'공공저작물 자유이용허락' + 조건 글자(출처표시·상업용금지·변경금지·자유이용·AI 학습)로 유형
- 저작권 문구: ©·Copyright·All rights reserved·무단 전재/복제·재배포 금지
- 스톡 사진 워터마크 글자: shutterstock·Getty·iStock·123RF·Alamy·Adobe Stock·Dreamstime·Depositphotos·클립아트코리아 등
못 찾는 것: 글자 없는 로고·무늬 워터마크, 너무 흐리거나 작은 글자 → 이미지 모델(로고 탐지·워터마크 판별)이 필요(설계 로컬 판독기).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from ncs_core.text import O, TRI

from .models import CheckOutcome

NAME = "②마크·워터마크"
SCRIPT = Path(__file__).with_name("data") / "win_ocr.ps1"
PADDLE_SCRIPT = Path(__file__).with_name("data") / "paddle_ocr.py"
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".llm_cache" / "ocr"
PADDLE_ENV = ".venv-ocr"             # 저장소 바로 아래에 두는 PaddleOCR용 가상 환경(FIG_OCR_PYTHON이 없을 때 찾는 곳)
DOCKER_WORK, DOCKER_SCRIPTS = "/work", "/ocr"   # 컨테이너 안에서 보이는 자리: 읽을 그림과 결과 / data 폴더(읽기 전용)
PADDLE_DET, PADDLE_REC = "PP-OCRv5_server_det", "korean_PP-OCRv5_mobile_rec"   # PaddleOCR 3.7의 lang="korean" 기본 짝
OFF = frozenset({"0", "off", "false", "no"})
ERROR_MARK = "__ERROR__"
MIN_SIDE = 1000                      # 작은 그림은 키워서 읽는다(Windows OCR은 글자가 작으면 못 읽음)
MAX_SIDE = 9500                      # Windows OCR 한도 10000px

KOGL = re.compile(r"공공누리|KOGL|공공저작물\s*자유\s*이용\s*허락", re.I)
# 모든 공공누리 마크에 '공공저작물 자유이용허락'이 들어 있으므로 '자유이용' 뒤에 '허락'이 오면 제0유형이 아니다.
# OCR이 흔히 틀리는 글자(출→줄, 처→저)도 받는다. '금지→금시'는 PaddleOCR이 키운 아래 띠에서 낸 오인식(2026-11-23 점검 그림).
KOGL_LICENSE_PHRASE = re.compile(r"자\s*유\s*이\s*용\s*[허혀헤해]\s*[락낙라]")   # 모든 마크의 '자유이용허락' — 유형 판단 전에 뺀다
KOGL_FREE = re.compile(r"자\s*유\s*이\s*용|제\s*0\s*유형")
KOGL_AI = re.compile(r"AI\s*(학습|유형)|인공지능\s*학습")
KOGL_COMMERCIAL = re.compile(r"상\s*[업엽]\s*(용|적\s*이용)?\s*[금곰]\s*[지시]|비\s*영\s*리")
KOGL_CHANGE = re.compile(r"[변번]\s*[경겸]\s*[금곰]\s*[지시]")
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


class _BatchOcr:
    """그림 여러 장을 바깥 프로그램 한 번에 읽는 OCR의 공통 부분 — 캐시, 임시 파일, 결과 읽기. 엔진은 _run만 정한다.

    last_error: 가장 최근에 읽지 못한 까닭(엔진을 못 올림·시간 초과 등). 점검의 '미실행' 사유에 그대로 실린다."""

    name = "OCR"
    cache = CACHE

    def __init__(self):
        self.last_error = ""

    def _run(self, listing: Path, result: Path, count: int) -> None:
        raise NotImplementedError

    def read_many(self, images: dict[str, bytes]) -> dict[str, list[str] | None]:
        out: dict[str, list[str] | None] = {}
        todo: dict[str, bytes] = {}
        for key, data in images.items():
            hit = self.cache / f"{key}.json"
            if hit.is_file():
                out[key] = json.loads(hit.read_text(encoding="utf-8"))
            else:
                todo[key] = data
        if not todo:
            return out
        self.cache.mkdir(parents=True, exist_ok=True)
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
                try:
                    self._run(listing, result, len(paths))
                except subprocess.TimeoutExpired:
                    self.last_error = f"{self.name}이(가) 제한 시간 안에 끝나지 않음(그림 {len(paths)}장)"
                except OSError as error:
                    self.last_error = f"{self.name}을(를) 실행하지 못함: {error}"[:300]
                read = json.loads(result.read_text(encoding="utf-8-sig")) if result.is_file() else {}
                if not read and not self.last_error:
                    self.last_error = f"{self.name}이(가) 결과를 내지 않음"
                for path, key in paths.items():
                    lines = read.get(path)
                    if isinstance(lines, str):
                        lines = [lines]
                    failed = next((str(x) for x in lines or [] if str(x).startswith(ERROR_MARK)), None)
                    if failed is not None:
                        self.last_error = failed[len(ERROR_MARK):].strip()
                        lines = None
                    out[key] = lines
                    if lines is not None:
                        (self.cache / f"{key}.json").write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
        return out


class WindowsOcr(_BatchOcr):
    """Windows 내장 OCR. 여러 그림을 PowerShell 한 번에 읽는다(시작에 1초 정도)."""

    name = "Windows OCR(ko)"

    @staticmethod
    def available() -> str:
        """쓸 수 없으면 이유, 쓸 수 있으면 ''."""
        if sys.platform != "win32":
            return "Windows가 아님"
        if not SCRIPT.is_file():
            return "OCR 스크립트가 없음"
        return ""

    def _run(self, listing: Path, result: Path, count: int) -> None:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                        "-ListFile", str(listing), "-OutFile", str(result)],
                       capture_output=True, timeout=60 + 3 * count, check=False)


class PaddleOcr(_BatchOcr):
    """PaddleOCR(PP-OCRv5 한국어). 도커 이미지나 PaddleOCR을 깐 파이썬으로 data/paddle_ocr.py를 한 번 돌려 여러 그림을 읽는다.

    모델을 올리는 데 몇 초, 그림 한 장에 CPU로 1초 안팎에서 몇 초가 든다(그림 하나를 다섯 모습으로 읽으므로 그 다섯 배).
    처음 한 번은 모델 파일을 내려받느라 더 걸린다. 읽은 결과는 캐시에 남아 같은 그림은 다시 읽지 않는다."""

    def __init__(self):
        super().__init__()
        self.det = os.getenv("FIG_OCR_DET", "").strip()
        self.rec = os.getenv("FIG_OCR_REC", "").strip()
        self.engine = os.getenv("FIG_OCR_ENGINE", "").strip() or ("onnxruntime" if self.docker_image() else "")
        self.name = f"PaddleOCR({self.rec or PADDLE_REC}{', Docker' if self.docker_image() else ''})"
        if self.det or self.rec:      # 모델을 바꾸면 읽은 글도 달라지므로 캐시를 따로 둔다
            tag = hashlib.sha256(f"{self.det}|{self.rec}".encode()).hexdigest()[:8]
            self.cache = CACHE / f"paddle_{tag}"
        else:
            self.cache = CACHE / "paddle"

    @staticmethod
    def docker_image() -> str:
        """FIG_OCR_DOCKER에 적은 이미지 이름. 적지 않았으면 ''(도커를 쓰지 않는다)."""
        return os.getenv("FIG_OCR_DOCKER", "").strip()

    @classmethod
    def where(cls) -> str:
        """어디서 도는지 한 줄(점검 스크립트·로그용)."""
        image = cls.docker_image()
        return f"도커 이미지 {image}" if image else f"파이썬 {cls.python() or '없음'}"

    @staticmethod
    def python() -> str:
        """PaddleOCR을 돌릴 파이썬 경로(도커를 쓰지 않을 때). 없으면 ''."""
        chosen = os.getenv("FIG_OCR_PYTHON", "").strip()
        if chosen:
            path = Path(chosen).expanduser()
            for candidate in (path, ROOT / path):
                if candidate.is_file():
                    return str(candidate)
            return shutil.which(chosen) or ""
        for candidate in (ROOT / PADDLE_ENV / "bin" / "python", ROOT / PADDLE_ENV / "Scripts" / "python.exe"):
            if candidate.is_file():
                return str(candidate)
        try:
            here = importlib.util.find_spec("paddleocr") is not None
        except (ImportError, ValueError):
            here = False
        return sys.executable if here else ""

    @classmethod
    def available(cls) -> str:
        """쓸 수 없으면 이유, 쓸 수 있으면 ''. 그 파이썬에서 paddleocr이 실제로 올라오는지는 읽을 때 드러난다(last_error)."""
        if not PADDLE_SCRIPT.is_file():
            return "PaddleOCR 스크립트가 없음"
        if cls.docker_image():      # 이미지가 있는지·도커가 켜져 있는지는 읽을 때 드러난다(시작할 때마다 도커에 묻지 않는다)
            return "" if shutil.which("docker") else "FIG_OCR_DOCKER를 적었는데 docker 명령이 없음(Docker Desktop 설치·실행 확인)"
        if cls.python():
            return ""
        chosen = os.getenv("FIG_OCR_PYTHON", "").strip()
        if chosen:
            return f"FIG_OCR_PYTHON이 가리키는 파이썬이 없음({chosen})"
        return f"PaddleOCR을 돌릴 곳이 없음(FIG_OCR_DOCKER, FIG_OCR_PYTHON 또는 {PADDLE_ENV} — docs/WEB.md '그림 속 글자 읽기')"

    def _models(self) -> list[str]:
        return [*(["--engine", self.engine] if self.engine else []),
                *(["--det", self.det] if self.det else []), *(["--rec", self.rec] if self.rec else [])]

    def _run(self, listing: Path, result: Path, count: int) -> None:
        if self.docker_image():
            return self._run_docker(listing, result, count)
        command = [self.python(), str(PADDLE_SCRIPT), "--list", str(listing), "--out", str(result), *self._models()]
        done = subprocess.run(command, capture_output=True, timeout=300 + 20 * count, check=False,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self._note_failure(done, result)

    def _run_docker(self, listing: Path, result: Path, count: int) -> None:
        """컨테이너 한 번으로 읽는다. 그림이 든 임시 폴더를 /work에, data 폴더를 /ocr(읽기 전용)에 붙이고 네트워크는 끊는다.
        호스트 경로는 컨테이너 안에서 다르므로(Windows의 C:\\… 등) 목록을 /work 기준으로 다시 쓰고, 결과의 경로를 되돌려 놓는다."""
        work = listing.parent
        inside = {f"{DOCKER_WORK}/{Path(path).name}": path for path in listing.read_text(encoding="utf-8").splitlines() if path}
        (work / "list.docker.txt").write_text("\n".join(inside), encoding="utf-8")
        answer = work / "out.docker.json"
        command = ["docker", "run", "--rm", "--pull", "never", "--network", "none",
                   "-v", f"{work}:{DOCKER_WORK}", "-v", f"{PADDLE_SCRIPT.parent}:{DOCKER_SCRIPTS}:ro",
                   self.docker_image(), "python", f"{DOCKER_SCRIPTS}/{PADDLE_SCRIPT.name}",
                   "--list", f"{DOCKER_WORK}/list.docker.txt", "--out", f"{DOCKER_WORK}/{answer.name}", *self._models()]
        done = subprocess.run(command, capture_output=True, timeout=300 + 20 * count, check=False)
        if answer.is_file():
            read = json.loads(answer.read_text(encoding="utf-8-sig"))
            result.write_text(json.dumps({inside[path]: lines for path, lines in read.items() if path in inside}, ensure_ascii=False),
                              encoding="utf-8")
        self._note_failure(done, result)

    def _note_failure(self, done, result: Path) -> None:
        if done.returncode and not result.is_file():      # 스크립트가 결과를 쓰기 전에 죽은 경우: import 실패, 이미지 없음, 도커가 꺼져 있음
            text = (done.stderr or b"").decode("utf-8", "replace")
            if "Segmentation fault" in text or done.returncode in (139, -11):
                self.last_error = ("PaddleOCR이 읽는 도중 Segmentation fault로 죽음 — 리눅스 ARM64의 paddle 엔진 문제일 수 있음"
                                   "(FIG_OCR_ENGINE=onnxruntime, 도커는 이미지를 다시 만들 것)")
                return
            tail = text.strip().splitlines()
            self.last_error = f"PaddleOCR 실행 실패: {tail[-1] if tail else f'종료 코드 {done.returncode}'}"[:300]


class MarkReader:
    """Resources.marks 자리. prefetch로 원고 그림을 한 번에 읽고, check에서 그림 하나의 결과를 준다."""

    def __init__(self, ocr=None):
        self.ocr = ocr or pick_ocr()[0] or WindowsOcr()
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

    @property
    def error(self) -> str:
        """읽지 못했을 때 엔진이 남긴 까닭(없으면 '')."""
        return getattr(self.ocr, "last_error", "") or ""


def pick_ocr() -> tuple[object | None, str]:
    """(쓸 OCR 엔진, 못 쓰는 까닭). FIG_OCR: 0이면 끔, windows·paddle이면 그 엔진만, 그 밖(기본 1)은 자동.
    자동은 Windows면 내장 OCR(전부터 쓰던 것 — 캐시와 결과가 그대로다), 아니면 PaddleOCR."""
    choice = os.getenv("FIG_OCR", "1").strip().lower()
    if choice in OFF:
        return None, "FIG_OCR=0으로 꺼 둠"
    if choice in ("paddle", "paddleocr"):
        reason = PaddleOcr.available()
        return (None, reason) if reason else (PaddleOcr(), "")
    if choice in ("windows", "win"):
        reason = WindowsOcr.available()
        return (None, reason) if reason else (WindowsOcr(), "")
    windows = WindowsOcr.available()
    if not windows:
        return WindowsOcr(), ""
    paddle = PaddleOcr.available()
    if not paddle:
        return PaddleOcr(), ""
    return None, f"쓸 수 있는 OCR이 없음 — Windows 내장 OCR: {windows} / PaddleOCR: {paddle}"


def why_not() -> str:
    """② 그림 속 글자 읽기를 못 하는 까닭(화면·로그에 그대로 보일 글). 할 수 있으면 ''."""
    return pick_ocr()[1]


def open_marks():
    """쓸 수 있으면 MarkReader, 아니면 None(② 미실행 — 까닭은 why_not())."""
    ocr, _ = pick_ocr()
    return MarkReader(ocr) if ocr is not None else None


def check_marks(item, res, cfg, prior) -> list[CheckOutcome]:
    lines = res.marks.read(item)
    if lines is None:
        reason = getattr(res.marks, "error", "")
        return [CheckOutcome(NAME, None, skipped="OCR로 그림을 읽지 못함" + (f" — {reason}" if reason else ""))]
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
