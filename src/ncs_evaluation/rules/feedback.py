"""평가 ⑤: 평가 방법별로 피드백을 제시하였는가 — 학습당 1행.

확정: 피드백 블록('N. 방법명') 수와 이름 = 평가 방법 목록(③이 읽은 글머리). 다르면 X.
휴리스틱: 블록마다 보충 학습(성취 낮은 경우)과 심화 학습(성취 높은 경우) 문구가 있는가 — 낱말로 찾고, 없으면 △(사람 확인).
"""

import re

from ncs_core import O, TRI, X, verdict
from ncs_core.notes import lines

ITEM_ID = "F02-평가-⑤"
COUNT = "⑤ 방법별 피드백 개수·이름 일치"
BOTH = "⑤ 심화·보충 학습 각각 제시"
REMEDIAL = re.compile(r"보충|미흡|낮은|낮을|보완|다시\s*설명|재학습|부족")
ENRICHMENT = re.compile(r"심화|우수|높은|높을|정확히\s*(이해|수행|파악)한\s*경우|향상|응용|확장|추가\s*과제")


def _norm(text: str) -> str:
    return re.sub(r"\s", "", text or "")


def check_feedback(regions: list[dict]) -> list[dict]:
    rows = []
    for region in regions:
        lesson = region["lesson"]
        checks, notes = {}, {}
        methods = [m["name"] for m in region["methods"]]
        blocks = region["feedback"]
        if not region["found"]:
            checks[COUNT] = TRI
            notes[COUNT] = "; ".join(region["notes"]) or "평가 구역을 찾지 못함"
        elif not region["feedback_found"]:
            checks[COUNT] = X
            notes[COUNT] = "'피드백' 소제목을 찾지 못함"
        elif not blocks:
            checks[COUNT] = X
            notes[COUNT] = "피드백 안에 'N. 평가 방법명' 블록이 없음"
        else:
            names = [b["name"] for b in blocks]
            if not methods:
                checks[COUNT] = TRI
                notes[COUNT] = f"평가 방법 목록을 읽지 못해 피드백 {len(blocks)}개({', '.join(names)})와 대조 못 함"
            else:
                missing = [m for m in methods if _norm(m) not in {_norm(n) for n in names}]
                extra = [n for n in names if _norm(n) not in {_norm(m) for m in methods}]
                ok = len(blocks) == len(methods) and not missing and not extra
                checks[COUNT] = O if ok else X
                if not ok:
                    parts = [f"평가 방법 {len(methods)}개 / 피드백 {len(blocks)}개"]
                    if missing:
                        parts.append("피드백 없는 방법: " + ", ".join(missing))
                    if extra:
                        parts.append("방법 목록에 없는 피드백: " + ", ".join(extra))
                    notes[COUNT] = " · ".join(parts)
            lacking = []
            for b in blocks:
                text = b["text"]
                need = [n for n, p in (("보충", REMEDIAL), ("심화", ENRICHMENT)) if not p.search(text)]
                if need:
                    lacking.append(f"학습 {lesson} 피드백 「{b['name']}」에 '{'·'.join(need)}' 문구 없음 (낱말로 찾음, 사람 확인)")
            checks[BOTH] = TRI if lacking else O
            if lacking:
                notes[BOTH] = lines(lacking)
        result = verdict(checks)
        rows.append({"item_id": ITEM_ID, "region_path": f"section1 > 학습 {lesson} > 평가 > 피드백", "위치": f"학습 {lesson}",
                     "원고": {"평가 방법": methods, "피드백": [b["name"] for b in blocks]}, "체크": checks, "판정": result, "비고": notes,
                     "수정 제안": None if result == "적합" else "평가 방법마다 피드백 블록을 두고, 성취가 높은 경우(심화)와 낮은 경우(보충)를 각각 제시"})
    return rows
