"""원고 분량 산정(REQ-02-013) — 원고 1개의 구성별 행·쪽, 기존 원고 대비 변경 분량, 권고 분량(75~85쪽) 표시, 수작업 대조 오차율.

산정 규칙(계약서 제13조 4항, 요구사항 표준 지침)
- 1행에 1자 이상 → 1행. 행 띄움·문단 나누기(빈 문단)도 1행. 출처를 밝힌 인용·캡션 글도 넣는다. 시각 자료는 뺀다.
- 쪽: 줄 배치를 읽은 원고는 물리 쪽마다 산정 대상이 차지한 높이가 본문 높이의 ½ 이상이면 1쪽, 아니면 그 쪽의 행을 '행'으로 남긴다.
  기입 분량(매) = 쪽 + (남은 행 ÷ 쪽당 행 수, ½ 이상 올림). 배치 정보가 없으면 전체 행 ÷ 쪽당 행 수(½ 이상 올림)로 '추정'한다.
- 변경 분량: 변경된 행만 같은 방식으로 센다.
판정 원칙: 확인하지 못한 것은 '판단불가'(추정치로는 권고 범위를 판정하지 않는다, 구성을 찾지 못하면 알린다).
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

from .config import DEFAULT_CONFIG, MM_PER_UNIT, SEGMENTS, VolumeConfig
from .diff import changed_lines
from .layout import Layout, Line, Unit, read_layout
from .segments import assign

UNDECIDED = "판단불가"


def round_half_up(value: float) -> int:
    """½ 이상이면 올림(계약서 '½쪽 이상인 경우 1쪽')."""
    return math.floor(value + 0.5)


def tally(lines: list[Line], layout: Layout, config: VolumeConfig) -> dict:
    """행 목록 → {'쪽', '행', '기입 분량', '쪽 환산', '행 합계'}."""
    lpp, body = layout.lines_per_page, config.body_height
    total = sum(line.count for line in lines)
    if not layout.measured:
        pages, rest = divmod(total, lpp)
        return {"쪽": pages, "행": rest, "기입 분량": round_half_up(total / lpp), "쪽 환산": round(total / lpp, 2), "행 합계": total}
    fill: dict[int, float] = defaultdict(float)
    count: dict[int, int] = defaultdict(int)
    for line in lines:
        page = line.page + int(line.top // body)
        top, height = line.top % body, line.height
        count[page] += line.count
        while height > 0:
            put = min(height, body - top)
            fill[page] += put
            height -= put
            page, top = page + 1, 0.0
    full = {p for p, h in fill.items() if h >= config.half_page * body}
    rest = sum(n for p, n in count.items() if p not in full)
    return {"쪽": len(full), "행": rest, "기입 분량": len(full) + round_half_up(rest / lpp),
            "쪽 환산": round(sum(fill.values()) / body, 2), "행 합계": total}


def _counted_units(layout: Layout, names: list[str], config: VolumeConfig) -> list[tuple[str, Unit]]:
    return [(name, unit) for block, name in zip(layout.blocks, names) if config.counted(name) for unit in block.units]


def _method(layout: Layout, config: VolumeConfig) -> str:
    if layout.measured:
        return f"배치 정보(한글이 {layout.format} 파일에 저장한 줄 배치 — 화면에 보이는 줄·쪽)"
    return f"추정(줄 배치 정보가 없어 글자 폭으로 줄 수를 셈 — 한 줄 약 {config.chars_per_line:g}자)"


def _range(value: int, layout: Layout, config: VolumeConfig) -> dict:
    low, high = config.recommended
    if not layout.measured:
        status = UNDECIDED
        note = f"추정치 {value}쪽이라 권고 범위({low}~{high}쪽)를 판정하지 않음 — 한글에서 저장한 원고로 다시 산정"
    elif value < low:
        status, note = "권고보다 적음", f"{value}쪽 — 권고 {low}~{high}쪽보다 {low - value}쪽 적음"
    elif value > high:
        status, note = "권고보다 많음", f"{value}쪽 — 권고 {low}~{high}쪽보다 {value - high}쪽 많음"
    else:
        status, note = "권고 범위 안", f"{value}쪽 — 권고 {low}~{high}쪽 안"
    return {"최소": low, "최대": high, "상태": status, "비고": note}


def measure(path: Path | str, *, previous: Path | str | None = None, manual_pages: float | None = None,
            config: VolumeConfig = DEFAULT_CONFIG) -> dict:
    """원고 분량 산정표. previous를 주면 기존 원고 대비 변경 분량, manual_pages를 주면 수작업 산정 대비 오차율을 함께."""
    layout = read_layout(path, config)
    names, found = assign(layout.blocks)
    body_mm = round(config.body_height * MM_PER_UNIT, 1)
    notes = []
    if not layout.measured:
        notes.append("줄 배치 정보가 없어(한글이 아닌 도구로 만든 파일 등) 행·쪽은 추정치입니다. 한글에서 저장한 hwp/hwpx로 다시 산정하세요.")
    counted_names = [name for name, counted in SEGMENTS if config.counted(name)]
    missing = [name for name in counted_names if name not in found]
    if not any(name.startswith("학습 —") for name in found):
        notes.append(f"{UNDECIDED}: 학습(내비게이터·필요 지식) 제목을 찾지 못해 구성 구분을 믿을 수 없습니다. 합계는 표지 뒤 전체를 센 값입니다.")
    if missing:
        notes.append("찾지 못한 구성(원고에 없거나 제목을 읽지 못함): " + ", ".join(missing))
    if not config.include_appendix:
        notes.append("부록을 산정에서 뺐습니다(요구사항정의서 V0.23 해석). 계약서 제13조 4항 ①은 부록을 산정 대상에 넣습니다.")

    rows = []
    for name, counted in SEGMENTS:
        picked = [b for b, n in zip(layout.blocks, names) if n == name]
        if not picked:
            continue
        lines = [line for b in picked for u in b.units for line in u.lines]
        pages = sorted({b.page + 1 for b in picked if b.page >= 0})
        rows.append({
            "구성": name, "반영": config.counted(name), "행": sum(line.count for line in lines),
            "쪽 환산": round((sum(line.height for line in lines) / config.body_height) if layout.measured
                          else sum(line.count for line in lines) / layout.lines_per_page, 2),
            "물리 쪽": f"{pages[0]}~{pages[-1]}" if pages else "",
            "시각 자료 제외(쪽)": round(sum(b.visual for b in picked) / config.body_height, 2),
        })
    units = _counted_units(layout, names, config)
    total = tally([line for _, unit in units for line in unit.lines], layout, config)
    result = {
        "원고": Path(path).name, "형식": layout.format, "측정 방식": _method(layout, config), "추정": not layout.measured,
        "가정": {
            "본문 높이": f"{body_mm}㎜ (A4 297㎜ − 위 20 − 아래 13 − 머리말 10 − 꼬리말 12)",
            "쪽당 행 수": layout.lines_per_page,
            "줄 간격": f"{layout.pitch} HWPUNIT ({round(layout.pitch * MM_PER_UNIT, 2)}㎜)"
                      + (" — 이 원고에서 가장 많은 본문 줄 간격" if layout.measured else " — 설정값"),
            "½쪽 기준": f"쪽마다 산정 대상 높이 ≥ {config.half_page:g} × 본문 높이면 1쪽",
            "부록": "포함(계약서 제13조 4항 ①)" if config.include_appendix else "제외",
        },
        "물리 쪽 수": layout.pages if layout.measured else None,
        "구성": rows,
        "합계": total,
        "권고 분량": _range(total["기입 분량"], layout, config),
        "변경": None, "수작업 대조": None, "알림": notes,
    }
    if previous is not None:
        result["변경"] = compare(layout, names, units, previous, config)
    if manual_pages is not None:
        result["수작업 대조"] = manual_check(total["기입 분량"], manual_pages, config)
    return result


def compare(layout: Layout, names: list[str], units: list[tuple[str, Unit]], previous: Path | str, config: VolumeConfig) -> dict:
    old = read_layout(previous, config)
    old_names, _ = assign(old.blocks)
    old_units = _counted_units(old, old_names, config)
    changed = changed_lines([u for _, u in old_units], [u for _, u in units])
    by_segment: dict[str, int] = defaultdict(int)
    for index, line in changed:
        by_segment[units[index][0]] += line.count
    lines = [line for _, line in changed]
    count = tally(lines, layout, config)
    total = sum(line.count for _, unit in units for line in unit.lines)
    old_total = tally([line for _, unit in old_units for line in unit.lines], old, config)
    return {
        "기존 원고": Path(previous).name, "기존 원고 분량": old_total, "기존 원고 추정": not old.measured,
        "변경 행": count["행 합계"], "변경 분량": count,
        "변경 비율": f"{(count['행 합계'] / total * 100) if total else 0:.1f}%",
        "구성별 변경 행": [{"구성": name, "변경 행": by_segment[name]} for name, _ in SEGMENTS if name in by_segment],
        "방법": "문단·표 행 단위로 짝을 짓고, 바뀐 글자가 1자라도 든 행을 1행 변경으로 셈(새 문단·새 표 행은 전부 변경)",
    }


def manual_check(auto: int, manual: float, config: VolumeConfig) -> dict:
    """수작업 산정 대비 오차율 = |자동 − 수작업| ÷ 수작업 × 100. 허용 오차(0.5%) 안이면 '기준 충족'."""
    if manual <= 0:
        raise ValueError("수작업 산정 쪽수는 0보다 커야 합니다")
    rate = abs(auto - manual) / manual * 100
    return {"자동": auto, "수작업": manual, "오차율": f"{rate:.2f}%",
            "기준": f"{config.tolerance_percent:g}% 이내", "결과": "기준 충족" if rate <= config.tolerance_percent else "기준 초과"}
