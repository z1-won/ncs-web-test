"""기타 ⑤: 이미지의 크기 및 해상도는 적절한가 — 그림마다 실효 DPI(원본 픽셀 ÷ 쪽 위 출력 크기).

체크리스트·F14·F06·F04·F21·F08 어디에도 숫자 기준이 없다(F21에 '저해상도 이미지 교체', '해상도가 떨어지는 사진 수정 필요'뿐).
그래서 기준(CheckConfig.target_dpi)은 화면에서 고른다 — 300(인쇄 권장, 기본) 또는 150(ncs_core.pictures.DPI_CHOICES).
  △  기준 미만  사람 확인. 검수 자료 안내서 D-01은 이미지 판독을 '후보 제시 + 에디팅 기관 확정'으로 두므로 자동으로 부적합을 내지 않는다
  O  기준 이상
그림 파일을 못 읽거나 형식을 모르면 △. hwp는 그림 개체를 읽지 못해 △.
수정 제안에는 그림마다 계산한 필요 픽셀 수와 최대 출력 크기(ncs_core.pictures.size_advice)를 적는다.
"""

from ncs_core import NA, O, TRI

from ncs_core.pictures import label, picture_records, size_advice
from .common import row

CHECK = "⑤ 이미지 해상도"


def check_resolution(context) -> list[dict]:
    manuscript, config = context.manuscript, context.config
    if manuscript.format != "hwpx":
        return [row("⑤", "section1", "", None, {CHECK: TRI}, {CHECK: "hwp는 그림 개체·크기를 읽을 수 없음 — hwpx로 확인"})]
    records = picture_records(manuscript)
    if not records:
        return [row("⑤", "section1", "", {"그림": 0}, {CHECK: NA}, {CHECK: "그림이 없음"})]
    rows, low = [], 0
    for r in records:
        place = f"section{r['section']} > {r['caption'] or '문단 ' + str(r['para'])}"
        shown = {"픽셀": f"{r['px'][0]}×{r['px'][1]}", "출력 mm": f"{r['mm'][0]}×{r['mm'][1]}", "DPI": r["dpi"], "형식": r["format"]}
        if r["dpi"] is None:
            low += 1
            rows.append(row("⑤", place, r["caption"], shown, {CHECK: TRI},
                            {CHECK: f"{label(r)} 그림 파일을 읽지 못해 해상도를 계산하지 못함(형식: {r['format'] or '알 수 없음'})"}))
        elif r["dpi"] < config.target_dpi:
            low += 1
            rows.append(row("⑤", place, r["caption"], shown, {CHECK: TRI},
                            {CHECK: f"{label(r)} {r['dpi']} DPI — 기준 {config.target_dpi} DPI 미만, 인쇄 시 흐려 보이는지 사람 확인"
                                    f"({r['px'][0]}×{r['px'][1]}px를 {r['mm'][0]}×{r['mm'][1]}mm로 출력)"},
                            f"흐려 보이면 원본 해상도가 높은 그림으로 바꾸거나 출력 크기를 줄임{size_advice(r, config.target_dpi)}"))
    if not low:
        dpis = [r["dpi"] for r in records]
        rows.append(row("⑤", "section1", "", {"그림": len(records), "최저 DPI": min(dpis)}, {CHECK: O},
                        {CHECK: f"그림 {len(records)}개 모두 기준 {config.target_dpi} DPI 이상(최저 {min(dpis)})"}))
    return rows
