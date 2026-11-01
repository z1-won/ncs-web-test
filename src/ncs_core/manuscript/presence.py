"""참고 자료·활용 서식·부록이 본문에 있는지의 근거를 찾는다."""

import re

from .config import DEFAULT_PARSE_CONFIG, ParseConfig
from .patterns import REF_LINE

TAIL_PATTERNS = {"참고 자료": r"참\s*고\s*자\s*료", "활용 서식": r"활\s*용\s*서\s*식", "부록": r"부\s*록"}
TAIL_ORDER = ("참고 자료", "활용 서식", "부록")  # 양식의 꼬리 순서 — 고정
BANNER_MIN_RATIO = 5.0  # 제목 배너는 본문 폭의 가로로 긴 띠 그림(실데이터 12:1, 10:1)
BANNER_MIN_WIDTH = 30000  # HWP 단위(1/7200 inch) ≈ 106 mm. 본문 폭 그림만 배너로 본다


def banner_figures(figures) -> list[int]:
    """이름 없는 제목 배너로 보이는 그림의 문단 인덱스. figures: (문단, 이름, 가로, 세로)."""
    return sorted(
        p for p, name, w, h in figures
        if not name and w >= BANNER_MIN_WIDTH and h > 0 and w / h >= BANNER_MIN_RATIO
    )


def section_presence(sections, images, config: ParseConfig = DEFAULT_PARSE_CONFIG, figures=()) -> dict:
    """{이름: {'있음': bool|None, '근거': str, 'k': 위치, ['배너만': True], ['end': 끝]}}.

    images: 본문 섹션의 (문단 인덱스, 원본 그림 이름). figures: 본문 섹션의 모든 그림 (문단, 이름 또는 "", 가로, 세로).
    있음=None은 판단 보류: '배너만'이 True면 제목은 있는데 내용이 없는 경우, 아니면 내용은 있는데 활용 서식/부록 중
    무엇인지 확정하지 못한 경우다.
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

    # 2) 내용 패턴 — 참고 자료: 참고문헌 꼴 줄이 연속으로 충분히 있으면 존재로 본다
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

    # 3) 이름 없는 배너 그림: 꼬리 구간(참고 자료 이후)의 가로로 긴 띠 그림은 제목 배너다.
    #     양식의 꼬리 순서(참고 자료 → 활용 서식 → 부록)대로, 아직 제목을 못 찾은 이름에 차례로 배정한다.
    #     참고 자료는 앞 단계(제목·배너·내용 패턴)에서 먼저 확정하고, 그 뒤의 배너만 다룬다.
    unnamed = banner_figures(figures)
    if unnamed and out["참고 자료"]["있음"]:
        # 기준점: 참고 자료의 시작(제목·배너 위치 또는 참고문헌 첫 줄). 그 앞의 배너(참고 자료 자신의 배너)는 제외
        anchor = out["참고 자료"]["k"]
        after = [p for p in unnamed if p > anchor]
        pending = [n for n in ("활용 서식", "부록") if not out[n]["있음"]]
        for name, p in zip(pending, after):
            out[name] = {"있음": True, "근거": f"이름 없는 제목 배너 그림 (section1 p{p}, 꼬리 순서상 {name})", "k": p}

    # 제목·배너 뒤에 내용이 없으면(개발이력 전까지 문단이 적으면) '배너만' → △
    for name in ("활용 서식", "부록"):
        found = out[name]
        if not found["있음"]:
            continue
        others = [TAIL_PATTERNS[o] for o in TAIL_PATTERNS if o != name]
        # 끝 지점: 다음 제목 텍스트, 개발 이력, 또는 다른 꼬리 이름의 확정 위치(배너 그림이면 텍스트가 없으므로)
        next_heading = min((out[o]["k"] for o in TAIL_PATTERNS if o != name and out[o]["k"] is not None and out[o]["k"] > found["k"]), default=len(raw))
        stop = next(
            (
                i
                for i, l in lines
                if i > found["k"] and (re.search(r"개발\s*이력", l) or any(re.fullmatch(p, l) for p in others))
            ),
            len(raw),
        )
        stop = min(stop, next_heading)
        body_n = len([l for i, l in lines if found["k"] < i < stop and not re.match(r"^※", l)])
        if body_n < config.tail_min_paragraphs:
            out[name] = {
                "있음": None,
                "배너만": True,  # 제목(텍스트·배너)은 있는데 내용이 없음 → 양식 잔재일 가능성
                "근거": f'{found["근거"]} 뒤에 내용이 없음(문단 {body_n}개) — 양식 배너만 남은 것인지 확인',
                "k": found["k"],
            }

    # 활용 서식: 제목(텍스트·배너)이 없을 때 참고 자료 뒤의 내용으로 추정한다.
    # 양식의 꼬리 순서는 참고 자료 → 활용 서식 → 부록 → 개발 이력으로 고정이므로, 부록 제목(배너) 위치를 알면
    # 참고 자료 끝과 부록 사이의 내용은 활용 서식으로 확정할 수 있다. 부록 위치를 모르면 둘 중 무엇인지 알 수 없어 None.
    if not out["활용 서식"]["있음"] and out["참고 자료"]["있음"]:
        start = out["참고 자료"].get("end", out["참고 자료"]["k"])
        appendix_k = out["부록"]["k"] if out["부록"]["있음"] is not False else None
        stop = (
            appendix_k
            if appendix_k is not None and appendix_k > start
            else next((i for i, l in lines if i > start and re.search(r"개발\s*이력", l)), len(raw))
        )
        middle = [l for i, l in lines if start < i < stop and not REF_LINE.match(l) and not re.match(r"^※", l)]
        if len(middle) >= config.ambiguous_tail_min_paragraphs:
            if appendix_k is not None and stop == appendix_k:
                out["활용 서식"] = {
                    "있음": True,
                    "근거": (
                        f'제목 텍스트·배너 이름은 없지만 참고 자료 뒤~부록 제목 앞(section1 p{start + 1}~p{stop - 1})에 '
                        f'문단 {len(middle)}개 있음 (예: "{middle[0][:30]}") — 꼬리 순서상 활용 서식'
                    ),
                    "k": start + 1,
                    "end": stop - 1,
                }
            else:
                out["활용 서식"] = {
                    "있음": None,
                    "근거": (
                        f'제목은 없지만 참고 자료 뒤~개발이력 앞에 문단 {len(middle)}개 있음 (예: "{middle[0][:30]}") '
                        "— 활용 서식 또는 부록 내용으로 보임(제목이 이미지라 둘을 구분 못 함), 확인 필요"
                    ),
                    "k": start + 1,
                }
    return out
