"""그림 고르기 → 업스케일 → 같은 자리에 넣은 hwpx 사본 만들기.

1. plan: picture_records()의 그림을 BinData별로 묶고(같은 그림 파일을 여러 곳에서 쓰면 한 번만), 가장 크게 출력되는 자리 기준
   실효 DPI가 목표 미만인 그림만 고른다. 필요 배율 = 목표 DPI ÷ 원본 DPI, 엔진 배율은 그 이상인 가장 작은 것(max_scale까지).
2. upscale: 원본을 PNG로 바꿔(엔진은 BMP를 못 읽음) 배율별로 엔진을 한 번씩 부르고, 결과를 필요 픽셀에 맞게 Lanczos로 줄인다.
   필요 배율보다 작은 배율밖에 못 쓰면 줄이지 않고 그대로 두고 '목표 미달'로 표시한다.
   엔진에는 그림 픽셀 수에 비례한 시간 제한을 두고, 묶음 실행이 실패하면(오류·시간 초과) 그림을 한 장씩 다시 돌려
   문제 그림 하나 때문에 나머지가 같이 실패하지 않게 한다. 실행 중에는 결과 파일 수로 진행 상황을 알린다.
   결과를 원본 크기로 줄여 원본과 비교한다 — 엔진이 오류 없이 이상한 그림을 내는 경우가 있다(Real-CUGAN: 검은 그림, 일부만 망가진 그림).
   그림 전체 평균만 보면 흰 바탕이 많은 도표에서 일부가 망가져도 작게 나오므로 16px 칸마다(내용이 있는 칸만) 평균 차도 본다.
   기준(도표 표본 4장 × 13개 모델 결과로 정함): 정상 결과의 칸 최대 차는 waifu2x 15 이하, Real-ESRGAN 35 이하였고
   일부가 망가진 Real-CUGAN 결과는 188, 글자가 번진 결과는 49였다.
     실패  전체 평균 차 > 40 또는 칸 최대 차 > 80   (망가진 결과 — 제안본에 넣지 않음)
     확인  칸 최대 차 > 40                         (제안본에는 넣고 비고에 '사람 확인' 표시)
3. write: BinData 파일만 바꾼 hwpx를 만든다. <hp:sz>(쪽 위 출력 크기)·imgDim·imgClip은 그대로 두고,
   그림 파일의 DPI 정보를 배율만큼 올려 그림의 '원래 크기(인치)'가 변하지 않게 한다. BMP·GIF는 PNG로 바꾸고 content.hpf의
   href·media-type을 고친다. zip 항목 순서와 압축 방식은 원본 그대로(mimetype이 첫 항목·무압축이어야 한글이 연다).
"""

from __future__ import annotations

import io
import math
import re
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageStat

from .engine import Engine

DEFAULT_TARGET_DPI = 300
DEFAULT_MIN_DPI = 200          # 판정 표시용: 이보다 낮으면 X, 목표 미만이면 △ (설계 메모 1절 제안 기준)
DEFAULT_FILE_DPI = 96          # 그림 파일에 DPI 정보가 없을 때 한글이 쓰는 값
MAX_MEAN_DIFF = 40             # 결과를 원본 크기로 줄였을 때 원본과의 평균 밝기 차(0~255)가 이보다 크면 실패
TILE = 16                      # 칸 비교 크기(원본 픽셀)
FLAT_TILE = 30                 # 원본 칸의 밝기 범위가 이보다 작으면 바탕 칸으로 보고 비교하지 않음
MAX_TILE_DIFF = 80             # 내용 칸 하나의 평균 차가 이보다 크면 실패(일부가 망가진 결과)
WARN_TILE_DIFF = 40            # 이보다 크면 제안본에는 넣되 사람 확인 표시
TIMEOUT_BASE = 120             # 엔진 시간 제한(초) = 기본 + 입력 백만 픽셀당 × 배율²
TIMEOUT_PER_MPX = 150          # waifu2x x2 실측 약 70초/백만 px(Iris Plus)의 약 8배 여유
PROGRESS_EVERY = 5             # 진행 상황 확인 간격(초)
MANIFEST = "Contents/content.hpf"
RUN_AS_PNG = {"bmp", "gif"}    # 이 형식은 PNG로 바꿔 넣는다(BMP는 용량이 너무 크고, 엔진 결과도 PNG)


def grade(dpi: int | None, target_dpi: int = DEFAULT_TARGET_DPI, min_dpi: int = DEFAULT_MIN_DPI) -> str:
    if dpi is None:
        return "판단불가"
    return "O" if dpi >= target_dpi else "△" if dpi >= min_dpi else "X"


