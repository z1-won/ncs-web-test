"""업스케일 제안 보고서 — 그림마다 원본/결과 그림 파일, JSON, 사람이 보는 HTML(원본·결과 나란히)."""

from __future__ import annotations

import html
import json
from pathlib import Path

from ncs_misc.images import label

from .pipeline import Job, grade


def rows(jobs: list[Job], skipped: list[dict], *, engine: str, target_dpi: int, min_dpi: int) -> list[dict]:
    out = []
    for job in jobs:
        first = job.uses[0]
        out.append({
            "그림": label(first), "BinData": job.bin_id, "원래 파일": job.href, "새 파일": job.new_href or None,
            "위치": [f"구역 {u['section']} 문단 {u['para']}" for u in job.uses],
            "원본 픽셀": f"{job.px[0]}×{job.px[1]}", "출력 mm": f"{first['mm'][0]}×{first['mm'][1]}",
            "원본 DPI": job.dpi, "판정(원본 기준)": grade(job.dpi, target_dpi, min_dpi),
            "엔진": engine, "배율": job.scale, "필요 배율": round(job.need, 2),
            "결과 픽셀": f"{job.out_px[0]}×{job.out_px[1]}" if job.out_px[0] else None,
            "업스케일 후 DPI(참고)": job.out_dpi, "목표 충족": job.status == "완료" and job.reaches_target,
            "원본과 차(전체/칸 최대)": f"{job.diff:.1f} / {job.tile_diff:.1f}" if job.diff is not None else None,
            "상태": job.status, "비고": job.note, "걸린 초(추정)": round(job.seconds, 1),
        })
    for s in skipped:
        r = s["record"]
        out.append({"그림": label(r), "BinData": r["bin_id"], "위치": [f"구역 {r['section']} 문단 {r['para']}"],
                    "원본 DPI": r["dpi"], "판정(원본 기준)": grade(r["dpi"], target_dpi, min_dpi), "상태": "건너뜀", "비고": s["이유"]})
    return out


def save(folder: Path, stem: str, jobs: list[Job], table: list[dict], summary: dict) -> dict[str, Path]:
    """folder 아래에 <stem>_그림/(원본·결과 PNG), <stem>_업스케일보고서.json·.html을 쓴다."""
    images = folder / f"{stem}_그림"
    images.mkdir(parents=True, exist_ok=True)
    pairs = {}
    for job in jobs:
        if job.preview:
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in job.bin_id)
            before, after = images / f"{safe}_원본.png", images / f"{safe}_업스케일.png"
            before.write_bytes(job.preview["before"])
            after.write_bytes(job.preview["after"])
            pairs[job.bin_id] = (f"{images.name}/{before.name}", f"{images.name}/{after.name}")
    data = folder / f"{stem}_업스케일보고서.json"
    data.write_text(json.dumps({"요약": summary, "그림": table}, ensure_ascii=False, indent=2), encoding="utf-8")
    page = folder / f"{stem}_업스케일보고서.html"
    page.write_text(_html(stem, table, pairs, summary), encoding="utf-8")
    return {"json": data, "html": page, "images": images}


def _html(stem: str, table: list[dict], pairs: dict, summary: dict) -> str:
    e = html.escape
    cards = []
    for row in table:
        pair = pairs.get(row.get("BinData"))
        facts = "".join(f"<dt>{e(k)}</dt><dd>{e(_text(v))}</dd>" for k, v in row.items()
                        if k not in ("그림",) and v not in (None, "", []))
        figs = (f'<div class="pair"><figure><img src="{e(pair[0])}"><figcaption>원본</figcaption></figure>'
                f'<figure><img src="{e(pair[1])}"><figcaption>업스케일</figcaption></figure></div>') if pair else ""
        state = {"완료": "ok", "실패": "bad", "건너뜀": "skip"}.get(row.get("상태"), "")
        cards.append(f'<section class="card {state}"><h2>{e(row["그림"])}</h2>{figs}<dl>{facts}</dl></section>')
    head = "".join(f"<li>{e(k)}: {e(_text(v))}</li>" for k, v in summary.items())
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>업스케일 제안 — {e(stem)}</title><style>
body{{font-family:"Malgun Gothic",sans-serif;margin:16px;background:#fafafa;color:#222}}
.card{{background:#fff;border:1px solid #ddd;border-left:6px solid #999;border-radius:6px;padding:12px;margin:12px 0}}
.card.ok{{border-left-color:#2a8a3e}}.card.bad{{border-left-color:#c62828}}.card.skip{{border-left-color:#bbb}}
h2{{font-size:16px;margin:0 0 8px}}.pair{{display:flex;gap:12px;flex-wrap:wrap}}
figure{{margin:0;flex:1 1 300px}}figure img{{width:100%;border:1px solid #ccc;background:#fff}}
figcaption{{font-size:12px;color:#666}}dl{{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;font-size:13px}}
dt{{color:#666}}dd{{margin:0}}.warn{{background:#fff8e1;border:1px solid #f0c36d;padding:8px 12px;border-radius:6px}}
</style></head><body><h1>업스케일 제안 — {e(stem)}</h1>
<p class="warn">판정은 원본 그림 기준이다. 업스케일은 화질만 올리고 원래 그림의 저작권은 그대로 남는다.
업스케일 모델이 글자·선을 바꿀 수 있으니 도표는 원본과 나란히 놓고 사람이 확인한다.</p>
<ul>{head}</ul>{''.join(cards)}</body></html>"""


def _text(value) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value))
    if isinstance(value, bool):
        return "예" if value else "아니오"
    return str(value)
