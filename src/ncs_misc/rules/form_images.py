"""기타 ⑧: '활용 서식'과 '부록'에서 해상도가 불량인 텍스트 이미지는 직접 입력 처리하였는가.

활용 서식·부록 구역(section_presence) 안의 그림만 본다. 글자가 든 이미지인지는 OCR이 있어야 알 수 있어
해상도로만 판정한다 — 기준은 기타 ⑤와 같다(CheckConfig.min_dpi·good_dpi).
  X  < 72 DPI  글자 이미지라면 읽기 어려움 → 직접 입력(사진이라도 해상도 자체가 불량)
  △  < 150 DPI 글자 이미지인지·읽을 수 있는지 사람 확인
  O  그 밖 / -  서식·부록이 없거나 그 안에 그림이 없음
SW제품기획 최종본 10종은 서식·부록 안 그림이 0개라 이 기준을 보정할 데이터가 없었다.
"""

import re

from ncs_core import NA, O, TRI, X

from ..images import label, picture_records, size_advice
from .common import row

CHECK = "⑧ 서식·부록 글자 이미지 해상도"
DEVELOPMENT = re.compile(r"(?:NCS\s*학습모듈\s*)?개발\s*이력")


def form_ranges(context) -> list[tuple[str, int, int]]:
    """(이름, 시작 문단, 끝 문단(포함)) — 활용 서식·부록. 끝을 모르면 다음 꼬리 구역 또는 개발 이력 앞까지."""
    body = context.manuscript.sections[context.config.body_section]
    starts = {name: v["k"] for name, v in context.presence.items()
              if isinstance(v, dict) and v.get("있음") and v.get("k") is not None}
    development = next((i for i, t in enumerate(body) if DEVELOPMENT.fullmatch((t or "").strip())), len(body))
    out = []
    for name in ("활용 서식", "부록"):
        if name not in starts:
            continue
        k = starts[name]
        found = context.presence[name]
        end = found.get("end")
        if end is None:
            later = [v for v in starts.values() if v > k] + [development]
            end = min(later) - 1
        out.append((name, k, end))
    return out


def check_form_images(context) -> list[dict]:
    manuscript, config = context.manuscript, context.config
    # hwp는 그림을 못 읽고, 서식·부록 제목이 그림이면 영역도 못 찾는다 → '없음(해당 없음)'으로 적합 처리하지 않고 먼저 △
    if manuscript.format != "hwpx":
        return [row("⑧", "section1", "", None, {CHECK: TRI}, {CHECK: "hwp는 그림 개체를 읽을 수 없음 — hwpx로 확인"})]
    ranges = form_ranges(context)
    if not ranges:
        return [row("⑧", "section1", "", None, {CHECK: NA}, {CHECK: "활용 서식·부록이 없음"})]
    records = [(name, r) for r in picture_records(manuscript, [config.body_section])
               for name, a, b in ranges if a <= r["para"] <= b]
    if not records:
        names = ", ".join(n for n, _, _ in ranges)
        return [row("⑧", "section1", "", {"그림": 0}, {CHECK: NA}, {CHECK: f"{names} 안에 그림이 없음(직접 입력한 서식)"})]
    rows = []
    for name, r in records:
        place = f"section1 > {name} > {r['caption'] or '문단 ' + str(r['para'])}"
        shown = {"픽셀": f"{r['px'][0]}×{r['px'][1]}", "출력 mm": f"{r['mm'][0]}×{r['mm'][1]}", "DPI": r["dpi"]}
        if r["dpi"] is None:
            rows.append(row("⑧", place, name, shown, {CHECK: TRI}, {CHECK: f"{name}의 {label(r)} 그림 파일을 읽지 못함 — 글자 이미지인지 사람 확인"}))
        elif r["dpi"] < config.min_dpi:
            rows.append(row("⑧", place, name, shown, {CHECK: X},
                            {CHECK: f"{name}의 {label(r)} {r['dpi']} DPI — {config.min_dpi} DPI 미만, 글자 이미지라면 직접 입력"},
                            f"글자 이미지는 한글로 직접 입력, 사진·그림은 해상도가 높은 것으로 교체{size_advice(r, config.good_dpi)}"))
        elif r["dpi"] < config.good_dpi:
            rows.append(row("⑧", place, name, shown, {CHECK: TRI},
                            {CHECK: f"{name}의 {label(r)} {r['dpi']} DPI — 글자 이미지라면 읽을 수 있는지 사람 확인"},
                            f"글자가 흐리면 직접 입력. 사진·그림이라면 교체{size_advice(r, config.good_dpi)}"))
        else:
            rows.append(row("⑧", place, name, shown, {CHECK: O}, {}))
    return rows
