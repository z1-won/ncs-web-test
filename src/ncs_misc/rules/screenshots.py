"""기타 ④: 특정 컴퓨터 프로그램 화면을 캡처하였을 경우 작업 표시줄을 잘라 내거나 지웠는가.

1. 캡처 화면 후보: 캡션·근처 출처 줄에 '스크린 숏·화면·캡처' 단서가 있거나, 픽셀 비율이 모니터 비율(16:9·16:10·21:9)이고
   가로가 화면 해상도 범위(800~3,840px)인 그림. 4160×2340 같은 카메라 사진 크기는 후보가 아니다.
2. 후보의 맨 아래 행들을 픽셀로 읽어(BMP·PNG·JPEG — ncs_misc.images, ncs_misc.jpeg) 작업 표시줄 띠를 찾는다:
   - 높이: 그림 높이의 2.5~7%(1080px 화면이면 약 27~75px)
   - 띠 배경이 고르다(행마다 배경색에 가까운 픽셀이 60% 이상, 행끼리 배경 밝기 차 12 이하)
   - 띠 위 화면과 경계가 뚜렷하다(띠 바로 위 행들과 배경 밝기 차 25 이상)
   - 띠 안에 아이콘 같은 내용이 있다(배경과 다른 픽셀 2~45%) — 빈 여백 띠는 작업 표시줄이 아니다
3. 판정: 띠 감지 → X(체크리스트가 직접 요구) · 픽셀을 읽지 못함(프로그레시브 JPEG 등) → △ · 감지 안 됨 → O
   후보가 없으면 O(캡처 화면 없음). hwp는 그림을 읽지 못해 △.
실제 작업 표시줄이 있는 캡처 예시가 없어 감지 기준은 합성 이미지로만 검증했다(SW제품기획 최종본 후보 3개는 감지 안 됨).
"""

import re

from ncs_core import O, TRI, X

from ..images import decode_rows, label, picture_records
from .common import row

CHECK = "④ 캡처 화면 작업 표시줄"
SHOT_WORDS = re.compile(r"스크린\s*숏|스크린샷|화면\s*캡[처쳐]|캡[처쳐]\s*화면|\b화면\b")
SCREEN_RATIOS = (16 / 9, 16 / 10, 21 / 9)
RATIO_TOLERANCE = 0.03
MIN_W, MAX_W = 800, 3840
BAND = (0.025, 0.07)


def is_capture_candidate(record: dict, paragraphs: list[str]) -> bool:
    near = " ".join((paragraphs[j] or "") for j in range(record["para"], min(len(paragraphs), record["para"] + 8)))
    if SHOT_WORDS.search(record["caption"] + " " + near):
        return True
    w, h = record["px"]
    if not (w and h and MIN_W <= w <= MAX_W):
        return False
    return any(abs(w / h - r) / r <= RATIO_TOLERANCE for r in SCREEN_RATIOS)


def _luma(pixel) -> int:
    r, g, b = pixel
    return (299 * r + 587 * g + 114 * b) // 1000


def _row_stats(line: list[int]) -> tuple[int, float]:
    """(배경 밝기 = 가장 흔한 밝기 구간, 배경에 가까운 픽셀 비율)."""
    buckets = {}
    for v in line:
        buckets[v // 8] = buckets.get(v // 8, 0) + 1
    bg = max(buckets, key=buckets.get) * 8 + 4
    near = sum(1 for v in line if abs(v - bg) <= 12)
    return bg, near / len(line)


def find_taskbar(lines: dict[int, list[int]], height: int) -> int | None:
    """맨 아래 작업 표시줄 띠의 높이(px). 없으면 None. lines: 행 번호 → 밝기 목록(맨 아래 행들 포함)."""
    stats = {y: _row_stats(v) for y, v in lines.items()}
    lo, hi = max(8, int(height * BAND[0])), max(12, int(height * BAND[1]))
    for band in range(lo, hi + 1):
        rows = [y for y in range(height - band, height) if y in stats]
        above = [y for y in range(height - band - 4, height - band) if y in stats]
        if len(rows) < band or len(above) < 2:
            continue
        bgs = [stats[y][0] for y in rows]
        if max(bgs) - min(bgs) > 12 or min(stats[y][1] for y in rows) < 0.6:
            continue
        band_bg = sorted(bgs)[len(bgs) // 2]
        if min(abs(stats[y][0] - band_bg) for y in above) < 25:
            continue
        content = sum(sum(1 for v in lines[y] if abs(v - band_bg) > 30) for y in rows) / sum(len(lines[y]) for y in rows)
        if 0.02 <= content <= 0.45:
            return band
    return None


def check_screenshots(context) -> list[dict]:
    manuscript = context.manuscript
    if manuscript.format != "hwpx":
        return [row("④", "section1", "", None, {CHECK: TRI}, {CHECK: "hwp는 그림을 읽을 수 없음 — hwpx로 확인"})]
    records = picture_records(manuscript)
    candidates = [r for r in records if is_capture_candidate(r, manuscript.sections[r["section"]])]
    if not candidates:
        return [row("④", "section1", "", {"그림": len(records), "캡처 후보": 0}, {CHECK: O},
                    {CHECK: f"그림 {len(records)}개 중 캡처 화면으로 보이는 것 없음"})]
    rows, flagged = [], 0
    for r in candidates:
        w, h = r["px"]
        place = f"section{r['section']} > {r['caption'] or '문단 ' + str(r['para'])}"
        shown = {"픽셀": f"{w}×{h}", "형식": r["format"]}
        lo = h - int(h * BAND[1]) - 8
        decoded = decode_rows(r, range(max(0, lo), h))
        if decoded is None:
            flagged += 1
            rows.append(row("④", place, r["caption"], shown, {CHECK: TRI},
                            {CHECK: f"{label(r)} 캡처 화면 후보인데 픽셀을 읽지 못함({r['format']}) — 작업 표시줄 사람 확인"}))
            continue
        band = find_taskbar({y: [_luma(p) for p in line] for y, line in decoded.items()}, h)
        if band:
            flagged += 1
            rows.append(row("④", place, r["caption"], {**shown, "띠 높이": band}, {CHECK: X},
                            {CHECK: f"{label(r)} 맨 아래 {band}px에 작업 표시줄로 보이는 띠(고른 배경 + 위 화면과 경계 + 아이콘)"},
                            "캡처 화면에서 작업 표시줄을 잘라 내거나 지움(프로그램명 노출 불가)"))
    if not flagged:
        rows.append(row("④", "section1", "", {"캡처 후보": len(candidates)}, {CHECK: O},
                        {CHECK: f"캡처 화면 후보 {len(candidates)}개 모두 맨 아래 작업 표시줄 띠가 보이지 않음"}))
    return rows
