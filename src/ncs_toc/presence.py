"""참고 자료·활용 서식·부록이 본문에 있는지의 근거를 찾는다."""

import re

from .config import DEFAULT_CONFIG, CheckConfig
from .patterns import REF_LINE

TAIL_PATTERNS = {"참고 자료": r"참\s*고\s*자\s*료", "활용 서식": r"활\s*용\s*서\s*식", "부록": r"부\s*록"}


def section_presence(sections, images, config: CheckConfig = DEFAULT_CONFIG) -> dict:
    """{이름: {'있음': bool|None, '근거': str, 'k': 위치}}.

    images: 본문 섹션의 (문단 인덱스, 원본 그림 이름). None은 '배너만 있고 내용은 없음'으로 사람 확인.
    """
    raw = sections[1] if len(sections) > 1 else []
    lines = [(i, l) for i, l in enumerate(raw) if l]
    out = {}
    for name, pattern in TAIL_PATTERNS.items():
        found = {"있음": False, "근거": "제목 텍스트·배너 이미지·내용 패턴 어느 것도 없음", "k": None}
        hit = next(((i, l) for i, l in lines if re.fullmatch(pattern, l)), None)
        if hit:  # 1) 제목 텍스트
            found = {"있음": True, "근거": f'제목 텍스트 "{hit[1]}" (section1 p{hit[0]})', "k": hit[0]}
        else:  # 2) 배너 이미지
            compact = pattern.replace(r"\s*", "")
            banner = next(((p, n) for p, n in images if re.search(compact, n.replace(" ", ""))), None)
            if banner:
                found = {"있음": True, "근거": f'배너 이미지 "{banner[1]}" (section1 p{banner[0]})', "k": banner[0]}
        out[name] = found

    # 제목·배너 뒤에 내용이 없으면(개발이력 전까지 문단이 적으면) '배너만' → △
    for name in ("활용 서식", "부록"):
        found = out[name]
        if not found["있음"]:
            continue
        others = [TAIL_PATTERNS[o] for o in TAIL_PATTERNS if o != name]
        stop = next(
            (
                i
                for i, l in lines
                if i > found["k"] and (re.search(r"개발\s*이력", l) or any(re.fullmatch(p, l) for p in others))
            ),
            len(raw),
        )
        body_n = len([l for i, l in lines if found["k"] < i < stop and not re.match(r"^※", l)])
        if body_n < config.tail_min_paragraphs:
            out[name] = {
                "있음": None,
                "근거": f'{found["근거"]} 뒤에 내용이 없음(문단 {body_n}개) — 양식 배너만 남은 것인지 확인',
                "k": found["k"],
            }

    # 3) 내용 패턴 — 참고 자료: 참고문헌 꼴 줄이 연속으로 충분히 있으면 존재로 본다
    if not out["참고 자료"]["있음"]:
        run, best = [], []
        for i, l in lines:
            if REF_LINE.match(l):
                run.append(i)
            else:
                if len(run) > len(best):
                    best = run
                run = []
        if len(run) > len(best):
            best = run
        if len(best) >= config.reference_min_lines:
            out["참고 자료"] = {
                "있음": True,
                "근거": f"참고문헌 꼴 줄 {len(best)}개 연속 (section1 p{best[0]}~p{best[-1]}) — 제목은 텍스트가 아님(이미지일 가능성)",
                "k": best[0],
                "end": best[-1],
            }

    # 활용 서식: 참고 자료 뒤 ~ 개발이력 앞에 내용이 있으면 '있을 가능성'
    if not out["활용 서식"]["있음"] and out["참고 자료"]["있음"]:
        start = out["참고 자료"].get("end", out["참고 자료"]["k"])
        stop = next((i for i, l in lines if i > start and re.search(r"개발\s*이력", l)), len(raw))
        middle = [l for i, l in lines if start < i < stop and not REF_LINE.match(l) and not re.match(r"^※", l)]
        if len(middle) >= config.ambiguous_tail_min_paragraphs:
            out["활용 서식"] = {
                "있음": None,
                "근거": (
                    f'제목은 없지만 참고 자료 뒤~개발이력 앞에 문단 {len(middle)}개 있음 (예: "{middle[0][:30]}") '
                    "— 활용 서식 또는 부록 내용으로 보임(제목이 이미지라 둘을 구분 못 함), 확인 필요"
                ),
                "k": start + 1,
            }
    return out
