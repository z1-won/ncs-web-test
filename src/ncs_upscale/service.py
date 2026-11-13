"""웹 화면용 그림 업스케일 — 그림 목록 → 원본 보기 → 한 장씩 업스케일 → 업스케일한 그림으로 제안본 hwpx.

명령행(__main__)은 원고 하나를 통째로 돌리지만, 화면은 사람이 원본을 보고 고른 그림만 한 장씩 키운다(한 장 20~40초).
결과는 업로드 폴더 아래 work 폴더에 그림 파일 + 정보(JSON)로 남기고, 제안본은 그 결과로 만든다.
업로드가 만료되면 폴더와 함께 지워진다.

GPU는 하나라 업스케일은 한 번에 하나씩만 돌린다(_GPU 잠금). 다른 요청은 앞 작업이 끝날 때까지 기다린다.
"""

from __future__ import annotations

import io
import json
import re
import threading
from pathlib import Path
from typing import Callable

from PIL import Image

from ncs_core.documents import load_document
from ncs_misc.images import label, picture_records

from .engine import DEFAULT_ENGINE, ENGINES
from .pipeline import DEFAULT_MIN_DPI, DEFAULT_TARGET_DPI, Job, _rgb, grade, plan, upscale, write_hwpx

MAX_SCALE = 2                 # 화면에서는 x2만(한 장 20~40초). x4는 4배 느려 요청 하나로 기다리기 어렵다
_GPU = threading.Lock()
_CACHE: dict[tuple[str, float], tuple[list[dict], dict]] = {}
_CACHE_LOCK = threading.Lock()

Runner = Callable[[Path, Path, int], None]


class PictureError(ValueError):
    """화면에 그대로 보여 줄 오류(그림 없음, 목표 이상 등)."""


def _records(manuscript: Path) -> tuple[list[dict], dict]:
    """(picture_records, binaries). 같은 파일을 여러 요청이 읽으므로 경로·수정 시각으로 기억해 둔다(최근 4개)."""
    key = (str(manuscript), manuscript.stat().st_mtime)
    with _CACHE_LOCK:
        if key in _CACHE:
            return _CACHE[key]
    document = load_document(manuscript)
    if document.format != "hwpx":
        raise PictureError("hwp 원고는 그림을 읽지 못합니다. 한글에서 hwpx로 저장해 다시 올리세요")
    value = (picture_records(document), document.binaries)
    with _CACHE_LOCK:
        _CACHE[key] = value
        while len(_CACHE) > 4:
            _CACHE.pop(next(iter(_CACHE)))
    return value


def _safe(bin_id: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]", "_", bin_id)


def _job_for(manuscript: Path, bin_id: str, target_dpi: int) -> tuple[Job | None, list[dict]]:
    records, binaries = _records(manuscript)
    uses = [r for r in records if r["bin_id"] == bin_id]
    if not uses:
        raise PictureError(f"원고에 그림 {bin_id}가 없습니다")
    jobs, _ = plan(uses, binaries, ENGINES[DEFAULT_ENGINE], target_dpi=target_dpi, max_scale=MAX_SCALE)
    return (jobs[0] if jobs else None), uses


def engine_status(tools: Path | None = None) -> dict:
    engine = ENGINES[DEFAULT_ENGINE]
    try:
        engine.find_exe(tools)
        problem = None
    except FileNotFoundError as error:
        problem = str(error)
    return {"name": engine.name, "note": engine.note, "available": problem is None, "problem": problem}


def list_pictures(manuscript: Path, work: Path, *, target_dpi: int = DEFAULT_TARGET_DPI,
                  min_dpi: int = DEFAULT_MIN_DPI) -> dict:
    """목표 DPI 미만인 그림 파일 목록(낮은 DPI 순). 같은 그림 파일을 여러 곳에 쓰면 한 항목에 자리를 모은다."""
    records, binaries = _records(manuscript)
    jobs, skipped = plan(records, binaries, ENGINES[DEFAULT_ENGINE], target_dpi=target_dpi, max_scale=MAX_SCALE)
    done = {item["bin_id"]: item for item in _results(work)}
    pictures = []
    for job in sorted(jobs, key=lambda j: j.dpi):
        first = job.uses[0]
        pictures.append({
            "bin_id": job.bin_id, "label": label(first), "caption": first.get("caption") or "",
            "places": [f"구역 {u['section']} 문단 {u['para']}" for u in job.uses],
            "px": list(job.px), "mm": list(first["mm"]), "format": job.format,
            "dpi": job.dpi, "grade": grade(job.dpi, target_dpi, min_dpi),
            "need": round(job.need, 2), "scale": job.scale, "reaches_target": job.reaches_target,
            "upscaled": done.get(job.bin_id),
        })
    return {
        "target_dpi": target_dpi, "min_dpi": min_dpi, "pictures": pictures,
        "counts": {"그림": len(records), "그림 파일": len({r["bin_id"] for r in records if r["bin_id"]}),
                   "대상": len(pictures), "건너뜀": len(skipped)},
        "skipped": [{"label": label(s["record"]), "reason": s["이유"]} for s in skipped],
    }


