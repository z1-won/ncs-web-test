"""평가 ③: 평가 방법은 2개 이상 필수적으로 제시하였는가? 학습당 1행.

'평가 방법' 소제목 아래 글머리 항목(서술형 시험, 평가자 질문, 역할 연기 …)을 세고, 방법별 표(학습 내용 | 평가 항목) 수와 대조한다.
"""

from ncs_core import O, TRI, X, verdict

ITEM_ID = "F02-평가-③"
CHECK = "③ 평가 방법 2개 이상"


def check_methods(regions: list[dict], *, min_methods: int = 2) -> list[dict]:
    rows = []
    for region in regions:
        lesson = region["lesson"]
        checks, notes = {}, {}
        names = [m["name"] for m in region["methods"]]
        if not region["found"]:
            checks[CHECK] = TRI
            notes[CHECK] = "; ".join(region["notes"]) or "평가 구역을 찾지 못함"
        else:
            count = max(len(names), region["method_tables"]) if not names else len(names)
            checks[CHECK] = O if count >= min_methods else X
            if not names and region["method_tables"]:
                checks[CHECK] = TRI
                notes[CHECK] = f"'평가 방법' 글머리 항목을 찾지 못했으나 방법 표가 {region['method_tables']}개 있음 — 원고 확인"
            elif count < min_methods:
                notes[CHECK] = f"{count}개 — {min_methods}개 이상 제시해야 함" + (f": {', '.join(names)}" if names else "")
            if names and region["method_tables"] and region["method_tables"] != len(names):
                checks["방법별 표 수"] = X
                notes["방법별 표 수"] = f"평가 방법 {len(names)}개({', '.join(names)})인데 평가 항목 표는 {region['method_tables']}개"
            odd = region.get("odd_method_heads") or []
            if odd:
                # 표는 평가 방법 표로 세되(표 수 비교는 정상), 양식의 머리 칸 '평가 항목'과 다르므로 X(완화하지 않음)
                checks["방법별 표 머리"] = X
                notes["방법별 표 머리"] = (f"평가 방법 표 {len(odd)}개의 머리 칸이 '평가 항목'이 아니라 '평가'(문단 {', '.join(map(str, odd))}) "
                                       "— 양식대로 '평가 항목'으로 고칠 것")
        result = verdict(checks)
        rows.append({"item_id": ITEM_ID, "region_path": f"section1 > 학습 {lesson} > 평가 > 평가 방법", "위치": f"학습 {lesson}",
                     "원고": {"개수": len(names), "방법": names, "표": region["method_tables"]}, "체크": checks, "판정": result,
                     "비고": notes, "수정 제안": None if result == "적합" else f"평가 방법을 {min_methods}개 이상 제시하고 방법마다 평가 항목 표 작성"})
    return rows