@dataclass
class Job:
    """BinData 하나(그림 파일 하나)에 대한 업스케일 작업."""
    bin_id: str
    href: str
    format: str
    px: tuple[int, int]
    data: bytes
    uses: list[dict]                       # 이 그림 파일을 쓰는 picture_records 항목들
    dpi: int                               # 가장 크게 출력되는 자리의 실효 DPI(= 가장 낮은 DPI)
    need: float                            # 필요 배율 = 목표 DPI ÷ dpi
    scale: int                             # 엔진 배율
    status: str = "대기"                   # 대기 / 완료 / 실패
    note: str = ""
    out_px: tuple[int, int] = (0, 0)
    out_dpi: int | None = None
    new_href: str = ""
    new_data: bytes = b""
    media_type: str = ""
    seconds: float = 0.0
    diff: float | None = None              # 원본과의 전체 평균 밝기 차
    tile_diff: float | None = None         # 내용 칸 중 가장 큰 평균 밝기 차
    preview: dict = field(default_factory=dict)   # {'before': png bytes, 'after': png bytes}

    @property
    def reaches_target(self) -> bool:
        return self.scale >= self.need


def plan(records: list[dict], binaries: dict[str, dict], engine: Engine, *, target_dpi: int = DEFAULT_TARGET_DPI,
         max_scale: int = 2) -> tuple[list[Job], list[dict]]:
    """(업스케일할 작업, 건너뛴 그림 [{'record', '이유'}]). 목표 이상인 그림은 어느 쪽에도 넣지 않는다.
    binaries = Document.binaries ({BinData id: {'href', 'bytes'}})."""
    by_bin: dict[str, list[dict]] = {}
    skipped = []
    for r in records:
        if not r["bin_id"] or not r["data"]:
            skipped.append({"record": r, "이유": "그림 파일 없음"})
        elif r["dpi"] is None or not r["format"]:
            skipped.append({"record": r, "이유": f"그림 형식을 읽지 못함({r['format'] or '알 수 없음'})"})
        else:
            by_bin.setdefault(r["bin_id"], []).append(r)
    jobs = []
    for bin_id, uses in by_bin.items():
        dpi = min(u["dpi"] for u in uses)
        if dpi >= target_dpi:
            continue
        need = target_dpi / dpi
        first = uses[0]
        jobs.append(Job(bin_id=bin_id, href=(binaries.get(bin_id) or {}).get("href") or "", format=first["format"],
                        px=first["px"], data=first["data"], uses=uses, dpi=dpi, need=need,
                        scale=engine.pick_scale(need, max_scale)))
    return jobs, skipped


def upscale(jobs: list[Job], engine: Engine, *, tools: Path | None = None,
            runner: Callable[[Path, Path, int], None] | None = None, progress: Callable[[str], None] = print) -> None:
    """jobs를 제자리에서 채운다(status·new_data·out_px …). runner(src, out, scale)는 테스트용 엔진 대역."""
    if runner is None:
        def run(src: Path, out: Path, scale: int, timeout: float) -> None:
            engine.run(src, out, scale, tools, timeout)
    else:
        def run(src: Path, out: Path, scale: int, timeout: float) -> None:
            runner(src, out, scale)
    by_scale: dict[int, list[Job]] = {}
    for job in jobs:
        by_scale.setdefault(job.scale, []).append(job)
    with tempfile.TemporaryDirectory(prefix="ncs_upscale_") as temp:
        work = Path(temp)
        for scale, group in sorted(by_scale.items()):
            originals = {}
            for i, job in enumerate(group):
                try:
                    image = Image.open(io.BytesIO(job.data))
                    image.load()
                except Exception as error:  # noqa: BLE001 — 깨진 그림 하나 때문에 전체를 멈추지 않는다
                    job.status, job.note = "실패", f"그림을 열지 못함: {error}"
                    continue
                originals[i] = image
            if not originals:
                continue
            src, out = _stage(work / f"in_x{scale}", work / f"out_x{scale}", originals)
            progress(f"  x{scale} 그림 {len(originals)}장 업스케일 중 ({engine.name})…")
            started = time.perf_counter()
            try:
                _watched(run, src, out, scale, _timeout(originals.values(), scale), len(originals), progress)
            except Exception as error:  # noqa: BLE001
                if len(originals) == 1 or isinstance(error, FileNotFoundError):
                    for i in originals:
                        group[i].status, group[i].note = "실패", str(error)
                    continue
                progress(f"  묶음 실행 실패({error}) — 한 장씩 다시 시도")
                _one_by_one(run, work, scale, group, originals, progress)
                continue
            each = (time.perf_counter() - started) / len(originals)
            for i, image in originals.items():
                group[i].seconds = each
                _collect(group[i], image, out / f"{i:04d}.png")


def _stage(src: Path, out: Path, originals: dict[int, Image.Image]) -> tuple[Path, Path]:
    """엔진 입력 폴더에 RGB PNG로 저장(엔진은 BMP를 못 읽음)하고 빈 출력 폴더를 만든다."""
    src.mkdir()
    out.mkdir()
    for i, image in originals.items():
        _rgb(image).save(src / f"{i:04d}.png")
    return src, out