def original_png(manuscript: Path, bin_id: str) -> bytes:
    """그림 파일을 브라우저가 보여 줄 수 있는 PNG로(원고 그림 대부분이 BMP). 투명 부분은 흰 바탕."""
    records, _ = _records(manuscript)
    data = next((r["data"] for r in records if r["bin_id"] == bin_id and r["data"]), None)
    if data is None:
        raise PictureError(f"원고에 그림 {bin_id}가 없습니다")
    with Image.open(io.BytesIO(data)) as image:
        buffer = io.BytesIO()
        _rgb(image).save(buffer, "PNG")
    return buffer.getvalue()


def upscale_one(manuscript: Path, bin_id: str, work: Path, *, target_dpi: int = DEFAULT_TARGET_DPI,
                tools: Path | None = None, runner: Runner | None = None) -> dict:
    """그림 하나를 업스케일해 work 폴더에 저장하고 결과 정보를 돌려준다. 실패해도 정보(status='실패', note)를 돌려준다."""
    job, _ = _job_for(manuscript, bin_id, target_dpi)
    if job is None:
        raise PictureError(f"그림 {bin_id}는 이미 {target_dpi} DPI 이상이거나 형식을 읽지 못해 업스케일 대상이 아닙니다")
    with _GPU:
        upscale([job], ENGINES[DEFAULT_ENGINE], tools=tools, runner=runner, progress=lambda _: None)
    info = {"bin_id": job.bin_id, "status": job.status, "note": job.note, "href": job.href, "new_href": job.new_href,
            "media_type": job.media_type, "px": list(job.px), "out_px": list(job.out_px), "dpi": job.dpi,
            "out_dpi": job.out_dpi, "scale": job.scale, "need": round(job.need, 2), "reaches_target": job.reaches_target,
            "diff": None if job.diff is None else round(job.diff, 1),
            "tile_diff": None if job.tile_diff is None else round(job.tile_diff, 1), "seconds": round(job.seconds, 1)}
    work.mkdir(parents=True, exist_ok=True)
    name = _safe(job.bin_id)
    if job.status == "완료":
        (work / f"{name}.bin").write_bytes(job.new_data)
    else:
        (work / f"{name}.bin").unlink(missing_ok=True)
    (work / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return info


def upscaled_file(work: Path, bin_id: str) -> tuple[bytes, str, str]:
    """(그림 바이트, media-type, 확장자) — 제안본에 들어갈 파일 그대로."""
    name = _safe(bin_id)
    info_path, data_path = work / f"{name}.json", work / f"{name}.bin"
    if not info_path.exists() or not data_path.exists():
        raise PictureError(f"그림 {bin_id}의 업스케일 결과가 없습니다. 먼저 업스케일하세요")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    ext = Path(info["new_href"]).suffix or ".png"
    return data_path.read_bytes(), info["media_type"] or "image/png", ext


def _results(work: Path) -> list[dict]:
    if not work.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(work.glob("*.json"))]


def build_proposal(manuscript: Path, work: Path) -> tuple[bytes, dict]:
    """업스케일에 성공한 그림만 같은 자리에 넣은 제안본 hwpx와 요약 {'바꾼 그림': n, '그림': [bin_id…]}."""
    jobs = []
    for info in _results(work):
        data_path = work / f"{_safe(info['bin_id'])}.bin"
        if info["status"] != "완료" or not data_path.exists():
            continue
        jobs.append(Job(bin_id=info["bin_id"], href=info["href"], format="", px=tuple(info["px"]), data=b"", uses=[],
                        dpi=info["dpi"], need=info["need"], scale=info["scale"], status="완료",
                        new_href=info["new_href"], new_data=data_path.read_bytes(), media_type=info["media_type"]))
    if not jobs:
        raise PictureError("업스케일한 그림이 없습니다. 그림을 먼저 업스케일하세요")
    content = write_hwpx(manuscript, jobs)
    placed = [j.bin_id for j in jobs if j.status == "완료"]
    if not placed:
        raise PictureError("업스케일한 그림을 원고에 넣지 못했습니다: " + "; ".join(j.note for j in jobs))
    return content, {"바꾼 그림": len(placed), "그림": placed}
