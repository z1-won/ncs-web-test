"""그림 식별자와 지각 해시. Pillow로 디코딩한다.

image_id  = RGB 픽셀 + 크기의 sha256 앞 16자 — BMP를 PNG로 다시 저장해도 같다(파일 바이트가 아니라 픽셀 기준).
phash     = 64비트 DCT 지각 해시(32×32 회색조 → 2차원 DCT → 왼쪽 위 8×8에서 중앙값 기준) — 16진 16자.
"""

from __future__ import annotations

import hashlib
import io
import math

from PIL import Image

SIZE, LOW = 32, 8
_COS = [[math.cos((2 * x + 1) * u * math.pi / (2 * SIZE)) for x in range(SIZE)] for u in range(LOW)]


def _open(data: bytes) -> Image.Image | None:
    if not data:
        return None
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:  # noqa: BLE001 — 깨진 그림은 식별하지 않는다(None)
        return None
    if image.mode in ("RGBA", "LA", "P", "PA"):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, "white")
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return image.convert("RGB")


def image_id(data: bytes) -> str | None:
    image = _open(data)
    if image is None:
        return None
    return hashlib.sha256(image.tobytes() + f"{image.size}".encode()).hexdigest()[:16]


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def phash(data: bytes) -> str | None:
    image = _open(data)
    if image is None:
        return None
    gray = image.convert("L").resize((SIZE, SIZE), Image.LANCZOS)
    pixels = list(gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata())
    rows = [pixels[y * SIZE:(y + 1) * SIZE] for y in range(SIZE)]
    # 분리 가능한 2차원 DCT의 왼쪽 위 8×8만 계산
    by_row = [[sum(row[x] * _COS[u][x] for x in range(SIZE)) for u in range(LOW)] for row in rows]
    coeffs = [sum(by_row[y][u] * _COS[v][y] for y in range(SIZE)) for v in range(LOW) for u in range(LOW)]
    ac = coeffs[1:]                                   # DC(평균 밝기) 제외하고 중앙값
    median = sorted(ac)[len(ac) // 2]
    bits = "".join("1" if c > median else "0" for c in coeffs)
    return f"{int(bits, 2):016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")