def _timeout(images, scale: int) -> float:
    mpx = sum(image.width * image.height for image in images) / 1_000_000
    return TIMEOUT_BASE + TIMEOUT_PER_MPX * mpx * scale * scale


def _watched(run, src: Path, out: Path, scale: int, timeout: float, total: int, progress) -> None:
    """엔진을 돌리는 동안 출력 폴더의 결과 파일 수로 진행 상황을 알린다(바뀔 때만)."""
    stop = threading.Event()
    started = time.perf_counter()

    shown = 0

    def report() -> None:
        nonlocal shown
        done = sum(1 for _ in out.glob("*.png"))
        if done != shown:
            shown = done
            elapsed = int(time.perf_counter() - started)
            progress(f"    {done}/{total}장 ({elapsed // 60}분 {elapsed % 60}초)")

    def watch() -> None:
        while not stop.wait(PROGRESS_EVERY):
            report()

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        run(src, out, scale, timeout)
    finally:
        stop.set()
        watcher.join()
    report()                                   # 마지막 장은 확인 간격 사이에 끝나므로 끝난 뒤 한 번 더


def _one_by_one(run, work: Path, scale: int, group: list[Job], originals: dict[int, Image.Image], progress) -> None:
    """묶음 실행이 실패했을 때 그림을 한 장씩 다시 돌린다 — 문제 그림만 실패로 남는다."""
    for n, (i, image) in enumerate(originals.items(), 1):
        job = group[i]
        src, out = _stage(work / f"in_x{scale}_{i:04d}", work / f"out_x{scale}_{i:04d}", {i: image})
        started = time.perf_counter()
        try:
            run(src, out, scale, _timeout([image], scale))
        except Exception as error:  # noqa: BLE001
            job.status, job.note = "실패", str(error)
            progress(f"    {n}/{len(originals)}장 {job.bin_id} 실패: {error}")
            continue
        job.seconds = time.perf_counter() - started
        _collect(job, image, out / f"{i:04d}.png")
        progress(f"    {n}/{len(originals)}장 {job.bin_id} {job.status}")


def _collect(job: Job, original: Image.Image, result: Path) -> None:
    if not result.exists():
        job.status, job.note = "실패", "엔진 결과 파일이 없음"
        return
    with Image.open(result) as raw:
        _finish(job, original, raw.convert("RGB"))


def compare(original: Image.Image, upscaled: Image.Image) -> tuple[float, float]:
    """(전체 평균 밝기 차, 내용 칸 중 가장 큰 평균 밝기 차). upscaled를 원본 크기로 줄여 비교한다.
    바탕만 있는 칸(밝기 범위 < FLAT_TILE)은 칸 비교에서 뺀다 — 흰 바탕의 작은 차이가 섞여 기준이 흐려지지 않게."""
    base = _rgb(original).convert("L")
    back = upscaled.resize(base.size, Image.LANCZOS).convert("L")
    diff = ImageChops.difference(base, back)
    worst = 0.0
    width, height = base.size
    for y in range(0, height, TILE):
        for x in range(0, width, TILE):
            box = (x, y, min(x + TILE, width), min(y + TILE, height))
            low, high = base.crop(box).getextrema()
            if high - low >= FLAT_TILE:
                worst = max(worst, ImageStat.Stat(diff.crop(box)).mean[0])
    return ImageStat.Stat(diff).mean[0], worst


def _rgb(image: Image.Image) -> Image.Image:
    if image.mode in ("RGB", "L"):
        return image.convert("RGB")
    if image.mode in ("RGBA", "LA", "P", "PA"):   # 투명 부분은 흰 바탕으로
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, "white")
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return image.convert("RGB")


