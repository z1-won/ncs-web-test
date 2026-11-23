"""원고 분량 산정(REQ-02-013) — 원고 1개의 구성별 행·쪽, 기존 원고 대비 변경 분량, 권고 분량(75~85쪽) 표시, 수작업 대조 오차율.

산정 규칙(계약서 제13조 4항, 요구사항 표준 지침)
- 1행에 1자 이상 → 1행. 행 띄움·문단 나누기(빈 문단)도 1행. 출처를 밝힌 인용·캡션 글도 넣는다. 시각 자료는 뺀다.
- 쪽: 줄 배치를 읽은 원고는 물리 쪽마다 산정 대상이 차지한 높이가 본문 높이의 ½ 이상이면 1쪽, 아니면 그 쪽의 행을 '행'으로 남긴다.
  기입 분량(매) = 쪽 + (남은 행 ÷ 쪽당 행 수, ½ 이상 올림). 배치 정보가 없으면 전체 행 ÷ 쪽당 행 수(½ 이상 올림)로 '추정'한다.
- 변경 분량(개선): 바뀐 행만 따로 모아 빈 공간 없이 이어 붙인 분량으로 센다(F16 정산지침 인쇄 20쪽) — gathered.
  물리 쪽마다 ½쪽 규칙을 적용한 값은 '물리 쪽 기준(참고)'으로만 남긴다.
- 출력본 PDF를 함께 주면 전체 쪽 수·구성별 쪽 범위·쪽별 채움 높이를 PDF에서 재고(printed.py) 그 기입 분량을 산정에 쓴다.
  한글 줄 배치 계산값은 '합계'에 그대로 두고 나란히 보여 준다. 다른 원고의 PDF면 판단불가로 알리고 한글 값을 쓴다.
- 집필료: 채택한 기입 분량 × 단가(fee.py, 계약서 F07·정산지침 F16 근거).
판정 원칙: 확인하지 못한 것은 '판단불가'(추정치로는 권고 범위를 판정하지 않는다, 구성을 찾지 못하면 알린다).
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

from .config import DEFAULT_CONFIG, MM_PER_UNIT, SEGMENTS, VolumeConfig, round_half_up
from ncs_core.pdf import PdfUnavailable

from .diff import changed_lines
from .fee import compute_fee
from .layout import Layout, Line, Unit, read_layout
from .printed import measure_printed
from .segments import OPTIONAL, assign, toc_tail

UNDECIDED = "판단불가"
VISUAL_NOTE = ("이 산정은 계약서 제2조 5항 기준(시각 자료 전부 제외)입니다. F16 정산지침 검수 기준과 다른 점(인용된 사진·삽화는 원고 매수에 넣음, "
               "같은 세분류 기개발 학습모듈에서 재인용한 글·표는 원고료에서 뺌)은 반영하지 않았으니 사람이 확인하세요.")


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


def gathered(lines: list[Line], layout: Layout, config: VolumeConfig) -> dict:
    """바뀐 행 → 개선 기준 변경 분량. F16 정산지침 인쇄 20쪽 '(개선) 새로 수정한 부분만을 별도로 모아 … 빈 공간 없이 새로운 문서로
    작성'에 따라 행을 원고의 물리 쪽에 두지 않고 이어 붙여 센다: 쪽 환산 = 바뀐 행 높이 합 ÷ 본문 높이(줄 배치가 없으면 행 수 ÷ 쪽당 행 수),
    온 쪽 + 남은 부분이 ½쪽 이상이면 1쪽.

    '행 띄움·문단 나누기는 그대로 둔다': Line.height는 같은 쪽 다음 줄까지의 거리라 바뀐 줄에 딸린 줄 사이·문단 간격이 들어 있다
    (쪽 마지막 줄은 줄 높이 + 줄 사이). 빈 문단(행 띄움)은 그 자체가 행이라 새로 생겼거나 바뀌었을 때만 들어간다.
    """
    count = sum(line.count for line in lines)
    if layout.measured:
        pages = sum(line.height for line in lines) / config.body_height
        how = "바뀐 행을 빈 공간 없이 이어 붙임 — 바뀐 행 높이 합(줄 사이·문단 간격 포함) ÷ 본문 높이"
    else:
        pages = count / layout.lines_per_page
        how = f"바뀐 행을 빈 공간 없이 이어 붙임 — 바뀐 행 수 ÷ 쪽당 {layout.lines_per_page}행(추정)"
    full = math.floor(pages)
    rest = pages - full
    return {"기입 분량": full + (1 if rest >= config.half_page else 0), "쪽 환산": round(pages, 2), "온 쪽": full,
            "남은 부분(쪽)": round(rest, 2), "행 합계": count,
            "방법": f"{how}, 온 쪽 + 남은 부분이 {config.half_page:g}쪽 이상이면 1쪽(F16 정산지침 인쇄 20쪽 개선 기준)"}


def _counted_units(layout: Layout, names: list[str], config: VolumeConfig) -> list[tuple[str, Unit]]:
    return [(name, unit) for block, name in zip(layout.blocks, names) if config.counted(name) for unit in block.units]


def _missing_notes(missing: list[str], toc: list[str]) -> list[str]:
    """찾지 못한 구성 알림. 활용 서식·부록은 필수가 아니므로(F11 인쇄 20~21쪽) 차례에도 없으면 '원고에 없음'으로, 차례에는 있는데
    본문에서 못 찾았으면 경고로 나눈다. 차례의 꼬리 목록을 읽지 못했으면 선택 구성이라고만 적는다."""
    required = [name for name in missing if name not in OPTIONAL]
    optional = [name for name in missing if name in OPTIONAL]
    notes = []
    if required:
        notes.append("찾지 못한 구성(원고에 없거나 제목을 읽지 못함): " + ", ".join(required))
    if not optional:
        return notes
    absent = [name for name in optional if toc and name not in toc]
    listed = [name for name in optional if name in toc]
    unknown = [name for name in optional if not toc]
    if absent:
        notes.append(f"원고에 없음(필수 아님 — 차례에도 없음, F11 매뉴얼 인쇄 20~21쪽): {', '.join(absent)}")
    if listed:
        notes.append(f"차례에는 있는데 본문에서 찾지 못한 구성(제목을 읽지 못했을 수 있음): {', '.join(listed)}")
    if unknown:
        notes.append(f"찾지 못한 선택 구성(필수 집필 사항 아님 — F11 매뉴얼 인쇄 20~21쪽, 차례를 읽지 못해 원고에 없는지는 확인 못함): {', '.join(unknown)}")
    return notes


def _method(layout: Layout, config: VolumeConfig) -> str:
    if layout.measured:
        return f"배치 정보(한글이 {layout.format} 파일에 저장한 줄 배치 — 화면에 보이는 줄·쪽)"
    return f"추정(줄 배치 정보가 없어 글자 폭으로 줄 수를 셈 — 한 줄 약 {config.chars_per_line:g}자)"


def _range(value: int, measured: bool, config: VolumeConfig) -> dict:
    low, high = config.recommended
    if not measured:
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
            config: VolumeConfig = DEFAULT_CONFIG, print_pdf: Path | str | None = None,
            fee_unit: int | None = None, contract_pages: int | None = None) -> dict:
    """원고 분량 산정표. previous를 주면 기존 원고 대비 변경 분량, manual_pages를 주면 수작업 산정 대비 오차율,
    print_pdf(출력본)를 주면 쪽을 PDF에서 잰 값, fee_unit(원/쪽)·contract_pages(계약 분량 매)로 집필료를 함께 낸다."""
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
    notes += _missing_notes(missing, toc_tail(layout.blocks, names))
    if not config.include_appendix:
        notes.append("부록을 산정에서 뺐습니다(요구사항정의서 V0.23 해석). 계약서 제13조 4항 ①, F16 정산지침 인쇄 19쪽 검수 대상 표(부록 ○), "
                     "F11 매뉴얼 인쇄 20~21쪽(집필 인정 범위 '2. 위치'~'7. 활용 서식/부록')은 부록을 산정 대상에 넣습니다.")
    notes.append(VISUAL_NOTE)

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
            "부록": "포함(계약서 제13조 4항 ①, F16 정산지침 인쇄 19쪽 검수 대상 표, F11 매뉴얼 인쇄 20~21쪽)" if config.include_appendix else "제외",
            "권고 분량": f"{config.recommended[0]}~{config.recommended[1]}쪽 — F11 매뉴얼 인쇄 20~21쪽 '권당 평균 매수(약 80쪽 내외)를 "
                       "과도하게 넘지 않도록' 권장, 범위는 3차 멘토 미팅 답변(계약 조건 아님, 참고 표시)",
            "시각 자료": "계약서 제2조 5항 기준 — 사진·삽화·도면·차트·그래프는 인용·직접 제작 구분 없이 모두 뺌",
        },
        "물리 쪽 수": layout.pages if layout.measured else None,
        "구성": rows,
        "합계": total,
        "권고 분량": None, "변경": None, "수작업 대조": None, "알림": notes,
        "출력본": None, "채택 분량": None, "집필료": None,
    }
    if print_pdf is not None:
        result["출력본"] = _printed(print_pdf, layout, rows, total, config)
        if not result["출력본"]["사용"]:
            notes.append(result["출력본"]["사유"] + " — 한글 줄 배치 값으로 산정합니다.")
    use_pdf = bool(result["출력본"] and result["출력본"]["사용"])
    if use_pdf:
        adopted, basis = result["출력본"]["합계"]["기입 분량"], "출력본 PDF 측정(쪽 수·쪽 범위·쪽별 채움) + 남은 행 계산"
    elif layout.measured:
        adopted, basis = total["기입 분량"], "한글 줄 배치 계산"
    else:
        adopted, basis = total["기입 분량"], "추정(글자 폭으로 줄 수를 셈)"
    result["채택 분량"] = {"기입 분량": adopted, "근거": basis, "한글 계산": total["기입 분량"],
                         "출력본 측정": result["출력본"]["합계"]["기입 분량"] if use_pdf else None}
    result["권고 분량"] = _range(adopted, use_pdf or layout.measured, config)
    if previous is not None:
        result["변경"] = compare(layout, names, units, previous, config)
    if manual_pages is not None:
        result["수작업 대조"] = manual_check(adopted, manual_pages, config)
    changed = result["변경"]["변경 분량"]["기입 분량"] if result["변경"] else None
    result["집필료"] = compute_fee(adopted, basis, config=config, unit=fee_unit, contract_pages=contract_pages,
                                changed_pages=changed, estimated=not (use_pdf or layout.measured))
    return result


def _printed(print_pdf: Path | str, layout: Layout, rows: list[dict], total: dict, config: VolumeConfig) -> dict:
    """출력본 산정. pypdf가 없으면 판단불가로 돌려준다(PDF가 아니거나 못 읽는 파일은 ValueError로 올린다)."""
    try:
        return measure_printed(print_pdf, layout, rows, total, config)
    except PdfUnavailable as error:
        return {"파일": Path(print_pdf).name, "사용": False, "사유": f"{UNDECIDED}: {error}", "측정 구분": [], "구성": [],
                "합계": None, "쪽별": [], "알림": []}


def compare(layout: Layout, names: list[str], units: list[tuple[str, Unit]], previous: Path | str, config: VolumeConfig) -> dict:
    old = read_layout(previous, config)
    old_names, _ = assign(old.blocks)
    old_units = _counted_units(old, old_names, config)
    changed = changed_lines([u for _, u in old_units], [u for _, u in units])
    by_segment: dict[str, int] = defaultdict(int)
    for index, line in changed:
        by_segment[units[index][0]] += line.count
    lines = [line for _, line in changed]
    count = gathered(lines, layout, config)
    total = sum(line.count for _, unit in units for line in unit.lines)
    old_total = tally([line for _, unit in old_units for line in unit.lines], old, config)
    return {
        "기존 원고": Path(previous).name, "기존 원고 분량": old_total, "기존 원고 추정": not old.measured,
        "변경 행": count["행 합계"], "변경 분량": count,
        "물리 쪽 기준(참고)": tally(lines, layout, config),   # 바뀐 행을 새 원고의 물리 쪽에 둔 채 쪽마다 ½쪽 규칙 — 산정에 쓰지 않음
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
