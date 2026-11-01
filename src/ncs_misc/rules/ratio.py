"""기타 ⑥: 학습 내용(N-M)마다 필요 지식과 수행 내용의 글자 수 비율이 3:7인가(최소한 5:5).

구간은 unit_regions의 학습 내용 구간 안에서 '필요 지식' 머리 ~ '수행 내용' 머리 = 필요 지식, '수행 내용' 머리 ~ 구간 끝 = 수행 내용.
글자 수는 공백을 뺀 글자 수이고 표 안 문단(수행 tip 상자 등)도 그 구간의 내용으로 센다. 메모 문단은 뺀다.
"""

import re

from ncs_core import O, TRI, X, visible
from ncs_core.manuscript import MEMO_LINE, mark

from .common import row

SPACES = re.compile(r"\s+")


def section_lengths(body: dict, unit: dict, aside: frozenset[int]) -> dict:
    """{'필요 지식': 글자 수, '수행 내용': 글자 수, 'found': {'필요 지식': bool, '수행 내용': bool}}"""
    lines = body["lines"]
    lengths, part, found = {"필요 지식": 0, "수행 내용": 0}, None, {"필요 지식": False, "수행 내용": False}
    for k in range(unit["k0"] + 1, unit["k1"]):
        i, text = lines[k]
        head = mark(text)
        if head in ("필요 지식", "수행 내용"):
            part, found[head] = head, True
            continue
        if head in ("교수·학습 방법", "평가"):
            break
        if part is None or i in aside or MEMO_LINE.match(text):
            continue
        lengths[part] += len(SPACES.sub("", text))
    return {**lengths, "found": found}


def check_ratio(context) -> list[dict]:
    config = context.config
    aside = context.manuscript.section_aside_paragraphs(config.body_section) or frozenset()
    rows = []
    for unit in context.units:
        key = f"{unit['no']}-{unit['sub']}"
        region = f"section1 > 학습 {unit['lesson']} > {key}. {visible(unit['text'])}"
        lengths = section_lengths(context.body, unit, aside)
        k, p = lengths["필요 지식"], lengths["수행 내용"]
        checks, notes = {}, {}
        if not lengths["found"]["필요 지식"] or not lengths["found"]["수행 내용"]:
            missing = [n for n, ok in lengths["found"].items() if not ok]
            checks["필요 지식:수행 내용 비율"] = TRI
            notes["필요 지식:수행 내용 비율"] = f"{key} '{'·'.join(missing)}' 머리를 찾지 못해 비율을 계산하지 못함"
        elif k + p == 0:
            checks["필요 지식:수행 내용 비율"] = TRI
            notes["필요 지식:수행 내용 비율"] = f"{key} 본문 글자가 없음"
        else:
            share = k / (k + p)
            tenths = round(share * 10)  # 비율은 'n:10-n' 한 자리로 보고 그 기준으로 판정(5:5는 통과)
            ratio = f"{tenths}:{10 - tenths}"
            over = tenths > round(config.knowledge_max_share * 10)
            checks["필요 지식:수행 내용 비율"] = X if over else O
            if over:
                notes["필요 지식:수행 내용 비율"] = f"{key} {ratio} (필요 지식 {k:,}자 / 수행 내용 {p:,}자) — 필요 지식이 절반을 넘음"
            elif tenths > round(config.knowledge_target_share * 10):
                notes["필요 지식:수행 내용 비율(참고)"] = f"{key} {ratio} — 3:7 권장, 5:5 이내라 통과"
        rows.append(row("⑥", region, key, {"필요 지식": k, "수행 내용": p}, checks, notes, "필요 지식을 줄이거나 수행 내용을 보강해 3:7에 가깝게"))
    return rows or [row("⑥", "section1", "", None, {"필요 지식:수행 내용 비율": TRI}, {"필요 지식:수행 내용 비율": "학습 내용(N-M) 구간을 찾지 못함"})]
