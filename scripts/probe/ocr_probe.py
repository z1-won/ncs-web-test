"""그림 속 글자 읽기(OCR) 점검 — 엔진이 이 컴퓨터에서 도는지, 마크·워터마크 글자를 읽는지 본다(외부로 보내는 것 없음).

  set -a; source .env; set +a
  python scripts/probe/ocr_probe.py                       # 글자를 그려 넣은 점검 그림 2장(공공누리 마크 글자, 저작권·워터마크 글자)
  python scripts/probe/ocr_probe.py 그림1.jpg 그림2.png     # 내 그림으로
  python scripts/probe/ocr_probe.py --no-cache 그림.png    # 캐시(.llm_cache/ocr)를 쓰지 않고 다시 읽기

검수와 같은 길로 읽는다: 그림 하나를 다섯 모습(전체·위 띠·아래 띠·대비·옅은 층)으로 만들어 한 번에 읽고, 모습마다 읽은 줄과
그것을 합쳐 해석한 결과(공공누리 유형·저작권 문구·스톡 워터마크)를 보여 준다. 엔진은 ncs_figures.marks.pick_ocr가 고른 것
(FIG_OCR=windows|paddle, 비우면 자동). PaddleOCR은 처음 한 번 모델 파일을 내려받느라 오래 걸린다.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ncs_figures import marks  # noqa: E402

FONTS = ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
         "C:/Windows/Fonts/malgun.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
SAMPLES = (
    ("공공누리 마크 글자", ["OPEN 공공누리 공공저작물 자유이용허락", "출처표시 상업용금지 변경금지"], ["OPEN KOGL"]),
    ("저작권·워터마크 글자", ["무단 전재 및 재배포 금지", "Copyright 2026 All rights reserved", "shutterstock"],
     ["Copyright 2026 All rights reserved", "shutterstock"]),
)


def _font(size: int):
    from PIL import ImageFont
    for path in FONTS:
        if Path(path).is_file():
            return ImageFont.truetype(path, size), True
    return ImageFont.load_default(), False


def sample_images() -> list[tuple[str, bytes]]:
    """글자를 그려 넣은 점검 그림. 한글 글꼴을 못 찾으면 영문 줄만 그린다."""
    from PIL import Image, ImageDraw
    font, korean = _font(34)
    out = []
    for name, lines, fallback in SAMPLES:
        image = Image.new("RGB", (1100, 500), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 60, 1040, 300), outline="gray", width=3)
        for row, line in enumerate(lines if korean else fallback):
            draw.text((80, 330 + 50 * row), line, fill="black", font=font)
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        out.append((name + ("" if korean else " (한글 글꼴 없음 — 영문만)"), buffer.getvalue()))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("images", nargs="*", help="점검할 그림 파일. 없으면 글자를 그려 넣은 점검 그림")
    parser.add_argument("--no-cache", action="store_true", help="캐시를 쓰지 않고 다시 읽는다")
    args = parser.parse_args(argv)
    ocr, reason = marks.pick_ocr()
    if ocr is None:
        print(f"OCR을 쓸 수 없습니다 — {reason}")
        return 1
    print(f"엔진: {ocr.name}" + (f"  ({ocr.where()})" if hasattr(ocr, "where") else ""))
    pictures = [(path, Path(path).read_bytes()) for path in args.images] or sample_images()
    with tempfile.TemporaryDirectory() as scratch:
        if args.no_cache:
            ocr.cache = Path(scratch)
        jobs, keys = {}, []
        for name, data in pictures:
            key = hashlib.sha256(data).hexdigest()[:16]
            keys.append(key)
            for part, png in marks.views(data).items():
                jobs[f"{key}_{part}"] = png
        started = time.perf_counter()
        read = ocr.read_many(jobs)
        elapsed = time.perf_counter() - started
    print(f"그림 {len(pictures)}장(모습 {len(jobs)}개)을 {elapsed:.1f}초에 읽음" + (f"  — 마지막 오류: {ocr.last_error}" if ocr.last_error else ""))
    failed = 0
    for (name, _), key in zip(pictures, keys):
        print(f"\n■ {name}")
        merged: list[str] = []
        for part in marks.VIEWS:
            lines = read.get(f"{key}_{part}")
            print(f"  {part:9s} " + ("읽지 못함" if lines is None else " / ".join(lines) if lines else "(글자 없음)"))
            merged += lines or []
        if all(read.get(f"{key}_{part}") is None for part in marks.VIEWS):
            failed += 1
            continue
        found = marks.analyze(list(dict.fromkeys(merged)))
        kogl = "없음" if not found["kogl"] else f"있음(유형 {found['kogl_type'] or '못 읽음'}{', AI유형' if found['kogl_ai'] else ''})"
        print(f"  → 공공누리 마크 {kogl} · 저작권 문구 {found['copyright'] or '없음'} · 스톡 워터마크 {found['stock'] or '없음'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