def _finish(job: Job, original: Image.Image, upscaled: Image.Image) -> None:
    pw, ph = job.px
    if upscaled.size != (pw * job.scale, ph * job.scale):
        job.status, job.note = "실패", f"결과 크기가 예상과 다름({upscaled.size[0]}×{upscaled.size[1]})"
        return
    base = _rgb(original)
    job.diff, job.tile_diff = compare(base, upscaled)
    if job.diff > MAX_MEAN_DIFF:
        job.status, job.note = "실패", f"결과가 원본과 크게 다름(평균 밝기 차 {job.diff:.0f}) — 검은 그림 등 엔진 오류로 봄"
        return
    if job.tile_diff > MAX_TILE_DIFF:
        job.status, job.note = "실패", f"결과 일부가 원본과 크게 다름(칸 최대 차 {job.tile_diff:.0f}) — 엔진 오류로 봄"
        return
    factor = min(job.need, job.scale)
    size = (max(1, math.ceil(pw * factor)), max(1, math.ceil(ph * factor)))
    final = upscaled if size == upscaled.size else upscaled.resize(size, Image.LANCZOS)
    job.out_px = final.size
    job.out_dpi = math.floor(job.dpi * final.size[0] / pw)
    file_dpi = original.info.get("dpi") or (DEFAULT_FILE_DPI, DEFAULT_FILE_DPI)
    new_dpi = (float(file_dpi[0]) * final.size[0] / pw, float(file_dpi[1]) * final.size[1] / ph)
    job.new_data, ext, job.media_type = _encode(final, job.format, new_dpi)
    job.new_href = job.href if not ext else re.sub(r"\.[^./]+$", "", job.href) + ext
    job.status = "완료"
    notes = []
    if job.tile_diff > WARN_TILE_DIFF:
        notes.append(f"일부가 원본과 많이 다름(칸 최대 차 {job.tile_diff:.0f}) — 글자·선이 바뀌지 않았는지 사람 확인")
    if not job.reaches_target:
        notes.append(f"x{job.scale}로는 목표 DPI에 못 미침(필요 x{job.need:.1f})")
    job.note = " / ".join(notes)
    job.preview = {"before": _png(base), "after": _png(final)}


def _encode(image: Image.Image, fmt: str, dpi: tuple[float, float]) -> tuple[bytes, str, str]:
    """(바이트, 바뀐 확장자 또는 '', media-type). JPEG는 JPEG로, 나머지는 PNG로."""
    buffer = io.BytesIO()
    if fmt.startswith("jpeg"):
        image.save(buffer, "JPEG", quality=95, subsampling=0, dpi=dpi)
        return buffer.getvalue(), "", "image/jpg"
    image.save(buffer, "PNG", dpi=dpi, optimize=True)
    return buffer.getvalue(), (".png" if fmt in RUN_AS_PNG else ""), "image/png"


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def write_hwpx(source: Path | bytes, jobs: list[Job]) -> bytes:
    """완료된 작업의 그림 파일만 바꾼 hwpx 바이트. 나머지 항목은 바이트 그대로, 순서·압축 방식도 원본 그대로."""
    done = [j for j in jobs if j.status == "완료"]
    raw = source if isinstance(source, bytes) else Path(source).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = set(archive.namelist())
        replace: dict[str, tuple[str, bytes]] = {}      # 원래 zip 이름 → (새 zip 이름, 바이트)
        renamed: dict[str, str] = {}                    # bin_id → 새 href
        taken = set(names)
        for job in done:
            old = _zip_name(job.href, names)
            if old is None:
                job.status, job.note = "실패", f"패키지에 그림 파일이 없음: {job.href}"
                continue
            new_href = job.new_href
            if new_href != job.href:
                prefix = old[: len(old) - len(job.href)]           # 'Contents/'로 시작하는 패키지 대비
                if prefix + new_href in taken:
                    new_href = re.sub(r"(\.[^./]+)$", r"_up\1", new_href)
                job.new_href = new_href
                renamed[job.bin_id] = new_href
                taken.add(prefix + new_href)
            replace[old] = (old[: len(old) - len(job.href)] + new_href, job.new_data)
        manifest = archive.read(MANIFEST).decode("utf-8") if renamed else None
        if manifest is not None:
            manifest = _fix_manifest(manifest, renamed, {j.bin_id: j.media_type for j in done})
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            for item in archive.infolist():
                if item.filename in replace:
                    name, data = replace[item.filename]
                    info = zipfile.ZipInfo(name, date_time=item.date_time)
                    info.compress_type = item.compress_type
                    info.external_attr = item.external_attr
                    target.writestr(info, data)
                elif item.filename == MANIFEST and manifest is not None:
                    target.writestr(item, manifest.encode("utf-8"), compress_type=item.compress_type)
                else:
                    target.writestr(item, archive.read(item.filename), compress_type=item.compress_type)
    return out.getvalue()


def _zip_name(href: str, names: set[str]) -> str | None:
    for name in (href, "Contents/" + href):
        if name in names:
            return name
    return None


def _fix_manifest(text: str, renamed: dict[str, str], media: dict[str, str]) -> str:
    """content.hpf에서 이름이 바뀐 그림 항목의 href·media-type만 고친다(나머지 글자는 그대로)."""
    def fix(match: re.Match) -> str:
        tag = match.group(0)
        bin_id = re.search(r'\bid="([^"]*)"', tag).group(1)
        if bin_id not in renamed:
            return tag
        tag = re.sub(r'\bhref="[^"]*"', f'href="{renamed[bin_id]}"', tag)
        return re.sub(r'\bmedia-type="[^"]*"', f'media-type="{media[bin_id]}"', tag)

    return re.sub(r"<(?:\w+:)?item\b[^>]*>", fix, text)
